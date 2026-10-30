#!/usr/bin/env python3
"""Flash a firmware file to the WLE and/or the WBA via ST-Link (STM32_Programmer_CLI backend).

Each MCU takes one .hex or .bin file. A .bin needs a load address; a .hex must not have one.
The tool knows nothing about what the image is (bootloader, app, data): the address is yours.

The ST-Link serial (--wle-sn/--wba-sn) is optional: without it the tool connects to every
ST-Link (hot-plug, no reset) and picks the one whose target reports a WLE/WBA Device ID.
With it, the target behind that ST-Link is still checked to be the right MCU.
MCUs are flashed one after the other, WLE first.

Examples:
  stflash.py --list
  stflash.py --wle-fw sid_smartac_stm32wle5.hex
  stflash.py --wba-fw app.bin --wba-addr 0x08012000
  stflash.py --wle-fw wle.hex --wba-fw wba.hex
  stflash.py --wle-sn 003A00213133510A37363734 --wle-fw wle.bin --wle-addr 0x08008800 \\
             --wba-sn 0026003F3233511239363634 --wba-fw wba.hex

STM32_Programmer_CLI lookup: --cli, then $STM32_CUBEPROGRAMMER_CLI_BIN, then PATH, then the
default STM32CubeProgrammer install directories.

Python use (put smac_tools/run_ui/tools on sys.path or PYTHONPATH):
  import stflash
  result = stflash.flash(wle_fw="wle.hex", wba_fw="wba.hex")   # {"WLE": True, "WBA": True}
  probes = stflash.list_connected()                             # identified ST-Links
flash() prints the same log as the CLI and raises stflash.StFlashError for setup problems.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass

# ST-Link detection, MCU identification and CLI helpers live in stlink.py (shared with the other tools);
# the names are re-exported here so stflash.identify(), stflash.Probe, ... keep working
if __package__:
    from .stlink import (CLI_ENV, CLI_NAME, CONNECT_MODES, DEFAULT_FREQ, DEVICE_IDS, MCUS, Probe, StLinkError, _describe,  # noqa: F401
                         connect_args, find_cli, identify, list_probes, parse_device, parse_probe_list, resolve,
                         resolve_probes, run_job, strip_ansi)
else:
    from stlink import (CLI_ENV, CLI_NAME, CONNECT_MODES, DEFAULT_FREQ, DEVICE_IDS, MCUS, Probe, StLinkError, _describe,  # noqa: F401
                        connect_args, find_cli, identify, list_probes, parse_device, parse_probe_list, resolve,
                        resolve_probes, run_job, strip_ansi)

StFlashError = StLinkError  # the name stflash users know


@dataclass
class Job:
    mcu: str  # "WLE" or "WBA"
    fw: str
    addr: int | None = None  # .bin only
    sn: str | None = None
    erase: str | tuple | None = None  # None: only the pages written; "all": mass erase; (pages): those pages


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def _addr(value):
    try:
        addr = int(value, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an address: {value!r}")
    if addr < 0:
        raise argparse.ArgumentTypeError(f"negative address: {value!r}")
    return addr


def _erase(value):
    """--xxx-erase: "all", or flash pages like "0-116" or "0,1,5-8"."""
    if value.lower() == "all":
        return "all"
    pages = []
    try:
        for part in value.split(","):
            first, _, last = part.strip().partition("-")
            first, last = int(first, 0), int(last or first, 0)
            if first < 0 or last < first:
                raise ValueError
            pages.extend(range(first, last + 1))
    except ValueError:
        raise argparse.ArgumentTypeError(f"not 'all' or a page list like 0-116 or 0,1,5-8: {value!r}")
    return tuple(pages)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cli", help=f"path to {CLI_NAME}")
    p.add_argument("--mode", choices=CONNECT_MODES, default="UR",
                   help="SWD connect mode for flashing; UR uses reset=HWrst (NRST must be wired), "
                        "the others reset=SWrst (default: %(default)s)")
    p.add_argument("--freq", type=int, metavar="KHZ", help=f"SWD frequency in kHz (default: {DEFAULT_FREQ})")
    p.add_argument("--inter-mcu-delay", type=float, default=0,
                   help="seconds to wait between WLE and WBA flashing (default: %(default)s)")
    p.add_argument("--no-verify", action="store_true", help="do not verify after writing")
    p.add_argument("--no-reset", action="store_true", help="do not reset the MCU after writing")
    p.add_argument("--dry-run", action="store_true", help="print the commands, touch no hardware")
    p.add_argument("--list", action="store_true", help="list connected ST-Links and the MCU behind each, then exit")
    for mcu in MCUS:
        low = mcu.lower()
        g = p.add_argument_group(f"{mcu}")
        g.add_argument(f"--{low}-sn", metavar="SN", help=f"ST-Link serial of the {mcu} (default: auto-detect)")
        g.add_argument(f"--{low}-fw", metavar="FILE", help=f"{mcu} firmware file (.hex or .bin)")
        g.add_argument(f"--{low}-addr", metavar="ADDR", type=_addr, help=f"{mcu} load address, .bin only (e.g. 0x08000000)")
        g.add_argument(f"--{low}-erase", metavar="PAGES", type=_erase,
                       help=f"erase the {mcu} before writing: 'all', or pages like 0-116 or 0,1,5-8 "
                            f"(default: only the pages that are written)")
    return p.parse_args(argv)


def _erase_spec(mcu, erase):
    """None, "all" or a sorted tuple of page numbers. Raises StFlashError."""
    if erase is None or erase == "all":
        return erase
    if isinstance(erase, str):
        try:
            return _erase(erase)
        except argparse.ArgumentTypeError as e:
            raise StFlashError(f"{mcu} erase: {e}")
    try:
        pages = tuple(sorted(set(int(p) for p in erase)))
    except (TypeError, ValueError):
        raise StFlashError(f"{mcu} erase must be 'all' or page numbers: {erase!r}")
    if not pages or pages[0] < 0:
        raise StFlashError(f"{mcu} erase must be 'all' or page numbers: {erase!r}")
    return pages


def make_jobs(wle_fw=None, wba_fw=None, wle_addr=None, wba_addr=None, wle_sn=None, wba_sn=None, wle_erase=None,
              wba_erase=None):
    """Jobs for the given firmware files (WLE first). Raises StFlashError."""
    given = {"WLE": (wle_fw, wle_addr, wle_sn, wle_erase), "WBA": (wba_fw, wba_addr, wba_sn, wba_erase)}
    jobs = []
    for mcu in MCUS:
        low = mcu.lower()
        fw, addr, sn, erase = given[mcu]
        if fw is None:
            if sn is not None or addr is not None or erase is not None:
                raise StFlashError(f"--{low}-sn/--{low}-addr/--{low}-erase given without --{low}-fw")
            continue
        if not os.path.isfile(fw):
            raise StFlashError(f"{mcu} firmware not found: {fw}")
        ext = os.path.splitext(fw)[1].lower()
        if ext == ".bin":
            if addr is None:
                raise StFlashError(f"{mcu} firmware is a .bin, --{low}-addr is required")
        elif ext == ".hex":
            if addr is not None:
                raise StFlashError(f"{mcu} firmware is a .hex, it carries its own addresses: drop --{low}-addr")
        else:
            raise StFlashError(f"{mcu} firmware must be .hex or .bin: {fw}")
        jobs.append(Job(mcu=mcu, fw=os.path.abspath(fw), addr=addr, sn=sn, erase=_erase_spec(mcu, erase)))

    if not jobs:
        raise StFlashError("nothing to flash: give --wle-fw and/or --wba-fw")
    sns = [j.sn for j in jobs if j.sn is not None]
    if len(sns) != len(set(sns)):
        raise StFlashError("--wle-sn and --wba-sn are the same ST-Link")
    return jobs


def validate(args):
    """Turn parsed args into jobs (WLE first). Raises StFlashError."""
    return make_jobs(wle_fw=args.wle_fw, wba_fw=args.wba_fw, wle_addr=args.wle_addr, wba_addr=args.wba_addr,
                     wle_sn=args.wle_sn, wba_sn=args.wba_sn, wle_erase=args.wle_erase, wba_erase=args.wba_erase)


# ---------------------------------------------------------------------------
# Flash commands
# ---------------------------------------------------------------------------

def build_cmd(cli, job, mode="UR", freq=None, verify=True, reset=True):
    cmd = [cli] + connect_args(job.sn if job.sn is not None else "<auto>", mode, freq)
    if job.erase == "all":
        cmd += ["-e", "all"]
    elif job.erase:
        cmd += ["-e"] + [str(p) for p in job.erase]
    cmd += ["-w", job.fw]
    if job.addr is not None:
        cmd.append(f"0x{job.addr:08X}")
    if verify:
        cmd.append("-v")
    if reset:
        cmd.append("-rst")
    return cmd


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def list_connected(cli=None, mode="UR", freq=None):
    """Connected ST-Links, each identified (connect only). Raises StFlashError."""
    cli = find_cli(cli)
    probes = list_probes(cli)
    for probe in probes:
        identify(cli, probe, mode, freq)
    return probes


def flash(wle_fw=None, wba_fw=None, *, wle_addr=None, wba_addr=None, wle_sn=None, wba_sn=None, wle_erase=None,
          wba_erase=None, mode="UR", freq=None, verify=True, reset=True, cli=None, dry_run=False,
          inter_mcu_delay=0):
    """Flash the given MCUs, WLE first; prints the same log as the CLI.

    wle_erase / wba_erase: None (only the pages written are erased), "all" (mass erase) or page numbers erased
    before writing, in the same CLI run.

    Returns {mcu: ok} for every MCU given. Raises StFlashError for setup problems (bad arguments,
    STM32_Programmer_CLI not found, ST-Link missing or on the wrong MCU); a failed write is ok=False.
    """
    if mode not in CONNECT_MODES:
        raise StFlashError(f"mode must be one of {', '.join(CONNECT_MODES)}: {mode!r}")
    if inter_mcu_delay < 0:
        raise StFlashError("inter_mcu_delay cannot be negative")
    cli = find_cli(cli)
    jobs = make_jobs(wle_fw=wle_fw, wba_fw=wba_fw, wle_addr=wle_addr, wba_addr=wba_addr,
                     wle_sn=wle_sn, wba_sn=wba_sn, wle_erase=wle_erase, wba_erase=wba_erase)
    opts = dict(mode=mode, freq=freq, verify=verify, reset=reset)

    if dry_run:
        for job in jobs:
            print(f"[{job.mcu}] {' '.join(build_cmd(cli, job, **opts))}")
        return {job.mcu: True for job in jobs}

    probes = resolve([j.mcu for j in jobs], sns={j.mcu: j.sn for j in jobs if j.sn is not None}, cli=cli,
                     mode=mode, freq=freq)
    for job in jobs:
        job.sn = probes[job.mcu].sn

    results = {}
    for job in jobs:
        if job.mcu == "WBA" and "WLE" in results and inter_mcu_delay:
            print(f"[INFO] Waiting {inter_mcu_delay:g} seconds between WLE and WBA flashing")
            time.sleep(inter_mcu_delay)
        results[job.mcu] = run_job(build_cmd(cli, job, **opts), f"[{job.mcu}]")

    print()
    for job in jobs:
        print(f"[INFO] {job.mcu} ({job.sn}): {'OK' if results[job.mcu] else 'FAILED'}  {job.fw}")
    return results


def cmd_list(cli, args):
    probes = list_connected(cli, args.mode, args.freq)
    if not probes:
        print("[INFO] No ST-Link connected")
        return 0
    for probe in probes:
        mcu = probe.mcu or ("unknown" if probe.device_id is not None else "?")
        print(f"{probe.sn}  board={probe.board or '-'}  MCU={mcu}  "
              + (f"Device ID=0x{probe.device_id:03X} {probe.device_name or ''}" if probe.device_id is not None
                 else probe.error))
    return 0


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.list:
            return cmd_list(args.cli, args)
        results = flash(wle_fw=args.wle_fw, wba_fw=args.wba_fw, wle_addr=args.wle_addr, wba_addr=args.wba_addr,
                        wle_sn=args.wle_sn, wba_sn=args.wba_sn, wle_erase=args.wle_erase, wba_erase=args.wba_erase,
                        mode=args.mode, freq=args.freq,
                        verify=not args.no_verify, reset=not args.no_reset, cli=args.cli, dry_run=args.dry_run,
                        inter_mcu_delay=args.inter_mcu_delay)
    except StFlashError as e:
        print(f"[ERROR] {e}")
        return 1
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted")
        sys.exit(130)
