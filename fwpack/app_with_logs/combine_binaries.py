#!/usr/bin/env python3
"""
combine_binaries.py

Merges a list of ELF/Intel-HEX/raw-binary firmware images into a single Intel HEX file.

Each input's type is inferred from its extension (.elf, .hex/.ihex, .bin). A .bin input has no
address information of its own, so it must be immediately followed by the HEX load offset to
place it at, e.g.:

    python3 combine_binaries.py wba_app.elf wba_boot.elf smac_mfg.bin 0x080FE000

Unless -o/--output is given, the output file is named after the concatenation of the input file
names with every '.' replaced by '_' (e.g. the command above writes
wba_app_elf_wba_boot_elf_smac_mfg_bin.hex).

ELF and .bin inputs are converted to Intel HEX via `objcopy` (already relied on elsewhere in this
tool, see burn.py); .hex/.ihex inputs are taken as-is. The converted records are then concatenated
in the given order, dropping every intermediate End-Of-File record (":00000001FF") and appending a
single one at the end - this is a mechanical/textual merge, so the caller is responsible for
ensuring the inputs don't have overlapping address ranges.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

OBJCOPY_BIN = "arm-none-eabi-objcopy"

BIN_EXTENSIONS = {".bin"}
ELF_EXTENSIONS = {".elf"}
HEX_EXTENSIONS = {".hex", ".ihex"}

IHEX_EOF_RECORD = ":00000001FF"


class InputError(Exception):
    pass


def default_output_name(entries):
    """Concatenates the input file names (dots replaced with underscores), e.g.
    wba_app.elf + smac_mfg.bin -> wba_app_elf_smac_mfg_bin.hex"""
    parts = [path.name.replace(".", "_") for path, _kind, _offset in entries]
    return "_".join(parts) + ".hex"


def parse_hex_offset(text):
    try:
        return int(text, 16)
    except ValueError:
        raise InputError(f"'{text}' is not a valid HEX offset")


def parse_inputs(tokens):
    entries = []
    i = 0

    while i < len(tokens):
        path = Path(tokens[i])
        suffix = path.suffix.lower()

        if suffix in BIN_EXTENSIONS:
            if i + 1 >= len(tokens):
                raise InputError(f"'{path}' is a .bin file and must be followed by a HEX offset")
            offset = parse_hex_offset(tokens[i + 1])
            entries.append((path, "bin", offset))
            i += 2
        elif suffix in ELF_EXTENSIONS:
            entries.append((path, "elf", None))
            i += 1
        elif suffix in HEX_EXTENSIONS:
            entries.append((path, "hex", None))
            i += 1
        else:
            raise InputError(f"'{path}': unrecognized file type (expected .elf, .hex/.ihex, or .bin)")

        if not path.is_file():
            raise InputError(f"'{path}': no such file")

    if not entries:
        raise InputError("no input files given")

    return entries


def convert_to_ihex(entry, tmp_dir):
    path, kind, offset = entry

    if kind == "hex":
        return path.read_text()

    tmp_out = tmp_dir / f"{path.stem}.hex"

    if kind == "elf":
        cmd = [OBJCOPY_BIN, "-O", "ihex", str(path), str(tmp_out)]
    else:  # bin
        cmd = [OBJCOPY_BIN, "-I", "binary", "-O", "ihex", f"--change-addresses=0x{offset:X}", str(path), str(tmp_out)]

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise InputError(f"'{OBJCOPY_BIN}' not found - required to convert '{path}' to Intel HEX")
    except subprocess.CalledProcessError as e:
        raise InputError(f"'{OBJCOPY_BIN}' failed converting '{path}': {e}")

    return tmp_out.read_text()


def merge_ihex(ihex_texts):
    merged = []

    for text in ihex_texts:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.upper() == IHEX_EOF_RECORD:
                continue
            merged.append(line)

    merged.append(IHEX_EOF_RECORD)
    return "\n".join(merged) + "\n"


def parse_ihex_ranges(text):
    """Returns the [start, end) byte range covered by each data record in an Intel HEX file."""
    ranges = []
    base = 0

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(":"):
            continue

        byte_count = int(line[1:3], 16)
        address = int(line[3:7], 16)
        record_type = int(line[7:9], 16)
        data = line[9:9 + byte_count * 2]

        if record_type == 0x00:  # data
            start = base + address
            ranges.append((start, start + byte_count))
        elif record_type == 0x01:  # EOF
            break
        elif record_type == 0x02:  # extended segment address
            base = int(data, 16) * 16
        elif record_type == 0x04:  # extended linear address
            base = int(data, 16) << 16
        # 0x03/0x05 (start segment/linear address) carry no memory-layout info

    return ranges


def coalesce_ranges(ranges):
    """Merges overlapping/adjacent [start, end) ranges into contiguous sections."""
    if not ranges:
        return []

    ordered = sorted(ranges)
    sections = [list(ordered[0])]

    for start, end in ordered[1:]:
        if start <= sections[-1][1]:
            sections[-1][1] = max(sections[-1][1], end)
        else:
            sections.append([start, end])

    return [tuple(section) for section in sections]


def format_size(num_bytes):
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes} bytes ({num_bytes / (1024 * 1024):.1f} MB)"
    if num_bytes >= 1024:
        return f"{num_bytes} bytes ({num_bytes / 1024:.1f} KB)"
    return f"{num_bytes} bytes"


def print_memory_map(text):
    sections = coalesce_ranges(parse_ihex_ranges(text))

    if not sections:
        print("[INFO] No data records found")
        return

    print(f"[INFO] Memory sections ({len(sections)}):")
    for i, (start, end) in enumerate(sections):
        print(f"[INFO]   0x{start:08X} - 0x{end - 1:08X}  ({format_size(end - start)})")

        if i + 1 < len(sections):
            gap_start, gap_end = end, sections[i + 1][0]
            print(f"[INFO]     ... gap  0x{gap_start:08X} - 0x{gap_end - 1:08X}  ({format_size(gap_end - gap_start)}) ...")


def combine(entries, output_path):
    with tempfile.TemporaryDirectory(prefix="combine_binaries_") as tmp_dir:
        tmp_dir = Path(tmp_dir)
        ihex_texts = [convert_to_ihex(entry, tmp_dir) for entry in entries]

    merged = merge_ihex(ihex_texts)
    output_path.write_text(merged)
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output Intel HEX file path (default: input file names concatenated, '.' replaced with '_')",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="ELF/HEX/BIN files to merge, in order. Each .bin must be immediately followed by its HEX load offset.",
    )
    args = parser.parse_args()

    try:
        entries = parse_inputs(args.inputs)
        output_path = Path(args.output) if args.output else Path(default_output_name(entries))
        merged = combine(entries, output_path)
    except InputError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Merged {len(entries)} input(s) into {output_path}")
    for path, kind, offset in entries:
        if kind == "bin":
            print(f"[INFO]   {path} (bin @ 0x{offset:X})")
        else:
            print(f"[INFO]   {path} ({kind})")

    print_memory_map(merged)


if __name__ == "__main__":
    main()
