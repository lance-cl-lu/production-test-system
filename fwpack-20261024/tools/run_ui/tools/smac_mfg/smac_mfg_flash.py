#!/usr/bin/env python3
"""Program one device: SMAC manufacturing data + WLE and WBA firmware.

Steps (1 to 3 run as separate tools with this Python, their output is passed through):
  1. gen_smac_mfg.py      - smac_mfg.bin from the sensor ICs and the back label (tools/gen_smac_mfg)
  2. combine_binaries.py  - one WLE hex: WLE bootloader + WLE app + smac_mfg.bin at 0x0803F800 (tools/combine_binaries)
  3. combine_binaries.py  - one WBA hex: WBA bootloader + WBA app, then wba_confirm adds the confirmed app validity
                            marker (the app does not run on trial, so no factory rollback at later stations) and the
                            bootloader metadata the erase removes (installed container version = WBA + WLE app
                            version, app implementation SID)
  4. stflash.flash()      - flash the WLE hex, then the WBA hex (smac_tools/run_ui/tools/stflash)

Before writing, the WLE is erased completely and the WBA everything but MFG_DATA (the Sidewalk manufacturing data,
last page): a board left in any state by an earlier failed run is reprogrammed from scratch, keeping only that page.

The first failing step stops the run with "[ERROR] ..." and its exit code.

Usage:
  smac_mfg_flash.py --wle-boot wle_boot.hex --wle-app wle_app.hex --wba-boot wba_boot.hex --wba-app wba_app.hex \\
                    --ics LPS22 BME69X --label 1A-2B3C4D

Python use (put smac_tools/run_ui/tools on sys.path or PYTHONPATH):
  import smac_mfg
  result = smac_mfg.program("wle_boot.hex", "wle_app.hex", "wba_boot.hex", "wba_app.hex", ["LPS22", "BME69X"],
                            "1A-2B3C4D")
program() prints the same log as the CLI, returns {"WLE": True, "WBA": True} and raises
smac_mfg.MfgFlashError (.exit_code) on the first failing check or step.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)  # smac_tools/run_ui/tools: the other tools are siblings
GEN_SMAC_MFG = os.path.join(TOOLS, "gen_smac_mfg", "gen_smac_mfg.py")
COMBINE_BINARIES = os.path.join(TOOLS, "combine_binaries", "combine_binaries.py")

# the sibling tool packages; TOOLS is on sys.path already when smac_mfg is imported as a package
try:
    import gen_smac_mfg  # noqa: E402
    import stflash  # noqa: E402
    import wba_confirm  # noqa: E402
except ImportError:
    sys.path.insert(0, TOOLS)
    import gen_smac_mfg  # noqa: E402
    import stflash  # noqa: E402
    import wba_confirm  # noqa: E402

STEPS = 4
WLE_ERASE = "all"  # mass erase; the combined WLE hex brings the SMAC mfg data back
# WBA (STM32WBA5xxG_Sidewalk_OTA.ld): 8 KB pages, MFG_DATA = page 127 at 0x080FE000 is kept
WBA_PAGE_SIZE = 0x2000
WBA_MFG_DATA = 0x080FE000
WBA_ERASE = tuple(range((WBA_MFG_DATA - 0x08000000) // WBA_PAGE_SIZE))  # pages 0..126
STFLASH_OPTIONS = ("wle_sn", "wba_sn", "mode", "freq", "cli", "inter_mcu_delay")


class MfgFlashError(Exception):
    """A check or step failed; exit_code is the process exit code to report."""

    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wle-boot", required=True, metavar="FILE", help="WLE bootloader image (.hex or .elf)")
    p.add_argument("--wle-app", required=True, metavar="FILE", help="WLE application image (.hex or .elf)")
    p.add_argument("--wba-boot", required=True, metavar="FILE", help="WBA bootloader image (.hex or .elf)")
    p.add_argument("--wba-app", required=True, metavar="FILE", help="WBA application image (.hex or .elf)")
    p.add_argument("--ics", required=True, nargs="+", metavar="IC",
                   help="sensor ICs on the board: " + ", ".join(sorted(gen_smac_mfg.IC_SENSOR_BITS)))
    p.add_argument("--label", required=True, help="device back label, XX-XXXXXX or XXXXXXXX (hex)")
    p.add_argument("--out-dir", metavar="DIR", help="keep the combined WLE and WBA hex files here (default: deleted)")

    g = p.add_argument_group("passed to stflash")
    g.add_argument("--wle-sn", metavar="SN")
    g.add_argument("--wba-sn", metavar="SN")
    g.add_argument("--mode")
    g.add_argument("--freq", type=int, metavar="KHZ", help=f"SWD frequency in kHz (default: {stflash.stlink.DEFAULT_FREQ})")
    g.add_argument("--inter-mcu-delay", type=float, default=0,
                   help="seconds to wait between WLE and WBA flashing (default: %(default)s)")
    g.add_argument("--cli", metavar="PATH")
    g.add_argument("--dry-run", action="store_true", help="print the flash commands, touch no hardware")
    return p.parse_args(argv)


def validate(wle_boot, wle_app, wba_boot, wba_app, ics, label, out_dir=None):
    """Check everything before the first step runs. Raises MfgFlashError."""
    for opt, path in (("--wle-boot", wle_boot), ("--wle-app", wle_app), ("--wba-boot", wba_boot),
                      ("--wba-app", wba_app)):
        if not os.path.isfile(path):
            raise MfgFlashError(f"{opt}: no such file: {path}")
    if out_dir and not os.path.isdir(out_dir):
        raise MfgFlashError(f"--out-dir: no such directory: {out_dir}")
    if not gen_smac_mfg.LABEL_RE.match(label):
        raise MfgFlashError(f"label '{label}' is not XX-XXXXXX or XXXXXXXX (hex digits)")
    unknown = [ic for ic in ics if ic.strip().upper() not in gen_smac_mfg.IC_SENSOR_BITS]
    if not ics or unknown:
        raise MfgFlashError(f"unknown IC: {', '.join(unknown) or '(none given)'} "
                            f"(known: {', '.join(sorted(gen_smac_mfg.IC_SENSOR_BITS))})")
    for tool in (GEN_SMAC_MFG, COMBINE_BINARIES):
        if not os.path.isfile(tool):
            raise MfgFlashError(f"tool not found: {tool}")


def program_kwargs(args):
    """Keyword arguments for program() from parsed command-line args."""
    kw = {k: getattr(args, k) for k in ("wle_boot", "wle_app", "wba_boot", "wba_app", "ics", "label", "out_dir",
                                       "dry_run")}
    kw.update({k: getattr(args, k) for k in STFLASH_OPTIONS if getattr(args, k) is not None})
    return kw


def run_step(n, title, script, script_args):
    print(f"[INFO] [STEP {n}/{STEPS}] {title}", flush=True)
    rc = subprocess.call([sys.executable, "-u", script] + script_args)
    if rc != 0:
        raise MfgFlashError(f"{title} failed (exit {rc})", rc)


def flash_step(n, title, kw):
    print(f"[INFO] [STEP {n}/{STEPS}] {title}", flush=True)
    try:
        results = stflash.flash(**kw)
    except stflash.StFlashError as e:
        raise MfgFlashError(f"{title} failed: {e}")
    finally:
        sys.stdout.flush()
    failed = [mcu for mcu, ok in results.items() if not ok]
    if failed:
        raise MfgFlashError(f"{title} failed: {', '.join(failed)}")
    return results


def program(wle_boot, wle_app, wba_boot, wba_app, ics, label, *, out_dir=None, dry_run=False, **stflash_opts):
    """Run the four steps for one device; prints the same log as the CLI.

    stflash_opts: wle_sn, wba_sn, mode, freq, cli (see stflash.flash()). Returns stflash's {mcu: ok}.
    Raises MfgFlashError (with .exit_code) on the first failing check or step.
    """
    unknown = set(stflash_opts) - set(STFLASH_OPTIONS)
    if unknown:
        raise TypeError(f"program() got unexpected keyword arguments: {', '.join(sorted(unknown))}")
    ics = list(ics)
    validate(wle_boot, wle_app, wba_boot, wba_app, ics, label, out_dir)
    with tempfile.TemporaryDirectory(prefix="smac_mfg_") as tmp:
        mfg_bin = os.path.join(tmp, "smac_mfg.bin")
        wle_hex = os.path.join(tmp, f"wle_{label}.hex")
        wba_hex = os.path.join(tmp, f"wba_{label}.hex")

        run_step(1, "SMAC MFG data", GEN_SMAC_MFG, ["-i", *ics, "-l", label, "-o", mfg_bin])
        run_step(2, "WLE image", COMBINE_BINARIES,
                 [wle_boot, wle_app, mfg_bin, f"0x{gen_smac_mfg.FACTORY_DATA_ADDRESS:08X}", "-o", wle_hex])
        wba_unconfirmed = os.path.join(tmp, "wba_unconfirmed.hex")
        run_step(3, "WBA image (confirmed)", COMBINE_BINARIES, [wba_boot, wba_app, "-o", wba_unconfirmed])
        try:
            marker = wba_confirm.confirm(wba_unconfirmed, wba_hex, wle_hex=wle_hex)
            metadata = wba_confirm.describe_metadata(wba_confirm.read_hex(wba_unconfirmed),
                                                     wba_confirm.read_hex(wle_hex))
        except wba_confirm.WbaConfirmError as e:
            raise MfgFlashError(f"WBA image: {e}")
        print(f"[INFO] Confirmed app validity marker at 0x{marker:08X}", flush=True)
        print(f"[INFO] {metadata}", flush=True)
        if out_dir:
            for image in (wle_hex, wba_hex):
                shutil.copy(image, out_dir)
                print(f"[INFO] Kept {os.path.join(out_dir, os.path.basename(image))}")
        print(f"[INFO] Erase before writing: WLE all, WBA pages {WBA_ERASE[0]}..{WBA_ERASE[-1]} "
              f"(keeps MFG_DATA at 0x{WBA_MFG_DATA:08X})")
        results = flash_step(4, "Erase + flash WLE + WBA",
                             {"wle_fw": wle_hex, "wba_fw": wba_hex, "wle_erase": WLE_ERASE, "wba_erase": WBA_ERASE,
                              "dry_run": dry_run, **stflash_opts})

    print(f"[INFO] Done: label {label}, ICs {' '.join(ics)}")
    return results


def main(argv=None):
    args = parse_args(argv)
    try:
        program(**program_kwargs(args))
    except MfgFlashError as e:
        print(f"[ERROR] {e}", flush=True)
        return e.exit_code
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted")
        sys.exit(130)
