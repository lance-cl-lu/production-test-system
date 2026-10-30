#!/usr/bin/env python3
"""SID secure programming: static WLE/WBA images, the sign key in WBA OTP, RDP level 1 on both MCUs.

For a sid_smartac device on two ST-Links whose virtual COM ports carry the WBA / WLE log UARTs:
  1. offline checks: merge each MCU's bootloader + app into one image (combine_binaries), check the images, the
     sign key, the external-flash (SPI NOR) factory image (its SID container version must be WBA + WLE app
     version, its WLE app's hardware version that of the WLE app) and CubeProgrammer OTP support
  2. find the ST-Links; both MCUs must still be at RDP level 0
  3. WLE: erase pages 0..124 (keeps NVM_STORAGE and the SMAC mfg data), write + verify the WLE image
  4. WBA: merge the image with the confirmed app validity marker and the bootloader metadata (installed container
     version, app implementation SID; wba_confirm), erase pages 0..116 (keeps LITTLE_FS = the Sidewalk
     registration, SNVMA, MFG_DATA), write + verify
  5. reset, read the WBA boot log: SIGN KEY not installed (or already the given key), FACTORY SID/GEN2 SIGN equal
     to the signatures in the external-flash image, app VALID
  6. write the key record into the first free WBA OTP slots and read it back (skipped if already there)
  7. reset, read the boot log again: SIGN KEY = the key, "Sign check OK", no [ERROR]/[WARNING] in the bootloader
     part, then --app-window seconds of app log without [ERROR], ASSERT, FATAL or Hard Fault
  8. RDP level 1 on the WLE, then the WBA, read back
Steps 6 and 8 cannot be undone (OTP is write-once; RDP 1 -> 0 mass-erases the flash), so they only run once every
earlier step passed. Exit code 0 on success; 1 with an "[ERROR] ..." line otherwise.

Needs pyserial and PyNaCl (pip install -r smac_tools/run_ui/requirements.txt) and STM32CubeProgrammer whose WBA OTP
write alignment is patched to 0x10 (see README.md).

Example:
  sid_secure_prog.py --wle-boot wle_boot.hex --wle-app wle_app.hex --wba-boot wba_boot.hex --wba-app wba_app.hex \\
                     --sign-key sign_key_pub.pem --ext-flash spi_flash_factory.bin

Python use (put smac_tools/run_ui/tools on sys.path or PYTHONPATH):
  import sid_secure_prog
  result = sid_secure_prog.program("wle_boot.hex", "wle_app.hex", "wba_boot.hex", "wba_app.hex",
                                   "sign_key_pub.pem", "spi_flash_factory.bin")
"""

import argparse
import os
import re
import struct
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)  # smac_tools/run_ui/tools
SMAC_TOOLS = os.path.normpath(os.path.join(TOOLS, "..", ".."))
for _path in (TOOLS, os.path.join(SMAC_TOOLS, "signing"), os.path.join(SMAC_TOOLS, "container")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import combine_binaries  # noqa: E402  (tools/combine_binaries: bootloader + app -> one image)
import sid_reg_wait  # noqa: E402  (tools/sid_reg_wait: log ports)
import sign_key  # noqa: E402  (smac_tools/signing: key files, OTP record)
import spi_flash_image  # noqa: E402  (smac_tools/container: SPI NOR image, factory containers)
import wba_confirm  # noqa: E402  (tools/wba_confirm: hex reading, confirmed validity marker)
from stflash import stlink  # noqa: E402

STEPS = 8

# WLE (STM32WLE5CCUX_FLASH.ld): 2 KB pages; NVM_STORAGE at 0x0803E800 and PERMANENT_DATA (SMAC mfg data) are kept
WLE_FLASH = 0x08000000
WLE_PAGE = 0x800
WLE_KEEP_FROM = 0x0803E800
# WBA (STM32WBA5xxG_Sidewalk_OTA.ld): 8 KB pages; LITTLE_FS at 0x080EA000, SNVMA and MFG_DATA are kept
WBA_FLASH = 0x08000000
WBA_PAGE = 0x2000
WBA_KEEP_FROM = 0x080EA000

# WLE app info block (fw_tools.c) at the start of the WLE app; the same bytes start the WLx image of a container
WLE_APP = 0x08008800
WLE_INFO_MAGIC = 0xC0FEB00B
WLE_INFO_VERHW_OFFSET = 37  # verhw = SMAC_HW_VERSION, major<<16 | minor<<8 | patch
WLE_INFO_SIZE = WLE_INFO_VERHW_OFFSET + 4

WLE_ERASE_PAGES = range(0, (WLE_KEEP_FROM - WLE_FLASH) // WLE_PAGE)  # 0..124
WBA_ERASE_PAGES = range(0, (WBA_KEEP_FROM - WBA_FLASH) // WBA_PAGE)  # 0..116

APP_HEADER = wba_confirm.APP_HEADER  # footer ptr, validity marker ptr
WBA_FOOTER_SIZE = sign_key.WBA_FOOTER_SIZE
CONFIRMED_MARKER = wba_confirm.CONFIRMED_MARKER
FLASH_WORD = wba_confirm.FLASH_WORD
memory = wba_confirm.memory
covered = wba_confirm.covered

OTP_DB_ALIGNMENT = 0x10
DEFAULT_APP_WINDOW = 10.0  # s
DEFAULT_BOOT_TIMEOUT = 30.0  # s

# boot log, with the ANSI codes already stripped: "[<ms>][<LEVEL>]: <message>"
LOG_RE = re.compile(r"^\[\d+\]\[([A-Z]+)\]:\s?(.*)$")
BOOT_BANNER_RE = re.compile(r"AIM version")
APP_START_RE = re.compile(r"Starting user application")
SIGN_KEY_RE = re.compile(r"^SIGN KEY: (.+?)\s*$")
FACTORY_RE = re.compile(r"^FACTORY (SID|GEN2) SIGN: ([0-9A-Fa-f]+)\s*$")
META_APP_RE = re.compile(r"^META APP: state=(\d+)")
APP_VALID = 1
APP_ISSUE_RE = re.compile(r"\[ERROR\]|ASSERT|FATAL|Hard Fault")


class SidSecureProgError(Exception):
    pass


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def read_hex(path):
    """Data of an Intel HEX file as sorted, merged [(start, bytes)]. Raises SidSecureProgError."""
    try:
        return wba_confirm.read_hex(path)
    except wba_confirm.WbaConfirmError as e:
        raise SidSecureProgError(str(e))


def check_range(name, segments, lo, hi):
    if not segments:
        raise SidSecureProgError(f"{name}: no data")
    for start, data in segments:
        end = start + len(data)
        if start < lo or end > hi:
            raise SidSecureProgError(f"{name}: data at 0x{start:08X}..0x{end - 1:08X} is outside "
                                     f"0x{lo:08X}..0x{hi - 1:08X} (the area this station erases)")


def check_wba_image(segments, pub):
    """The WBA app's validity-marker address, after checking the image layout and the app signature."""
    check_range("WBA image", segments, WBA_FLASH, WBA_KEEP_FROM)
    if not covered(segments, WBA_FLASH, 4):
        raise SidSecureProgError("WBA image: no bootloader at 0x08000000 (expected bootloader + app)")
    if not covered(segments, APP_HEADER, 8):
        raise SidSecureProgError(f"WBA image: no app OTA header at 0x{APP_HEADER:08X}")
    footer, _marker = struct.unpack("<II", memory(segments, APP_HEADER, 8))

    app_size = footer + WBA_FOOTER_SIZE - sign_key.WBA_APP_FLASH_BASE
    if not 0 < app_size <= WBA_KEEP_FROM - sign_key.WBA_APP_FLASH_BASE:
        raise SidSecureProgError(f"WBA image: app footer address 0x{footer:08X} is outside the app area")
    try:
        if not sign_key.verify_wba_image(memory(segments, sign_key.WBA_APP_FLASH_BASE, app_size), pub):
            raise SidSecureProgError(f"WBA image: the app is NOT signed with {sign_key.describe_key(pub)}; with RDP "
                                     f"level 1 the bootloader would refuse to start it")
    except ValueError as e:
        raise SidSecureProgError(f"WBA image: {e}")

    try:
        return wba_confirm.marker_address(segments, limit=WBA_KEEP_FROM)  # inside the area this station erases
    except wba_confirm.WbaConfirmError as e:
        raise SidSecureProgError(f"WBA image: {e}")


def load_key(value):
    """Ed25519 public key from a key file (ST PEM with a public block) or 64 hex digits."""
    if os.path.isfile(value):
        try:
            return sign_key.load_public_key(value)
        except (sign_key.SignKeyError, ValueError, ImportError) as e:
            raise SidSecureProgError(f"--sign-key {value}: {e}")
    if re.fullmatch(r"[0-9A-Fa-f]{64}", value):
        return bytes.fromhex(value)
    raise SidSecureProgError(f"--sign-key: {value!r} is neither a key file nor 64 hex digits")


def factory_signatures(path, pub):
    """{"SID": sig, "GEN2": sig} of the factory containers in the SPI NOR image, after checking them with pub."""
    try:
        image = Path(path).read_bytes()
    except OSError as e:
        raise SidSecureProgError(f"--ext-flash: cannot read {path}: {e.strerror}")
    signatures = {}
    for slot in spi_flash_image.FACTORY_SLOTS:
        offset = spi_flash_image.SLOT_OFFSETS[slot]
        data = image[offset:offset + spi_flash_image.SLOT_SIZE]
        try:
            container = spi_flash_image.check_container(data, slot)
            spi_flash_image.verify_signatures(data, container, pub)
        except spi_flash_image.InputError as e:
            raise SidSecureProgError(f"--ext-flash: {slot} factory container: {e}")
        signatures[slot] = container["signature"].hex().upper()
    return signatures


def write_hex(path, address, data):
    spi_flash_image.write_intel_hex(path, address, data)


def factory_versions(path):
    """{"SID": version, "GEN2": version} of the factory containers in the SPI NOR image (already checked)."""
    image = Path(path).read_bytes()
    return {slot: spi_flash_image.parse_container(image[spi_flash_image.SLOT_OFFSETS[slot]:])["version"]
            for slot in spi_flash_image.FACTORY_SLOTS}


def hw_version_str(verhw):
    """SMAC_HW_VERSION (major<<16 | minor<<8 | patch) as "major.minor.patch"."""
    return f"{(verhw >> 16) & 0xFF}.{(verhw >> 8) & 0xFF}.{verhw & 0xFF}"


def wle_hw_version(info, what):
    """verhw from the first WLE_INFO_SIZE bytes of a WLE app (its info block)."""
    if len(info) < WLE_INFO_SIZE:
        raise SidSecureProgError(f"{what}: too short for the WLE app info block ({len(info)} bytes)")
    magic, = struct.unpack_from("<I", info, 0)
    if magic != WLE_INFO_MAGIC:
        raise SidSecureProgError(f"{what}: no WLE app info block (magic 0x{magic:08X}, expected "
                                 f"0x{WLE_INFO_MAGIC:08X})")
    return struct.unpack_from("<I", info, WLE_INFO_VERHW_OFFSET)[0]


def factory_wle_hw_version(path, slot="SID"):
    """verhw of the WLE app in a factory container of the SPI NOR image (already checked)."""
    data = Path(path).read_bytes()[spi_flash_image.SLOT_OFFSETS[slot]:]
    container = spi_flash_image.parse_container(data)
    for name, offset, size in container["images"]:
        if name == "WLx":
            return wle_hw_version(data[offset:offset + min(size, WLE_INFO_SIZE)],
                                  f"--ext-flash: {slot} factory container's WLE image")
    raise SidSecureProgError(f"--ext-flash: the {slot} factory container has no WLE image")


def merge_marker(wba_hex, out_dir, wle_hex):
    """The WBA image merged with the confirmed validity marker and the bootloader metadata for wle_hex (wba_confirm,
    one file, one write)."""
    out = os.path.join(out_dir, "wba_confirmed.hex")
    try:
        wba_confirm.confirm(wba_hex, out, limit=WBA_KEEP_FROM, wle_hex=wle_hex)
    except wba_confirm.WbaConfirmError as e:
        raise SidSecureProgError(f"WBA image: {e}")
    return out


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------

def free_otp_slot(dump):
    """Index of the first run of free (all 0xFF) slots big enough for the key record, or None."""
    size, count = sign_key.OTP_SLOT_SIZE, sign_key.OTP_SLOTS
    free = [dump[i:i + size] == b"\xff" * size for i in range(0, len(dump), size)]
    return next((i for i in range(len(free) - count + 1) if all(free[i:i + count])), None)


def otp_plan(dump, pub):
    """None if the key is already in OTP, else the slot to write it to. Raises SidSecureProgError."""
    status, key = sign_key.parse_otp(dump)
    if status == sign_key.OTP_OK:
        if key == pub:
            return None
        raise SidSecureProgError(f"OTP already holds another key: {sign_key.describe_key(key)} (OTP cannot be erased)")
    if status == sign_key.OTP_INVALID:
        raise SidSecureProgError("OTP holds an invalid key record; the bootloader would refuse every image")
    slot = free_otp_slot(dump)
    if slot is None:
        raise SidSecureProgError(f"no {sign_key.OTP_SLOTS} free consecutive OTP slots left")
    return slot


# ---------------------------------------------------------------------------
# Boot log
# ---------------------------------------------------------------------------

def parse_log_line(line):
    """(level or None, message) of a log line without ANSI codes."""
    m = LOG_RE.match(line)
    return (m.group(1), m.group(2)) if m else (None, line)


def boot_sections(lines):
    """(bootloader lines, app lines) of the last boot in collected [(mcu, line)]; WBA lines only."""
    wba = [line for mcu, line in lines if mcu == "WBA"]
    start = next((i for i in range(len(wba) - 1, -1, -1) if APP_START_RE.search(wba[i])), None)
    if start is None:
        raise SidSecureProgError("the bootloader did not start the app (no 'Starting user application' line)")
    banner = next((i for i in range(start, -1, -1) if BOOT_BANNER_RE.search(wba[i])), None)
    if banner is None:
        raise SidSecureProgError("bootloader banner ('AIM version') not seen: the boot log is incomplete")
    return wba[banner:start + 1], wba[start + 1:]


def check_boot(lines, pub, factory, *, provisioned):
    """Check one boot's log. provisioned=False: before OTP (key may be missing); True: the final check.

    Returns the SIGN KEY value the bootloader reported. Raises SidSecureProgError."""
    boot, app = boot_sections(lines)
    messages = [parse_log_line(line) for line in boot]
    expected_key = pub.hex().upper()

    keys = [m.group(1) for _, msg in messages if (m := SIGN_KEY_RE.match(msg))]
    if len(keys) != 1:
        raise SidSecureProgError(f"expected one 'SIGN KEY' line in the boot log, got {len(keys)}")
    key = keys[0].upper() if re.fullmatch(r"[0-9A-Fa-f]{64}", keys[0]) else keys[0]
    allowed = (expected_key,) if provisioned else (expected_key, "not installed")
    if key not in allowed:
        raise SidSecureProgError(f"bootloader reports SIGN KEY: {key}, expected {' or '.join(allowed)}")

    reported = {m.group(1): m.group(2).upper() for _, msg in messages if (m := FACTORY_RE.match(msg))}
    for slot, signature in factory.items():
        if slot not in reported:
            raise SidSecureProgError(f"no 'FACTORY {slot} SIGN' line in the boot log")
        if reported[slot] != signature:
            raise SidSecureProgError(f"FACTORY {slot} SIGN differs from the external-flash image: the device has "
                                     f"{reported[slot][:16]}..., the image {signature[:16]}...")

    states = [int(m.group(1)) for _, msg in messages if (m := META_APP_RE.match(msg))]
    if states != [APP_VALID]:
        raise SidSecureProgError(f"app state is {states or 'not reported'}, expected {APP_VALID} (VALID): the "
                                 f"validity marker did not take")

    if provisioned:
        checks = [msg for _, msg in messages if msg.startswith("Sign check")]
        if checks != ["Sign check OK"]:
            raise SidSecureProgError(f"expected exactly one 'Sign check OK', got {checks or 'none'}")
        issues = [line for line, (level, _) in zip(boot, messages) if level in ("ERROR", "WARNING")]
        if issues:
            raise SidSecureProgError(f"bootloader reported: {issues[0]}")
        app_issues = [line for line in app if APP_ISSUE_RE.search(line)]
        if app_issues:
            raise SidSecureProgError(f"app reported: {app_issues[0]}")
    return key


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _step(n, title):
    print(f"[INFO] [STEP {n}/{STEPS}] {title}", flush=True)


def combine_image(mcu, boot, app, out):
    """Merge an MCU's bootloader and app into one Intel HEX (combine_binaries), print its memory map."""
    low = mcu.lower()
    try:
        text = combine_binaries.combine(combine_binaries.parse_inputs([boot, app]), Path(out))
    except combine_binaries.InputError as e:
        raise SidSecureProgError(f"--{low}-boot/--{low}-app: {e}")
    print(f"[INFO] {mcu} image: {os.path.basename(boot)} + {os.path.basename(app)}")
    combine_binaries.print_memory_map(text)
    return out


def offline_checks(wle_boot, wle_app, wba_boot, wba_app, key, ext_flash, cli, work_dir):
    """Everything that needs no hardware. Merges each MCU's bootloader + app into work_dir.

    Returns (pub, marker, factory signatures, cli path, WLE image, WBA image)."""
    files = (("--wle-boot", wle_boot), ("--wle-app", wle_app), ("--wba-boot", wba_boot), ("--wba-app", wba_app))
    for opt, path in files + (("--ext-flash", ext_flash),):
        if not os.path.isfile(path):
            raise SidSecureProgError(f"{opt}: no such file: {path}")
    for opt, path in files:
        if not path.lower().endswith((".hex", ".ihex", ".elf")):
            raise SidSecureProgError(f"{opt}: must be Intel HEX (.hex) or ELF (.elf): {path}")

    pub = load_key(key)
    print(f"[INFO] Sign key: {sign_key.describe_key(pub)}")
    wle_hex = combine_image("WLE", wle_boot, wle_app, os.path.join(work_dir, "wle.hex"))
    wba_hex = combine_image("WBA", wba_boot, wba_app, os.path.join(work_dir, "wba.hex"))
    check_range("WLE image", read_hex(wle_hex), WLE_FLASH, WLE_KEEP_FROM)
    marker = check_wba_image(read_hex(wba_hex), pub)
    print(f"[INFO] WBA app signed with the key; validity marker at 0x{marker:08X}")
    factory = factory_signatures(ext_flash, pub)
    versions = factory_versions(ext_flash)
    for slot, signature in factory.items():
        print(f"[INFO] Factory {slot} container OK, version 0x{versions[slot]:08X}, signature {signature[:16]}...")
    wba_segments, wle_segments = read_hex(wba_hex), read_hex(wle_hex)
    try:
        wba_confirm.metadata(wba_segments, wle_segments, limit=WBA_KEEP_FROM, marker=marker)
        installed = wba_confirm.container_version(wba_segments, wle_segments)
        print(f"[INFO] {wba_confirm.describe_metadata(wba_segments, wle_segments)}")
    except wba_confirm.WbaConfirmError as e:
        raise SidSecureProgError(f"bootloader metadata: {e}")
    # the SID factory container must hold these apps: the bootloader compares its version with the installed one
    if versions["SID"] != installed:
        raise SidSecureProgError(
            f"--ext-flash: SID factory container version {wba_confirm.version_str(versions['SID'])} "
            f"(0x{versions['SID']:08X}) does not match the apps being programmed: WBA "
            f"{wba_confirm.version_str(wba_confirm.wba_version(wba_segments))} + WLE "
            f"{wba_confirm.version_str(wba_confirm.wle_version(wle_segments))} = "
            f"{wba_confirm.version_str(installed)} (0x{installed:08X})")
    print("[INFO] SID factory container version matches the WBA + WLE apps")
    # ... and was built for the same hardware: the WLE app's SMAC_HW_VERSION (hw_2_0_2 / hw_2_0_3 builds share a
    # version and differ only in this)
    factory_hw = factory_wle_hw_version(ext_flash)
    wle_hw = wle_hw_version(memory(wle_segments, WLE_APP, WLE_INFO_SIZE), "WLE image")
    if factory_hw != wle_hw:
        raise SidSecureProgError(
            f"--ext-flash: the SID factory container's WLE app is for hardware {hw_version_str(factory_hw)} "
            f"(0x{factory_hw:08X}), the WLE app being programmed for {hw_version_str(wle_hw)} (0x{wle_hw:08X})")
    print(f"[INFO] SID factory container WLE hardware version {hw_version_str(factory_hw)} matches the WLE app")

    try:
        cli_path = stlink.find_cli(cli)
    except stlink.StLinkError as e:
        raise SidSecureProgError(str(e))
    alignment = stlink.otp_db_alignment(cli_path)
    if alignment != OTP_DB_ALIGNMENT:
        raise SidSecureProgError(
            f"STM32CubeProgrammer cannot write the WBA OTP safely: the OTP block <Alignment> in "
            f"{stlink.WBA_DEVICE_DB} is {hex(alignment) if alignment is not None else 'not found'}, needs 0x10 "
            f"(see the sid_secure_prog README)")
    return pub, marker, factory, cli_path, wle_hex, wba_hex


def boot_log(cli, probes, freq, ports, after, timeout):
    try:
        return sid_reg_wait.collect(ports, APP_START_RE, timeout, after=after,
                                    start=lambda: sid_reg_wait.reset_device(cli, probes, freq))
    except sid_reg_wait.SidRegWaitError as e:
        raise SidSecureProgError(f"boot log: {e}")


def program(wle_boot, wle_app, wba_boot, wba_app, sign_key_value, ext_flash, **opts):
    """Run the steps (see the module docstring); prints the same log as the CLI.

    opts: app_window, boot_timeout, wle_sn, wba_sn, wba_port, wle_port, mode, freq, cli, rdp, check_only.
    Returns {"key_fp", "otp_slot" (None if the key was already there), "rdp": {mcu: level}}.
    Raises SidSecureProgError at the first failing check or step.
    """
    with tempfile.TemporaryDirectory(prefix="sid_secure_prog_images_") as work_dir:
        return _program(work_dir, wle_boot, wle_app, wba_boot, wba_app, sign_key_value, ext_flash, **opts)


def _program(work_dir, wle_boot, wle_app, wba_boot, wba_app, sign_key_value, ext_flash, *,
             app_window=DEFAULT_APP_WINDOW, boot_timeout=DEFAULT_BOOT_TIMEOUT, wle_sn=None, wba_sn=None, wba_port=None,
             wle_port=None, mode="UR", freq=None, cli=None, rdp=True, check_only=False,
             list_ports=sid_reg_wait.list_ports, open_port=sid_reg_wait.open_port):
    _step(1, "Offline checks")
    pub, marker, factory, cli, wle_fw, wba_fw = offline_checks(wle_boot, wle_app, wba_boot, wba_app, sign_key_value,
                                                               ext_flash, cli, work_dir)
    result = {"key_fp": sign_key.fingerprint(pub), "otp_slot": None, "rdp": {}}
    if check_only:
        return result

    try:
        _step(2, "ST-Links")
        probes = stlink.resolve(["WLE", "WBA"], sns={m: s for m, s in (("WLE", wle_sn), ("WBA", wba_sn)) if s},
                                cli=cli, freq=freq)
        for mcu in ("WLE", "WBA"):
            level = stlink.read_rdp(cli, probes[mcu].sn, freq=freq)
            if level != stlink.RDP_LEVEL_0:
                raise SidSecureProgError(f"{mcu} RDP is 0x{level:02X}, not level 0: already locked "
                                         f"(an RDP regression mass-erases it first)")
        devices = sid_reg_wait.port_devices(probes, wba_port, wle_port, True, list_ports)

        _step(3, "WLE: erase pages 0..124, write image")
        if not stlink.program(cli, probes["WLE"].sn, os.path.abspath(wle_fw), "[WLE]", erase_pages=WLE_ERASE_PAGES,
                              mode=mode, freq=freq):
            raise SidSecureProgError("WLE erase/write failed")

        with tempfile.TemporaryDirectory(prefix="sid_secure_prog_") as tmp:
            _step(4, "WBA: erase pages 0..116, write image + confirmed validity marker + bootloader metadata")
            image = merge_marker(os.path.abspath(wba_fw), tmp, os.path.abspath(wle_fw))
            if not stlink.program(cli, probes["WBA"].sn, image, "[WBA]", erase_pages=WBA_ERASE_PAGES, mode=mode,
                                  freq=freq):
                raise SidSecureProgError("WBA erase/write failed")

            ports = sid_reg_wait.open_logs(devices, sid_reg_wait.DEFAULT_BAUD, open_port)
            try:
                _step(5, "Boot check: sign key, factory containers")
                key = check_boot(boot_log(cli, probes, freq, ports, 0.0, boot_timeout), pub, factory,
                                 provisioned=False)

                _step(6, "WBA OTP: sign key record")
                dump = stlink.read_memory(cli, probes["WBA"].sn, sign_key.FLASH_OTP_BASE, sign_key.FLASH_OTP_SIZE,
                                          freq=freq)
                slot = otp_plan(dump, pub)
                if slot is None:
                    print(f"[INFO] The key is already in OTP (bootloader reported {key[:16]}...), nothing to write")
                else:
                    address = sign_key.FLASH_OTP_BASE + slot * sign_key.OTP_SLOT_SIZE
                    record_hex = os.path.join(tmp, "otp_key_record.hex")
                    write_hex(record_hex, address, sign_key.otp_record(pub))
                    print(f"[INFO] Writing the key record to OTP slots {slot}..{slot + sign_key.OTP_SLOTS - 1} "
                          f"(0x{address:08X})")
                    ok = stlink.program(cli, probes["WBA"].sn, record_hex, "[WBA]", mode=mode, freq=freq)
                    status, written = sign_key.parse_otp(stlink.read_memory(
                        cli, probes["WBA"].sn, sign_key.FLASH_OTP_BASE, sign_key.FLASH_OTP_SIZE, freq=freq))
                    if status != sign_key.OTP_OK or written != pub:
                        raise SidSecureProgError(f"OTP read-back after the write: status {status}, "
                                                 f"{'key ' + written.hex().upper() if written else 'no key'}"
                                                 f"{'' if ok else ' (the write reported an error)'}")
                    result["otp_slot"] = slot

                _step(7, f"Boot check: signature enforced, {app_window:g} s of app log")
                check_boot(boot_log(cli, probes, freq, ports, app_window, boot_timeout), pub, factory,
                           provisioned=True)
            finally:
                sid_reg_wait.close_logs(ports)

        _step(8, "RDP level 1: WLE, then WBA")
        if not rdp:
            print("[WARNING] --no-rdp: both MCUs stay at RDP level 0 (bench use only)")
        else:
            for mcu in ("WLE", "WBA"):
                ok = stlink.set_rdp(cli, probes[mcu].sn, stlink.RDP_LEVEL_1, f"[{mcu}]", mode=mode, freq=freq)
                level = stlink.read_rdp(cli, probes[mcu].sn, freq=freq)
                if level != stlink.RDP_LEVEL_1:
                    raise SidSecureProgError(f"{mcu} RDP reads 0x{level:02X} after setting level 1"
                                             f"{'' if ok else ' (the CLI reported an error)'}")
                result["rdp"][mcu] = level
                print(f"[INFO] {mcu} RDP level 1 (0x{level:02X})")
    except stlink.StLinkError as e:
        raise SidSecureProgError(str(e))
    except sid_reg_wait.SidRegWaitError as e:
        raise SidSecureProgError(str(e))
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wle-boot", required=True, metavar="FILE", help="WLE bootloader (.hex or .elf)")
    p.add_argument("--wle-app", required=True, metavar="FILE", help="WLE application (.hex or .elf)")
    p.add_argument("--wba-boot", required=True, metavar="FILE", help="WBA bootloader (.hex or .elf)")
    p.add_argument("--wba-app", required=True, metavar="FILE", help="WBA application, signed with the key (.hex or .elf)")
    p.add_argument("--sign-key", required=True, metavar="KEY",
                   help="Ed25519 public sign key: key file (PEM with an ED25519 PUBLIC KEY block) or 64 hex digits")
    p.add_argument("--ext-flash", required=True, metavar="BIN",
                   help="external-flash (SPI NOR) factory image, as made by smac_tools/container/spi_flash_image.py")
    p.add_argument("--app-window", type=float, default=DEFAULT_APP_WINDOW, metavar="S",
                   help=f"seconds of app log checked after the final boot (default: {DEFAULT_APP_WINDOW:g})")
    p.add_argument("--boot-timeout", type=float, default=DEFAULT_BOOT_TIMEOUT, metavar="S",
                   help=f"seconds to wait for the app start after each reset (default: {DEFAULT_BOOT_TIMEOUT:g})")
    p.add_argument("--wle-sn", metavar="SN", help="ST-Link serial of the WLE (default: auto-detect)")
    p.add_argument("--wba-sn", metavar="SN", help="ST-Link serial of the WBA (default: auto-detect)")
    p.add_argument("--wba-port", metavar="PORT", help="WBA log serial port (default: the WBA ST-Link's VCP)")
    p.add_argument("--wle-port", metavar="PORT", help="WLE log serial port (default: the WLE ST-Link's VCP)")
    p.add_argument("--mode", choices=stlink.CONNECT_MODES, default="UR",
                   help="SWD connect mode for erase/write/RDP (default: UR, needs NRST)")
    p.add_argument("--freq", type=int, metavar="KHZ", help=f"SWD frequency in kHz (default: {stlink.DEFAULT_FREQ})")
    p.add_argument("--cli", metavar="PATH", help=f"path to {stlink.CLI_NAME}")
    p.add_argument("--check-only", action="store_true", help="only the offline checks (step 1), no hardware")
    p.add_argument("--no-rdp", action="store_true", help="skip RDP level 1 (bench use only; OTP is still written)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        result = program(args.wle_boot, args.wle_app, args.wba_boot, args.wba_app, args.sign_key, args.ext_flash,
                         app_window=args.app_window,
                         boot_timeout=args.boot_timeout, wle_sn=args.wle_sn, wba_sn=args.wba_sn,
                         wba_port=args.wba_port, wle_port=args.wle_port, mode=args.mode, freq=args.freq,
                         cli=args.cli, rdp=not args.no_rdp, check_only=args.check_only)
    except SidSecureProgError as e:
        print(f"[ERROR] {e}", flush=True)
        return 1
    if args.check_only:
        print("[INFO] Offline checks passed", flush=True)
    else:
        otp = "already there" if result["otp_slot"] is None else f"slot {result['otp_slot']}"
        print(f"[INFO] PASS: key fp={result['key_fp']} (OTP {otp}), RDP "
              f"{'level 1' if result['rdp'] else 'unchanged (--no-rdp)'}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted")
        sys.exit(130)
