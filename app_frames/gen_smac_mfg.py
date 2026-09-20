#!/usr/bin/env python3
"""
gen_smac_mfg.py

Generates the sid_smartac WLE manufacturing data binary: the raw image of the
`factory_data_internal_t` struct read by

    apps/st/stm32wba/sid_smartac/stm32wle5x/components/factory_data/src/factory_data.c
    apps/st/stm32wba/sid_smartac/stm32wle5x/components/factory_data/include/factory_data/factory_data.h

Each field is stored alongside its bitwise-inverted value; factory_data_get() only returns a field
whose stored inverted bytes are the exact one's-complement of its data bytes (`inverted[i] ==
(uint8_t)~data[i]`), so this tool computes and writes the same complement.

If -m/-l is omitted, that field is left UNPOPULATED rather than defaulted: both its data and
inverted bytes are written as 0xFF, matching erased-flash state. `0xFF` data with `0xFF` inverted
fails factory_data_get()'s `data[i] == (uint8_t)~inverted[i]` check by construction, so the
firmware correctly reports that field as missing instead of silently reading a fabricated zero
value.

The `.factory_data` linker section (STM32WLE5CCUX_FLASH.ld) is NOLOAD, fixed at flash address
0x0803F800 (start of the PERMANENT_DATA region) and is not part of the application image - the
output of this script must be flashed there separately, e.g.:

    JLinkExe -> LoadFile smac_mfg.bin,0x0803F800

Usage:
    python3 gen_smac_mfg.py [-m ENV_SENSORS_MAP] [-l LABEL] [-o OUTPUT]

    -m, --env-sensors-map   Bitmask of environmental sensors present on the device, in HEX
                             (e.g. "7FF" or "0x7FF"). Left unpopulated (0xFF) if omitted.
    -l, --label             Device back-label, printed in the form XX-XXXXXX (8 hex digits).
                             The "-" is optional (XXXXXXXX also accepted). Left unpopulated
                             (0xFF) if omitted.

NOTE ON LABEL ENCODING: the 8 hexadecimal characters are packed two per byte, most-significant
nibble first, in label order (for example, 1500013C becomes 15 00 01 3C).
"""

import argparse
import re
import struct
import sys
from pathlib import Path

FACTORY_DATA_ADDRESS = 0x0803F800

# Must match `factory_data_internal_t` in factory_data.c (packed, little-endian):
#   fd_label_t label:                    uint8_t label[4];    uint8_t inverted[4];
#   fd_env_sensors_map_t env_sensors_map: uint32_t env_sensors_map; uint32_t inverted;
FACTORY_DATA_FORMAT = '<4s4sII'
FACTORY_DATA_SIZE = struct.calcsize(FACTORY_DATA_FORMAT)

LABEL_RE = re.compile(r'^([0-9A-Fa-f]{2})-?([0-9A-Fa-f]{6})$')

UNPOPULATED_FIELD = b'\xFF\xFF\xFF\xFF'

DEFAULT_OUTPUT = Path(__file__).parent / 'smac_mfg.bin'


class InvalidLabelError(Exception):
    pass


class InvalidEnvSensorsMapError(Exception):
    pass


def invert_bytes(data: bytes) -> bytes:
    return bytes((~b) & 0xFF for b in data)


def parse_env_sensors_map(hex_str: str) -> int:
    try:
        value = int(hex_str, 16)
    except ValueError:
        raise InvalidEnvSensorsMapError(f"'{hex_str}' is not a valid hex value")

    if not (0 <= value <= 0xFFFFFFFF):
        raise InvalidEnvSensorsMapError(f"env_sensors_map 0x{value:X} does not fit in 32 bits")

    return value


def encode_label(label_str: str) -> bytes:
    match = LABEL_RE.match(label_str)
    if not match:
        raise InvalidLabelError(f"'{label_str}' does not match the expected label form XX-XXXXXX (dash optional)")

    return bytes.fromhex(match.group(1) + match.group(2))


def build_factory_data(env_sensors_map, label_str) -> bytes:
    if label_str is None:
        label, label_inverted = UNPOPULATED_FIELD, UNPOPULATED_FIELD
    else:
        label = encode_label(label_str)
        label_inverted = invert_bytes(label)

    if env_sensors_map is None:
        env_sensors_map_value, env_sensors_map_inverted = 0xFFFFFFFF, 0xFFFFFFFF
    else:
        env_sensors_map_value = env_sensors_map
        env_sensors_map_inverted = (~env_sensors_map) & 0xFFFFFFFF

    return struct.pack(
        FACTORY_DATA_FORMAT,
        label, label_inverted,
        env_sensors_map_value, env_sensors_map_inverted,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-m', '--env-sensors-map', default=None,
                         help='Environmental sensors bitmap, in HEX (e.g. "7FF" or "0x7FF"). '
                              'Left unpopulated (0xFF) if omitted.')
    parser.add_argument('-l', '--label', default=None,
                         help='Device back-label, 8 hexadecimal digits in form XX-XXXXXX or XXXXXXXX. '
                              'Left unpopulated (0xFF) if omitted.')
    parser.add_argument('-o', '--output', default=str(DEFAULT_OUTPUT),
                         help=f'Output binary file path (default: {DEFAULT_OUTPUT})')

    args = parser.parse_args()

    try:
        env_sensors_map = (
            parse_env_sensors_map(args.env_sensors_map) if args.env_sensors_map is not None else None
        )
        factory_data = build_factory_data(env_sensors_map, args.label)
        assert len(factory_data) == FACTORY_DATA_SIZE

        with open(args.output, 'wb') as f:
            f.write(factory_data)

        print('[INFO] env_sensors_map = ' +
              (f'0x{env_sensors_map:08X}' if env_sensors_map is not None else 'UNPOPULATED (0xFF)'))
        print('[INFO] label           = ' + (args.label if args.label is not None else 'UNPOPULATED (0xFF)'))
        print(f'[INFO] Wrote {len(factory_data)} bytes to {args.output}')
        print(f'[INFO] Flash at address 0x{FACTORY_DATA_ADDRESS:08X} (.factory_data section, '
              f'STM32WLE5CCUX_FLASH.ld)')

    except (InvalidLabelError, InvalidEnvSensorsMapError) as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
