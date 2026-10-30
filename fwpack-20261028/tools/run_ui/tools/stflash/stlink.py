"""ST-Link and STM32_Programmer_CLI helpers shared by the tools in smac_tools/run_ui/tools.

Finds STM32_Programmer_CLI, lists the connected ST-Links, identifies the MCU behind each one (Device ID),
matches ST-Links to the WLE / WBA, runs CLI commands with streamed output and resets an MCU through NRST.

  from stflash import stlink
  cli = stlink.find_cli()
  probes = stlink.resolve(["WLE", "WBA"], cli=cli)     # {"WLE": Probe(sn=...), "WBA": Probe(...)}
  stlink.reset(cli, probes["WBA"].sn, "[WBA]")

resolve(..., cache=path) keeps the ST-Link -> MCU mapping in a file (see the mapping cache section).
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime

CLI_NAME = "STM32_Programmer_CLI"
CLI_ENV = "STM32_CUBEPROGRAMMER_CLI_BIN"

MCUS = ("WLE", "WBA")

# Device IDs (DBGMCU_IDCODE.DEV_ID) as named in STM32CubeProgrammer's Data_Base/STM32_Prog_DB_<id>.xml
DEVICE_IDS = {
    0x497: "WLE",  # STM32WLxx
    0x492: "WBA",  # STM32WBA52/54/55
    0x4B0: "WBA",  # STM32WBA6
    0x4B2: "WBA",  # STM32WBA2
}

CONNECT_MODES = ("UR", "NORMAL", "HOTPLUG")

DEFAULT_FREQ = 2000  # kHz, SWD clock used when no frequency is given

# a CLI run that fails before connecting (no "Device ID" in its output) did nothing on the target: run it again
CONNECT_ATTEMPTS = 3
CONNECT_RETRY_DELAY = 1.0  # s

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
ERROR_RE = re.compile(r"^\s*Error\s*:", re.MULTILINE)
PROBE_RE = re.compile(r"^\s*ST-Link Probe\s+\d+\s*:", re.MULTILINE | re.IGNORECASE)
PROBE_SN_RE = re.compile(r"^\s*ST-LINK SN\s*:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
BOARD_RE = re.compile(r"^\s*Board Name\s*:\s*(.*?)\s*$", re.MULTILINE | re.IGNORECASE)
DEVICE_ID_RE = re.compile(r"^\s*Device ID\s*:\s*(0x[0-9A-Fa-f]+)", re.MULTILINE | re.IGNORECASE)
DEVICE_NAME_RE = re.compile(r"^\s*Device name\s*:\s*(.*?)\s*$", re.MULTILINE | re.IGNORECASE)


class StLinkError(Exception):
    pass


@dataclass
class Probe:
    sn: str
    board: str | None = None
    device_id: int | None = None
    device_name: str | None = None
    error: str | None = None  # why identification failed
    cached: bool = False  # MCU taken from the mapping cache, not read from the target

    @property
    def mcu(self):
        return DEVICE_IDS.get(self.device_id)


def strip_ansi(text):
    return ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# STM32_Programmer_CLI
# ---------------------------------------------------------------------------

def _default_cli_dirs():
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        return [r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin",
                os.path.join(home, r"STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin")]
    if system == "Darwin":
        return ["/Applications/STM32CubeProgrammer.app/Contents/MacOs/bin",
                os.path.join(home, "Applications/STM32CubeProgrammer.app/Contents/MacOs/bin")]
    return [os.path.join(home, "STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin"),
            "/opt/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin"]


def find_cli(cli_arg=None):
    for path in (cli_arg, os.environ.get(CLI_ENV)):
        if path:
            if not (os.path.isfile(path) and os.access(path, os.X_OK)):
                raise StLinkError(f"{CLI_NAME} not found or not executable: {path}")
            return path
    path = shutil.which(CLI_NAME)
    if path:
        return path
    for d in _default_cli_dirs():
        for name in (CLI_NAME, CLI_NAME + ".exe"):
            path = os.path.join(d, name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    raise StLinkError(f"{CLI_NAME} not found: install STM32CubeProgrammer, or pass --cli / set ${CLI_ENV}")


def _run(cmd):
    """Run quietly, return (returncode, output without ANSI codes)."""
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, strip_ansi(r.stdout.decode(errors="replace"))


def connect_failed(rc, output):
    """True if a CLI run failed before it connected to the target: no Device ID printed, so nothing was done."""
    return DEVICE_ID_RE.search(output) is None and (rc != 0 or ERROR_RE.search(output) is not None)


def _retry_connect(run_once, label, attempts=None):
    """(rc, output) of run_once(), run again (up to CONNECT_ATTEMPTS times) while it fails before connecting.

    Connecting sometimes fails at random even under reset; a run that never connected is safe to repeat,
    whatever it was going to do (write, OTP, RDP)."""
    attempts = CONNECT_ATTEMPTS if attempts is None else attempts
    for attempt in range(1, attempts + 1):
        rc, out = run_once()
        if attempt == attempts or not connect_failed(rc, out):
            return rc, out
        print(f"[WARNING] {label} connect failed ({_last_error(out)}), retry {attempt}/{attempts - 1}", flush=True)
        time.sleep(CONNECT_RETRY_DELAY)


def _run_connect(cmd, sn, attempts=None):
    """_run() of a command that connects to the target, retried while the connection fails."""
    return _retry_connect(lambda: _run(cmd), f"ST-Link {sn}:", attempts)


def connect_args(sn, mode, freq=None):
    """-c connect arguments; freq in kHz, DEFAULT_FREQ when None."""
    args = ["-c", "port=SWD"]
    if sn is not None:
        args.append(f"sn={sn}")
    args.append(f"mode={mode}")
    if mode == "UR":
        args.append("reset=HWrst")
    elif mode == "NORMAL":
        args.append("reset=SWrst")
    args.append(f"freq={DEFAULT_FREQ if freq is None else freq}")
    return args


def parse_probe_list(output):
    """Probes from `STM32_Programmer_CLI --list st-link` output."""
    probes = []
    blocks = PROBE_RE.split(strip_ansi(output))[1:]
    for block in blocks:
        sn = PROBE_SN_RE.search(block)
        if not sn:
            continue
        board = BOARD_RE.search(block)
        probes.append(Probe(sn=sn.group(1), board=board.group(1) if board else None))
    return probes


def list_probes(cli):
    rc, out = _run([cli, "--list", "st-link"])
    probes = parse_probe_list(out)
    if rc != 0 and not probes:
        raise StLinkError(f"{CLI_NAME} --list failed (rc={rc}):\n{out.strip()}")
    return probes


def parse_device(output):
    """(device_id, device_name) from a connect output, None for what is missing."""
    output = strip_ansi(output)
    dev_id = DEVICE_ID_RE.search(output)
    name = DEVICE_NAME_RE.search(output)
    return (int(dev_id.group(1), 16) if dev_id else None,
            name.group(1) if name else None)


def _last_error(output):
    errors = [line.strip() for line in output.splitlines() if ERROR_RE.match(line)]
    return errors[-1] if errors else "no Device ID in output"


def identify(cli, probe, mode="UR", freq=None, *, hotplug=True):
    """Connect-only to find the MCU behind the probe: hot-plug first (no reset) unless `hotplug` is False,
    then `mode`. The last mode tried gets the connect retries."""
    modes = list(dict.fromkeys(("HOTPLUG", mode) if hotplug else (mode,)))
    for m in modes:
        rc, out = _run_connect([cli] + connect_args(probe.sn, m, freq), probe.sn, None if m == modes[-1] else 1)
        probe.device_id, probe.device_name = parse_device(out)
        if probe.device_id is not None:
            probe.error = None
            return probe
        probe.error = f"connect ({m}) failed: {_last_error(out)}"
    return probe


def _describe(probe):
    if probe.device_id is None:
        return f"{probe.sn} ({probe.error or 'not identified'})"
    return f"{probe.sn} (Device ID 0x{probe.device_id:03X} {probe.device_name or ''}".rstrip() + ")"


def resolve_probes(jobs, probes):
    """Fill in job.sn from identified probes and check that every SN is on the right MCU.

    Jobs with a given SN are checked first, so a wrong SN is reported as such rather than as a missing MCU.
    """
    by_sn = {p.sn: p for p in probes}
    taken = {j.sn for j in jobs if j.sn is not None}
    for job in sorted(jobs, key=lambda j: j.sn is None):
        low = job.mcu.lower()
        if job.sn is not None:
            probe = by_sn.get(job.sn)
            if probe is None:
                found = ", ".join(sorted(by_sn)) or "none"
                raise StLinkError(f"{job.mcu}: ST-Link {job.sn} is not connected (connected: {found})")
            if probe.mcu is None:
                raise StLinkError(f"{job.mcu}: cannot identify the MCU behind ST-Link {_describe(probe)}")
            if probe.mcu != job.mcu:
                raise StLinkError(f"--{low}-sn {job.sn} is connected to a {probe.mcu}, not a {job.mcu}: {_describe(probe)}")
            continue
        matches = [p for p in probes if p.mcu == job.mcu and p.sn not in taken]
        if len(matches) == 1:
            job.sn = matches[0].sn
            taken.add(job.sn)
            continue
        listing = "\n".join(f"  {_describe(p)}" for p in probes) or "  none"
        if not matches:
            raise StLinkError(f"{job.mcu}: no ST-Link connected to a {job.mcu} found. ST-Links:\n{listing}")
        raise StLinkError(f"{job.mcu}: several ST-Links are connected to a {job.mcu}, pick one with --{low}-sn:\n{listing}")
    return jobs


def _printable(text):
    """`text` with what stdout cannot encode replaced (the CLI's progress bar blocks on a cp1252 pipe)."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(enc, errors="replace").decode(enc)


def _stream(cmd, prefix):
    """Run the CLI once with output streamed under `prefix`; (rc, output lines)."""
    print(f"[INFO] {prefix} {' '.join(cmd)}")
    sys.stdout.flush()
    output = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        for raw in proc.stdout:
            # progress bars redraw with \r: keep what is left on screen
            line = strip_ansi(raw.decode(errors="replace")).rstrip("\r\n").split("\r")[-1]
            output.append(line)
            print(_printable(f"{prefix} {line}"))
            sys.stdout.flush()
    return proc.returncode, "\n".join(output)


def run_job(cmd, prefix, mcu=None):
    """Run the CLI with output streamed under `prefix`, again if it fails to connect. True on success.

    mcu: the MCU expected behind the ST-Link; MappingError if its Device ID says otherwise."""
    rc, output = _retry_connect(lambda: _stream(cmd, prefix), prefix)
    if mcu is not None:
        check_mcu(output, next((a[3:] for a in cmd if a.startswith("sn=")), "?"), mcu)
    output = output.splitlines()
    if rc != 0:
        print(f"[ERROR] {prefix} {CLI_NAME} exited with {rc}")
        return False
    errors = [line for line in output if ERROR_RE.match(line)]
    if errors:
        print(f"[ERROR] {prefix} {CLI_NAME} reported: {errors[-1].strip()}")
        return False
    return True


@dataclass
class Target:
    """An MCU to find, with its ST-Link serial if the user gave one."""
    mcu: str
    sn: str | None = None


def resolve(mcus, *, sns=None, cli=None, mode="UR", freq=None, hotplug=True, cache=None):
    """{mcu: Probe} for the given MCUs: lists and identifies the ST-Links, prints one line per ST-Link.

    sns: {mcu: serial} for MCUs whose ST-Link is given; the others are auto-detected (exactly one ST-Link must
    report that MCU). hotplug: as in identify(). Raises StLinkError.
    cache: mapping cache file. Its mapping is used without connecting to any target while the connected ST-Links are
    exactly the cached ones and agree with `sns`; those Probes are marked cached, and the caller must check the MCU
    on its first connect (check_mcu()) before anything that writes. A detection of all of MCUS is saved there.
    """
    cli = find_cli(cli)
    sns = sns or {}
    targets = [Target(mcu, sns.get(mcu)) for mcu in mcus]
    probes = list_probes(cli)
    if not probes:
        raise StLinkError("no ST-Link connected")
    cached = _from_cache(cache, mcus, sns, probes)
    if cached is not None:
        for mcu, probe in cached.items():
            print(f"[INFO] ST-Link {probe.sn} -> {mcu} (cached)")
        return cached
    explicit = {t.sn for t in targets if t.sn is not None}
    # with every SN given, only touch those probes; otherwise every probe is a candidate
    to_identify = probes if any(t.sn is None for t in targets) else [p for p in probes if p.sn in explicit]
    for probe in to_identify:
        identify(cli, probe, mode, freq, hotplug=hotplug)
        print(f"[INFO] ST-Link {_describe(probe)} -> {probe.mcu or '?'}")
    resolve_probes(targets, probes)
    by_sn = {p.sn: p for p in probes}
    result = {t.mcu: by_sn[t.sn] for t in targets}
    if cache and set(mcus) == set(MCUS):
        save_mapping(cache, result)
    return result


def reset(cli, sn, prefix, freq=None, mode="HOTPLUG", mcu=None):
    """Hardware reset (NRST) of the MCU behind ST-Link `sn`, output streamed under `prefix`. True on success.

    mode: how the CLI connects before the reset; "UR" holds NRST while connecting, for a target that
    hot-plug does not reach. mcu: the MCU expected there (MappingError if another one answers)."""
    return run_job([cli] + connect_args(sn, mode, freq) + ["-hardRst"], prefix, mcu=mcu)


# ---------------------------------------------------------------------------
# Mapping cache: which ST-Link is on which MCU, so a station does not connect to every ST-Link to find out.
# File: {"detected_at": "<local time>", "WLE": {"sn": "...", "device_id": 1175}, "WBA": {...}}
# ---------------------------------------------------------------------------

class MappingError(StLinkError):
    """An ST-Link answered with another MCU than expected, e.g. a cached mapping after the ST-Links were swapped."""


def load_mapping(path):
    """{mcu: serial} from the cache file, or None if there is none or it is unreadable."""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        mapping = {mcu: raw[mcu]["sn"] for mcu in MCUS if mcu in raw}
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not mapping or not all(isinstance(sn, str) and sn for sn in mapping.values()):
        return None
    return mapping


def save_mapping(path, probes):
    """Write {mcu: Probe} to the cache file."""
    data = {"detected_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    for mcu, probe in probes.items():
        data[mcu] = {"sn": probe.sn, "device_id": probe.device_id}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def forget_mapping(path):
    """Delete the cache file, so the next resolve() detects."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _from_cache(path, mcus, sns, probes):
    """{mcu: Probe} from the cache if it covers `mcus`, agrees with `sns` and its ST-Links are exactly the connected
    ones (an extra ST-Link may be another board's; detection would refuse that as ambiguous), else None."""
    mapping = load_mapping(path)
    if mapping is None or not set(mcus) <= set(mapping):
        return None
    if {p.sn for p in probes} != set(mapping.values()) or len(set(mapping.values())) != len(mapping):
        return None
    if any(sn != mapping.get(mcu) for mcu, sn in sns.items()):
        return None
    by_sn = {p.sn: p for p in probes}
    result = {}
    for mcu in mcus:
        probe = by_sn[mapping[mcu]]
        probe.cached = True
        result[mcu] = probe
    return result


def check_mcu(output, sn, mcu):
    """Raise MappingError if the CLI output's Device ID is not `mcu`'s (no Device ID: nothing to check)."""
    dev_id, _ = parse_device(output)
    if dev_id is None or DEVICE_IDS.get(dev_id) == mcu:
        return
    found = DEVICE_IDS.get(dev_id) or f"0x{dev_id:03X} device"
    raise MappingError(f"ST-Link {sn} is connected to a {found}, not the {mcu}")


# ---------------------------------------------------------------------------
# Memory, option bytes
# ---------------------------------------------------------------------------

RDP_LEVEL_0 = 0xAA
RDP_LEVEL_1 = 0xBB
RDP_RE = re.compile(r"^\s*RDP\s*:\s*0x([0-9A-Fa-f]+)", re.MULTILINE)
WBA_DEVICE_DB = "STM32_Prog_DB_0x492.xml"  # STM32WBA52/54/55
OTP_BLOCK_RE = re.compile(r'<Parameters\s+address="0x0BF90000"[^>]*>.*?<Alignment>\s*(0x[0-9A-Fa-f]+)\s*</Alignment>',
                          re.IGNORECASE | re.DOTALL)


def program(cli, sn, path, prefix, *, erase_pages=None, verify=True, mode="UR", freq=None):
    """Write a .hex file (it carries its addresses) in one CLI run, optionally erasing the given flash pages first,
    and verify it. Output streamed under `prefix`. True on success."""
    cmd = [cli] + connect_args(sn, mode, freq)
    if erase_pages:
        cmd += ["-e"] + [str(p) for p in erase_pages]
    cmd += ["-w", path]
    if verify:
        cmd.append("-v")
    return run_job(cmd, prefix)


def read_memory(cli, sn, address, size, *, mode="HOTPLUG", freq=None):
    """`size` bytes of target memory from `address` (e.g. the OTP area). Raises StLinkError."""
    with tempfile.TemporaryDirectory(prefix="stlink_") as tmp:
        path = os.path.join(tmp, "dump.bin")
        rc, out = _run_connect([cli] + connect_args(sn, mode, freq) + ["-u", f"0x{address:08X}", str(size), path], sn)
        if rc != 0 or ERROR_RE.search(out) or not os.path.isfile(path):
            raise StLinkError(f"reading 0x{address:08X}+{size} via ST-Link {sn} failed: {_last_error(out)}")
        with open(path, "rb") as f:
            data = f.read()
    if len(data) != size:
        raise StLinkError(f"reading 0x{address:08X}+{size} via ST-Link {sn}: got {len(data)} bytes")
    return data


def read_rdp(cli, sn, *, mode="HOTPLUG", freq=None, mcu=None):
    """The RDP option byte (0xAA = level 0, 0xBB = level 1, 0xCC = level 2). Raises StLinkError.

    mcu: the MCU expected behind the ST-Link; MappingError if its Device ID says otherwise."""
    rc, out = _run_connect([cli] + connect_args(sn, mode, freq) + ["-ob", "displ"], sn)
    if mcu is not None:
        check_mcu(out, sn, mcu)
    # a value printed by a run that failed is not trusted
    if ERROR_RE.search(out):
        raise StLinkError(f"cannot read the RDP option byte via ST-Link {sn}: {_last_error(out)}")
    if rc != 0:
        raise StLinkError(f"cannot read the RDP option byte via ST-Link {sn}: {CLI_NAME} exited with {rc}")
    m = RDP_RE.search(out)
    if m is None:
        raise StLinkError(f"cannot read the RDP option byte via ST-Link {sn}: no RDP line in the output")
    return int(m.group(1), 16)


def set_rdp(cli, sn, value, prefix, *, mode="UR", freq=None):
    """Program the RDP option byte (the MCU reloads its option bytes and resets). True if the CLI reports success;
    read the level back with read_rdp() to be sure."""
    return run_job([cli] + connect_args(sn, mode, freq) + ["-ob", f"RDP=0x{value:02X}"], prefix)


def otp_db_alignment(cli):
    """Write alignment of the WBA OTP block in CubeProgrammer's device database next to `cli`, or None if not found.

    The stock database says 0x4, which makes `-w` split OTP writes inside a 16-byte line and half-program it;
    OTP writes need 0x10."""
    cli_dir = os.path.dirname(os.path.abspath(cli))
    for db_dir in (os.path.join(cli_dir, "Data_Base"), os.path.join(cli_dir, "..", "Data_Base")):
        path = os.path.join(db_dir, WBA_DEVICE_DB)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                m = OTP_BLOCK_RE.search(f.read())
            return int(m.group(1), 16) if m else None
    return None
