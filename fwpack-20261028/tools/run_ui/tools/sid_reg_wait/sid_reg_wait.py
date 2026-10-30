#!/usr/bin/env python3
"""Reset the WLE and the WBA, then wait for the Sidewalk registration on the WBA log UART.

The device is on two ST-Links; the virtual COM port (VCP) of each one is wired to its MCU's log UART
(WBA USART1, WLE USART2, 115200 8N1). The tool
  1. finds which ST-Link is on which MCU (stflash's stlink module, like stflash itself, but connecting under reset
     only, no hot-plug attempt),
  2. finds each ST-Link's VCP by its USB serial number (= the ST-Link serial) and opens it,
  3. resets the WLE, then the WBA, through NRST (STM32_Programmer_CLI mode=UR -hardRst),
  4. prints both logs as [WBA-UART] / [WLE-UART] lines and passes on the first WBA line that matches --pass,
  5. checks from the boot logs that the resets came through NRST (see NrstCheck; --no-nrst-check skips it).

The default --pass matches both ways sid_smartac reports a registered device (app_sidewalk.c):
"Sidewalk Device Registration done" when it registers during this boot, "Registration status: registered"
at boot when it was registered before. Lines are matched without their ANSI color codes.

Exit code 0 on PASS; 1 on a --fail match, a timeout or a setup error ("[ERROR] ..." line).
Needs pyserial for the serial ports (pip install -r smac_tools/run_ui/requirements.txt).

Examples:
  sid_reg_wait.py
  sid_reg_wait.py --timeout 600 --wba-sn 0026003F3233511239363634
  sid_reg_wait.py --no-reset --wba-port /dev/ttyACM1 --no-wle-log

Python use (put smac_tools/run_ui/tools on sys.path or PYTHONPATH):
  import sid_reg_wait
  line = sid_reg_wait.wait_registration(timeout=300)     # raises sid_reg_wait.SidRegWaitError
"""

import argparse
import os
import queue
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)  # smac_tools/run_ui/tools: stflash is a sibling

try:
    from stflash import stlink  # noqa: E402
except ImportError:
    sys.path.insert(0, TOOLS)
    from stflash import stlink  # noqa: E402

DEFAULT_PASS = r"Sidewalk Device Registration done|Registration status: registered"
DEFAULT_TIMEOUT = 300  # s, 5 min
DEFAULT_BAUD = 115200
READ_TIMEOUT = 0.1  # s, serial read timeout, bounds how fast the readers notice a stop
RESET_ORDER = ("WLE", "WBA")
CONNECT_MODE = "UR"  # connect under reset for detection and resets: hot-plug sometimes fails to reach the MCU
NRST_CHECK_TIMEOUT = 10  # s after the resets for the boot logs to show them
WBA_RESET_REASON_RE = re.compile(r"Reset reason: (.+?) Reset\b")  # WBA bootloader, application_install_manager.c
WLE_BOOT_RE = re.compile(r"Application name:")  # first line of the WLE app's boot banner, app_freertos.c


class SidRegWaitError(Exception):
    pass


# ---------------------------------------------------------------------------
# Serial ports
# ---------------------------------------------------------------------------

def _pyserial():
    try:
        import serial
        import serial.tools.list_ports
    except ImportError:
        raise SidRegWaitError("pyserial is needed for the ST-Link serial ports: pip install pyserial")
    return serial


def list_ports():
    """The serial ports pyserial sees (objects with .device and .serial_number)."""
    return list(_pyserial().tools.list_ports.comports())


def open_port(device, baud):
    """Open a serial port for reading (8N1, short read timeout)."""
    serial = _pyserial()
    try:
        port = serial.Serial(device, baud, timeout=READ_TIMEOUT)
    except serial.SerialException as e:
        raise SidRegWaitError(f"cannot open {device}: {e}")
    try:
        port.reset_input_buffer()
    except Exception as e:  # SerialException, or termios.error on POSIX, which pyserial does not wrap
        try:
            port.close()
        except Exception:
            pass
        raise SidRegWaitError(f"cannot flush {device}: {e}")
    return port


def find_port(mcu, sn, ports):
    """Device name of the virtual COM port of ST-Link `sn` among `ports`. Raises SidRegWaitError."""
    matches = [p.device for p in ports if (getattr(p, "serial_number", None) or "").upper() == sn.upper()]
    if len(matches) == 1:
        return matches[0]
    usb = [p for p in ports if getattr(p, "serial_number", None)]  # skip built-in ports (no USB serial number)
    listing = "\n".join(f"  {p.device}  serial={p.serial_number}" for p in usb) or "  none with a USB serial number"
    if not matches:
        raise SidRegWaitError(f"{mcu}: no serial port of ST-Link {sn} found, give --{mcu.lower()}-port. Ports:\n{listing}")
    raise SidRegWaitError(f"{mcu}: ST-Link {sn} has several serial ports ({', '.join(matches)}), "
                          f"pick one with --{mcu.lower()}-port")


# ---------------------------------------------------------------------------
# NRST check
# ---------------------------------------------------------------------------

class NrstCheck:
    """Checks from the boot logs that the NRST resets reached the MCUs (the ST-Link's NRST is wired).

    WBA: its bootloader must report "Reset reason: External NRST Reset"; another reason (e.g. Software) means the
    MCU was reset some other way. WLE: its boot banner must appear; a WLE log that stays silent (a build without
    logs) is only a warning, one that prints without the banner means the WLE did not reboot.
    feed() every log line after the resets; arm() starts the NRST_CHECK_TIMEOUT window, expire() ends it.
    """

    def __init__(self, mcus):
        self.pending = set(mcus)
        self.heard = set()  # MCUs that printed anything
        self.deadline = None

    def arm(self):
        self.deadline = time.monotonic() + NRST_CHECK_TIMEOUT

    def feed(self, mcu, line):
        """Raises SidRegWaitError if the WBA reports a reset other than NRST."""
        self.heard.add(mcu)
        if mcu not in self.pending:
            return
        if mcu == "WBA":
            m = WBA_RESET_REASON_RE.search(line)
            if m is None:
                return
            if m.group(1) != "External NRST":
                raise SidRegWaitError(f"NRST check: the WBA reports a {m.group(1)} reset, not External NRST: "
                                      f"check that the WBA ST-Link's NRST is wired to the WBA")
            print("[INFO] NRST check: WBA reset reason External NRST", flush=True)
        else:
            if not WLE_BOOT_RE.search(line):
                return
            print("[INFO] NRST check: WLE rebooted", flush=True)
        self.pending.discard(mcu)

    def expire(self):
        """End of the window: raises SidRegWaitError for an MCU that did not show its NRST reset."""
        pending, self.pending = sorted(self.pending), set()
        for mcu in pending:
            if mcu == "WLE" and mcu not in self.heard:
                print(f"[WARNING] NRST check: the WLE log stayed silent for {NRST_CHECK_TIMEOUT:g} s, "
                      f"its reset is not checked", flush=True)
                continue
            what = "reset reason" if mcu == "WBA" else "boot banner"
            raise SidRegWaitError(f"NRST check: no {mcu} {what} within {NRST_CHECK_TIMEOUT:g} s of its reset"
                                  f"{'' if mcu in self.heard else ' (its log stayed silent)'}: "
                                  f"check that the {mcu} ST-Link's NRST is wired to the {mcu}")


# ---------------------------------------------------------------------------
# Reading the logs
# ---------------------------------------------------------------------------

def _reader(mcu, port, q, stop):
    """Post (mcu, line) for every complete line read from `port`, ("error", text) if the port fails."""
    buf = b""
    try:
        while not stop.is_set():
            data = port.read(256)
            if not data:
                continue
            buf += data
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                q.put((mcu, stlink.strip_ansi(raw.decode(errors="replace")).rstrip("\r")))
    except Exception as e:  # a VCP that disappears raises SerialException / OSError
        if not stop.is_set():
            q.put(("error", f"{mcu} serial port: {e}"))


class _LogStream:
    """Reader threads for the log ports; next_line() hands out (mcu, line) and prints it as [<MCU>-UART] ....

    With an NrstCheck, every line goes through it, and its window ends (expire()) while lines are being read."""

    def __init__(self, ports, check=None):
        self.check = check
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.threads = [threading.Thread(target=_reader, args=(mcu, port, self.q, self.stop), daemon=True)
                        for mcu, port in ports.items()]
        for t in self.threads:
            t.start()

    def _check_open(self):
        return self.check is not None and self.check.pending and self.check.deadline is not None

    def next_line(self, deadline):
        """(mcu, line) of the next line, or None when the deadline passed. Raises SidRegWaitError if a port fails
        or the NRST check fails."""
        while True:
            now = time.monotonic()
            if self._check_open() and now >= self.check.deadline:
                self.check.expire()
            if now >= deadline:
                return None
            limit = min(deadline, self.check.deadline) if self._check_open() else deadline
            try:
                source, line = self.q.get(timeout=min(max(limit - now, 0.001), 0.5))
            except queue.Empty:
                continue
            if source == "error":
                raise SidRegWaitError(line)
            print(f"[{source}-UART] {line}", flush=True)
            if self.check is not None:
                self.check.feed(source, line)
            return source, line

    def settle(self):
        """Read on (printing) until the NRST check has its answer; returns the lines read."""
        lines = []
        while self._check_open():
            got = self.next_line(self.check.deadline)
            if got is not None:
                lines.append(got)
        return lines

    def close(self):
        self.stop.set()
        for t in self.threads:
            t.join(timeout=1)


def watch(ports, pass_re, fail_re=None, timeout=DEFAULT_TIMEOUT, start=None, check=None):
    """Print the lines of every port until a WBA line matches pass_re (returns it) or fail_re / timeout (raises).

    ports: {mcu: port} with a read(n) -> bytes method (pyserial Serial or a test double). Reader threads are
    started here; start() (e.g. the resets) runs once they read, so no output is missed. check: an NrstCheck,
    armed after start(); the pass line is returned once it has its answer.
    """
    stream = _LogStream(ports, check)
    try:
        if start is not None:
            start()
        if check is not None:
            check.arm()
        print(f"[INFO] Waiting up to {timeout:g} s for a WBA line matching: {pass_re.pattern}", flush=True)
        deadline = time.monotonic() + timeout
        while True:
            got = stream.next_line(deadline)
            if got is None:
                raise SidRegWaitError(f"timeout after {timeout:g} s waiting for: {pass_re.pattern}")
            source, line = got
            if source != "WBA":
                continue
            if fail_re is not None and fail_re.search(line):
                raise SidRegWaitError(f"FAIL: {line}")
            if pass_re.search(line):
                stream.settle()
                return line
    finally:
        stream.close()


def collect(ports, until_re, timeout, after=0.0, start=None, check=None):
    """Print and return the lines of every port, as [(mcu, line)], up to the first WBA line matching until_re,
    plus `after` more seconds of lines. Raises SidRegWaitError if no WBA line matches within `timeout`.

    Like watch(), start() runs once the readers are going, and `check` is an NrstCheck armed after it.
    """
    stream = _LogStream(ports, check)
    lines = []
    try:
        if start is not None:
            start()
        if check is not None:
            check.arm()
        deadline = time.monotonic() + timeout
        while True:
            got = stream.next_line(deadline)
            if got is None:
                raise SidRegWaitError(f"timeout after {timeout:g} s waiting for: {until_re.pattern}")
            lines.append(got)
            if got[0] == "WBA" and until_re.search(got[1]):
                break
        deadline = time.monotonic() + after
        while (got := stream.next_line(deadline)) is not None:
            lines.append(got)
        return lines + stream.settle()
    finally:
        stream.close()


def reset_device(cli, probes, freq=None, mode=CONNECT_MODE):
    """NRST reset of the WLE, then the WBA, connecting in `mode` (under reset by default). Raises SidRegWaitError
    if one fails, stlink.MappingError if another MCU than expected answers on an ST-Link."""
    for mcu in RESET_ORDER:
        if not stlink.reset(cli, probes[mcu].sn, f"[{mcu}]", freq, mode=mode, mcu=mcu):
            raise SidRegWaitError(f"{mcu} reset failed")


def port_devices(probes, wba_port=None, wle_port=None, wle_log=True, list_ports=list_ports):
    """{mcu: serial device} for the logs: given ports as they are, the others found by their ST-Link serial.

    A missing WBA port raises SidRegWaitError; a missing WLE port only prints a warning (the WLE log is optional)."""
    devices = {}
    available = None
    for mcu, given, wanted in (("WBA", wba_port, True), ("WLE", wle_port, wle_log)):
        if not wanted:
            continue
        if given is not None:
            devices[mcu] = given
            continue
        available = list_ports() if available is None else available
        try:
            devices[mcu] = find_port(mcu, probes[mcu].sn, available)
        except SidRegWaitError as e:
            if mcu == "WBA":
                raise
            print(f"[WARNING] WLE log not shown: {e}")
    return devices


def open_logs(devices, baud=DEFAULT_BAUD, open_port=open_port):
    """Open the log ports ({mcu: device} -> {mcu: port}); closes what it opened if one fails."""
    ports = {}
    try:
        for mcu, device in devices.items():
            ports[mcu] = open_port(device, baud)
            print(f"[INFO] {mcu} log: {device} at {baud} baud")
    except BaseException:
        close_logs(ports)
        raise
    return ports


def close_logs(ports):
    for port in ports.values():
        try:
            port.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _regex(pattern, name):
    try:
        return re.compile(pattern)
    except re.error as e:
        raise SidRegWaitError(f"--{name}: bad regex {pattern!r}: {e}")


def wait_registration(timeout=DEFAULT_TIMEOUT, pass_re=DEFAULT_PASS, fail_re=None, *, wle_sn=None, wba_sn=None,
                      wba_port=None, wle_port=None, wle_log=True, reset=True, nrst_check=True, baud=DEFAULT_BAUD,
                      cli=None, freq=None, stlink_cache=None, rescan=False, list_ports=list_ports,
                      open_port=open_port):
    """Reset the device and wait for the Sidewalk registration; returns the matching WBA line.

    Prints the same log as the CLI. Raises SidRegWaitError on a fail match, a timeout or a setup problem
    (stlink.StLinkError from ST-Link detection is passed through as SidRegWaitError).
    stlink_cache: ST-Link mapping cache file (stlink.resolve()), used when resetting: each reset checks the MCU
    behind its ST-Link, and a wrong cached mapping is forgotten and detected again once. rescan: forget it first.
    list_ports / open_port: pyserial by default; replaceable, e.g. in tests.
    """
    pass_re = _regex(pass_re, "pass")
    fail_re = _regex(fail_re, "fail") if fail_re else None
    if timeout <= 0:
        raise SidRegWaitError("--timeout must be positive")
    cache = stlink_cache if reset else None  # without the resets nothing would check a cached mapping
    if cache and rescan:
        stlink.forget_mapping(cache)

    def attempt():
        return _wait_once(timeout, pass_re, fail_re, wle_sn, wba_sn, wba_port, wle_port, wle_log, reset, nrst_check,
                          baud, cli, freq, cache, list_ports, open_port)

    try:
        return attempt()
    except stlink.MappingError as e:
        if not cache:
            raise SidRegWaitError(str(e))
        print(f"[WARNING] {e}: the cached ST-Link mapping is wrong, detecting the ST-Links again", flush=True)
        stlink.forget_mapping(cache)
    try:
        return attempt()
    except stlink.MappingError as e:
        raise SidRegWaitError(str(e))


def _wait_once(timeout, pass_re, fail_re, wle_sn, wba_sn, wba_port, wle_port, wle_log, reset, nrst_check, baud, cli,
               freq, cache, list_ports, open_port):
    """One wait_registration() run; stlink.MappingError when a reset finds another MCU than the mapping says."""
    # which MCUs need their ST-Link: both for the reset, otherwise those whose port is to be found
    need = set(RESET_ORDER) if reset else {m for m, p, on in (("WBA", wba_port, True), ("WLE", wle_port, wle_log))
                                           if on and p is None}
    probes, cli_path = {}, None
    if need:
        try:
            cli_path = stlink.find_cli(cli)
            mcus = [m for m in RESET_ORDER if m in need]
            probes = stlink.resolve(mcus, sns={m: s for m, s in (("WLE", wle_sn), ("WBA", wba_sn)) if s and m in need},
                                    cli=cli_path, mode=CONNECT_MODE, freq=freq, hotplug=False, cache=cache)
        except stlink.StLinkError as e:
            raise SidRegWaitError(str(e))

    devices = port_devices(probes, wba_port, wle_port, wle_log, list_ports)
    ports = open_logs(devices, baud, open_port)

    def do_reset():
        reset_device(cli_path, probes, freq)

    check = NrstCheck(ports) if reset and nrst_check else None
    try:
        return watch(ports, pass_re, fail_re, timeout, start=do_reset if reset else None, check=check)
    finally:
        close_logs(ports)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="S",
                   help=f"seconds to wait after the reset (default: {DEFAULT_TIMEOUT})")
    p.add_argument("--pass", dest="pass_re", default=DEFAULT_PASS, metavar="REGEX",
                   help=f"WBA line that means registered (default: {DEFAULT_PASS!r})")
    p.add_argument("--fail", dest="fail_re", metavar="REGEX", help="WBA line that means failed (default: none)")
    p.add_argument("--wle-sn", metavar="SN", help="ST-Link serial of the WLE (default: auto-detect)")
    p.add_argument("--wba-sn", metavar="SN", help="ST-Link serial of the WBA (default: auto-detect)")
    p.add_argument("--wba-port", metavar="PORT", help="WBA log serial port (default: the WBA ST-Link's VCP)")
    p.add_argument("--wle-port", metavar="PORT", help="WLE log serial port (default: the WLE ST-Link's VCP)")
    p.add_argument("--no-wle-log", action="store_true", help="do not open the WLE log port")
    p.add_argument("--no-reset", action="store_true", help="do not reset, only wait")
    p.add_argument("--no-nrst-check", action="store_true",
                   help="do not check from the boot logs that the resets came through NRST")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"log baud rate (default: {DEFAULT_BAUD})")
    p.add_argument("--stlink-cache", metavar="FILE",
                   help="ST-Link -> MCU mapping cache: reused while the same ST-Links are connected (default: none, "
                        "always detect)")
    p.add_argument("--rescan", action="store_true", help="forget the --stlink-cache mapping and detect the ST-Links")
    p.add_argument("--cli", metavar="PATH", help=f"path to {stlink.CLI_NAME}")
    p.add_argument("--freq", type=int, metavar="KHZ", help=f"SWD frequency in kHz (default: {stlink.DEFAULT_FREQ})")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        line = wait_registration(timeout=args.timeout, pass_re=args.pass_re, fail_re=args.fail_re,
                                 wle_sn=args.wle_sn, wba_sn=args.wba_sn, wba_port=args.wba_port,
                                 wle_port=args.wle_port, wle_log=not args.no_wle_log, reset=not args.no_reset,
                                 nrst_check=not args.no_nrst_check, baud=args.baud, cli=args.cli, freq=args.freq,
                                 stlink_cache=args.stlink_cache, rescan=args.rescan)
    except SidRegWaitError as e:
        print(f"[ERROR] {e}", flush=True)
        return 1
    print(f"[INFO] PASS: {line}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted")
        sys.exit(130)
