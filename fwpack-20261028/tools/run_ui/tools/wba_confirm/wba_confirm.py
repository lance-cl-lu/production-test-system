#!/usr/bin/env python3
"""Add the "confirmed" app validity marker to a WBA image (bootloader + app, Intel HEX).

The WBA bootloader runs an app whose validity marker is erased ("pending") on trial: after 3 boots without the app
confirming itself (it needs a Sidewalk link for that) it rejects the app and reinstalls the factory container. The
marker is NOLOAD, so a freshly built image never contains it. A station that programs an app for good writes it
already confirmed, as a factory install does (app_wba_set_valid()): the 16-byte magic
7AC3F91E D45E8B20 31B7C4DA E9A0625F at the address the app's OTA header points to (second word at 0x08012188).

With --wle (the WLE image going onto the same device) it also adds the bootloader metadata that a factory install
writes and a station's erase removes: the installed container version (OTA status page, WBA app version + WLE app
version) and the app implementation (AIM_META page, SID). Without them the bootloader logs
"[WARNING] metadata.c:306 err=15" on every boot.

The marker (and metadata) are merged into the image with combine_binaries, so the result is one file, written in
one go.

Usage:
  wba_confirm.py wba.hex [--wle wle.hex] -o wba_confirmed.hex

Python use (put smac_tools/run_ui/tools on sys.path or PYTHONPATH):
  import wba_confirm
  marker = wba_confirm.confirm("wba.hex", "wba_confirmed.hex", wle_hex="wle.hex")   # raises WbaConfirmError
"""

import argparse
import os
import struct
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)  # smac_tools/run_ui/tools: combine_binaries is a sibling
try:
    import combine_binaries  # noqa: E402
except ImportError:
    sys.path.insert(0, TOOLS)
    import combine_binaries  # noqa: E402

WBA_FLASH = 0x08000000
WBA_MFG_DATA = 0x080FE000  # Sidewalk MFG_DATA page: the marker is always below it
APP_FLASH = 0x08012000  # APP_FLASH in STM32WBA5xxG_Sidewalk_OTA.ld
APP_HEADER = APP_FLASH + 0x188  # sid_aim_ota_header_t: footer pointer, validity marker pointer, version
# SID_AIM_IFC_VALIDITY_MARKER_MAGIC_WORD_INITIALIZER (sid_application_install_manager_ifc.h)
CONFIRMED_MARKER = struct.pack("<4I", 0x7AC3F91E, 0xD45E8B20, 0x31B7C4DA, 0xE9A0625F)
FLASH_WORD = 16
APP_VERSION = APP_HEADER + 8  # app_version_major, _minor, _patch, _build (one byte each)

# Bootloader metadata (sid_smartac_wba_bootloader Core/Src/metadata.c). Both pages are NOLOAD.
OTA_STATUS = 0x0800E000  # OTA_STATUS_FLASH: ota_state_t {trial_counter (32 B), container_version, install_status}
CONTAINER_VERSION_LINE = OTA_STATUS + 32
CONTAINER_VERSION_MAGIC = (0xC0DEBABE, 0xFEEDFACE, 0x02AC0DE1)  # cMetadataOtaStateInstalledContainerVersionMagic
AIM_META = 0x08010000  # AIM_META: app implementation line at offset 0
APP_IMPL_MAGIC = (0x5EEDFEE1, 0xDEADF00D, 0x999AABB3)  # cMetadataAppImplementationMagic
APP_IMPL_SID = 0  # APP_IMPLEMENTATION_SID, the bootloader's default

# WLE app info block (fw_tools.c), at the start of the WLE app (FLASH_AIB); as smac_tools/container/container.py
WLE_APP = 0x08008800
WLE_INFO_MAGIC = 0xC0FEB00B
WLE_VERFW_OFFSET = 33  # verfw, already packed major<<24 | minor<<16 | patch<<8 | build


class WbaConfirmError(Exception):
    pass


# ---------------------------------------------------------------------------
# Intel HEX
# ---------------------------------------------------------------------------

def read_hex(path):
    """Data of an Intel HEX file as sorted, merged [(start, bytes)]. Raises WbaConfirmError."""
    segments = []
    base = 0
    eof = None
    try:
        lines = Path(path).read_text().splitlines()
    except OSError as e:
        raise WbaConfirmError(f"cannot read {path}: {e.strerror}")
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        if eof:  # combine_binaries would still merge (and so flash) it, unchecked
            raise WbaConfirmError(f"{path}:{n}: data after the end-of-file record (line {eof})")
        try:
            if not line.startswith(":"):
                raise ValueError("no ':'")
            record = bytes.fromhex(line[1:])
            count, address, rtype = record[0], int.from_bytes(record[1:3], "big"), record[3]
            data = record[4:4 + count]
            if len(record) != 5 + count or sum(record) & 0xFF:
                raise ValueError("bad length or checksum")
        except (ValueError, IndexError) as e:
            raise WbaConfirmError(f"{path}:{n}: not an Intel HEX record ({e})")
        if rtype == 0x00:
            start = base + address
            if segments and segments[-1][0] + len(segments[-1][1]) == start:
                segments[-1][1].extend(data)
            else:
                segments.append([start, bytearray(data)])
        elif rtype == 0x01:
            eof = n
        elif rtype == 0x02:
            base = int.from_bytes(data, "big") << 4
        elif rtype == 0x04:
            base = int.from_bytes(data, "big") << 16
    merged = []
    for start, data in sorted(segments):
        if merged and merged[-1][0] + len(merged[-1][1]) >= start:
            prev_start, prev = merged[-1]
            if prev_start + len(prev) - start > 0:
                raise WbaConfirmError(f"{path}: data overlaps at 0x{start:08X}")
            prev.extend(data)
        else:
            merged.append([start, bytearray(data)])
    return [(start, bytes(data)) for start, data in merged]


def memory(segments, start, size, fill=0xFF):
    """`size` bytes from `start` out of the hex segments, gaps filled with `fill`."""
    out = bytearray([fill]) * size
    for seg_start, data in segments:
        lo, hi = max(start, seg_start), min(start + size, seg_start + len(data))
        if lo < hi:
            out[lo - start:hi - start] = data[lo - seg_start:hi - seg_start]
    return bytes(out)


def covered(segments, start, size):
    """True if any byte of start..start+size-1 has data."""
    return any(seg_start < start + size and start < seg_start + len(data) for seg_start, data in segments)


def write_hex(path, address, data):
    """A small Intel HEX file holding `data` at `address`."""
    def record(rtype, addr16, payload):
        body = bytes([len(payload), addr16 >> 8, addr16 & 0xFF, rtype]) + payload
        return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper() + "\n"

    lines, upper, i = [], None, 0
    while i < len(data):
        a = address + i
        if a >> 16 != upper:
            upper = a >> 16
            lines.append(record(0x04, 0, upper.to_bytes(2, "big")))
        count = min(16, len(data) - i, 0x10000 - (a & 0xFFFF))  # a record must not cross a 64 KB boundary
        lines.append(record(0x00, a & 0xFFFF, data[i:i + count]))
        i += count
    lines.append(record(0x01, 0, b""))
    with open(path, "w", encoding="ascii") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------

def marker_address(segments, limit=WBA_MFG_DATA):
    """Address of the app's validity marker, from its OTA header. Raises WbaConfirmError.

    The marker must be a flash word below `limit` that the image leaves empty."""
    if not covered(segments, APP_HEADER, 8):
        raise WbaConfirmError(f"no app OTA header at 0x{APP_HEADER:08X}")
    _footer, marker = struct.unpack("<II", memory(segments, APP_HEADER, 8))
    if marker % FLASH_WORD or not WBA_FLASH <= marker <= limit - FLASH_WORD:
        raise WbaConfirmError(f"validity marker address 0x{marker:08X} is not a flash word inside "
                              f"0x{WBA_FLASH:08X}..0x{limit - 1:08X}")
    if covered(segments, marker, FLASH_WORD):
        raise WbaConfirmError(f"the image already has data at the validity marker 0x{marker:08X}")
    return marker


# ---------------------------------------------------------------------------
# Bootloader metadata
# ---------------------------------------------------------------------------

def version_str(v):
    """A packed version (major in the top byte) as "major.minor.patch.build"."""
    return ".".join(str((v >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def wba_version(segments):
    """The WBA app version from its OTA header, packed like the bootloader's fw_ver_to_u32()."""
    if not covered(segments, APP_VERSION, 4):
        raise WbaConfirmError(f"no app version in the OTA header at 0x{APP_VERSION:08X}")
    major, minor, patch, build = memory(segments, APP_VERSION, 4)
    return (major << 24) | (minor << 16) | (patch << 8) | build


def wle_version(segments):
    """The WLE app version (verfw) from the info block at the WLE app start."""
    magic, = struct.unpack("<I", memory(segments, WLE_APP, 4))
    if magic != WLE_INFO_MAGIC:
        raise WbaConfirmError(f"no WLE app info block at 0x{WLE_APP:08X} (magic 0x{magic:08X}, "
                              f"expected 0x{WLE_INFO_MAGIC:08X})")
    return struct.unpack("<I", memory(segments, WLE_APP + WLE_VERFW_OFFSET, 4))[0]


def container_version(wba_segments, wle_segments):
    """The installed container version a factory install of these apps records: WBA app version + WLE app version
    (bootloader.c, smac_tools/container/container.py)."""
    v = wba_version(wba_segments) + wle_version(wle_segments)
    if v > 0xFFFFFFFF:
        raise WbaConfirmError(f"container version 0x{v:X} (WBA + WLE app version) does not fit 32 bits")
    return v


def metadata_lines(version, app_impl=APP_IMPL_SID):
    """[(address, 16 bytes)]: the installed container version and app implementation lines."""
    return [(CONTAINER_VERSION_LINE, struct.pack("<4I", *CONTAINER_VERSION_MAGIC, version)),
            (AIM_META, struct.pack("<4I", *APP_IMPL_MAGIC, app_impl))]


def metadata(wba_segments, wle_segments, limit=WBA_MFG_DATA, marker=None):
    """The metadata lines for these images, checked to be flash below `limit` that the WBA image leaves empty and,
    with `marker` (the validity marker address), not the marker's line. Raises WbaConfirmError."""
    lines = metadata_lines(container_version(wba_segments, wle_segments))
    for address, _data in lines:
        if marker is not None and address < marker + FLASH_WORD and marker < address + FLASH_WORD:
            raise WbaConfirmError(f"the validity marker 0x{marker:08X} (from the app's OTA header) is at the "
                                  f"bootloader metadata 0x{address:08X}")
        if not WBA_FLASH <= address <= limit - FLASH_WORD:
            raise WbaConfirmError(f"bootloader metadata at 0x{address:08X} is outside "
                                  f"0x{WBA_FLASH:08X}..0x{limit - 1:08X}")
        if covered(wba_segments, address, FLASH_WORD):
            raise WbaConfirmError(f"the image already has data at the bootloader metadata 0x{address:08X}")
    return lines


def confirm(in_hex, out_hex, limit=WBA_MFG_DATA, wle_hex=None):
    """Write in_hex + the confirmed validity marker to out_hex (via combine_binaries); returns the marker address.
    With wle_hex (the WLE image for the same device) the bootloader metadata lines are added too.
    Raises WbaConfirmError."""
    segments = read_hex(in_hex)
    marker = marker_address(segments, limit)
    lines = [(marker, CONFIRMED_MARKER)]
    if wle_hex:
        lines += metadata(segments, read_hex(wle_hex), limit, marker=marker)
    with tempfile.TemporaryDirectory(prefix="wba_confirm_") as tmp:
        inputs = [in_hex]
        for i, (address, data) in enumerate(lines):
            inputs.append(os.path.join(tmp, f"line_{i}.hex"))
            write_hex(inputs[-1], address, data)
        try:
            combine_binaries.combine(combine_binaries.parse_inputs(inputs), Path(out_hex))
        except combine_binaries.InputError as e:
            raise WbaConfirmError(f"merging the validity marker and metadata: {e}")
    return lines[0][0]


def describe_metadata(wba_segments, wle_segments):
    """One log line about the metadata confirm() adds for these images."""
    wba, wle = wba_version(wba_segments), wle_version(wle_segments)
    v = container_version(wba_segments, wle_segments)
    return (f"Bootloader metadata: installed container version 0x{v:08X} "
            f"(WBA {version_str(wba)} + WLE {version_str(wle)}), app implementation SID")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", metavar="IN.hex", help="WBA image: bootloader + app, Intel HEX")
    p.add_argument("--wle", metavar="WLE.hex",
                   help="WLE image (bootloader + app) for the same device: also add the bootloader metadata")
    p.add_argument("-o", "--output", required=True, metavar="OUT.hex", help="the image with the confirmed marker")
    args = p.parse_args(argv)
    try:
        marker = confirm(args.input, args.output, wle_hex=args.wle)
        if args.wle:
            print(f"[INFO] {describe_metadata(read_hex(args.input), read_hex(args.wle))}", flush=True)
    except WbaConfirmError as e:
        print(f"[ERROR] {e}", flush=True)
        return 1
    print(f"[INFO] Confirmed validity marker at 0x{marker:08X} -> {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
