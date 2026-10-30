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
    python3 gen_smac_mfg.py [-m ENV_SENSORS_MAP | -i IC_NAME [IC_NAME ...]] [-l LABEL] [-o OUTPUT]

    -m, --env-sensors-map   Bitmask of environmental sensors present on the device, in HEX
                             (e.g. "7FF" or "0x7FF"). Left unpopulated (0xFF) if omitted.
                             Mutually exclusive with -i/--ics.
    -i, --ics                List of internal environmental-sensor ICs present on the device, one
                             name per sensor family: LPS22, ENS21X, SHT4X, BME69X, e.g.
                             "-i LPS22 BME69X". Builds the env_sensors_map bitmask from
                             sensor_id_t bit positions instead of specifying it directly (see
                             IC_SENSOR_BITS below for the exact IC -> sensor_id_t mapping).
                             Mutually exclusive with -m/--env-sensors-map.
    -l, --label             Device back-label, printed in the form XX-XXXXXX (8 hex digits,
                             0-9/a-f, case-insensitive). The "-" is optional (XXXXXXXX also
                             accepted). Left unpopulated (0xFF) if omitted.

NOTE ON LABEL ENCODING: neither factory_data.h nor INFO_FRAME_SPEC.md pins down the nibble
packing, only the printed form "XX-XXXXXX". This tool packs the 8 hex digits two per byte, most
significant nibble first, in label order (byte 0 = digits[0:2], i.e. the "XX" part) - but this
has not been cross-checked against a reference device/production tool and should be confirmed
before relying on it for real manufacturing data.

Python use (put smac_tools/run_ui/tools on sys.path or PYTHONPATH):
    import gen_smac_mfg
    data = gen_smac_mfg.build_factory_data(gen_smac_mfg.parse_ic_names(["LPS22", "BME69X"]), "1A-2B3C4D")
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

LABEL_RE = re.compile(r'^([0-9a-fA-F]{2})-?([0-9a-fA-F]{6})$')

UNPOPULATED_FIELD = b'\xFF\xFF\xFF\xFF'

DEFAULT_OUTPUT = Path(__file__).parent / 'smac_mfg.bin'

# sensor_id_t bit positions -- must match
# apps/st/stm32wba/sid_smartac/stm32wle5x/components/sensor_manager/include/sensor_manager/sensor_type.h
SENSOR_ID_TEMP_1 = 0
SENSOR_ID_TEMP_2 = 1
SENSOR_ID_TEMP_3 = 2
SENSOR_ID_TEMP_4 = 3
SENSOR_ID_TEMP_5 = 4
SENSOR_ID_RH_1 = 5
SENSOR_ID_RH_2 = 6
SENSOR_ID_RH_3 = 7
SENSOR_ID_PRESS_1 = 8
SENSOR_ID_PRESS_2 = 9
SENSOR_ID_PRESS_3 = 10

# Internal environmental-sensor IC name -> sensor_id_t bits it activates. Mirrors the probe/create
# calls in sampler_sensor_list_init() (apps/.../sampler/src/sampler_sensor_list.c):
#   LPS22   -> SENSOR_ID_TEMP_1 + SENSOR_ID_PRESS_1 (one lps22 driver; LPS22DF/HH/HB are told apart
#              at runtime, so the part does not change the bits)
#   ENS21X  -> SENSOR_ID_TEMP_2 + SENSOR_ID_RH_1 (any of ENS210/211/212/213/215)
#   SHT4X   -> SENSOR_ID_TEMP_2 + SENSOR_ID_RH_1, the same bits as ENS21X: both are alternative parts
#              for the same board position, the firmware uses SHT4x if it probes, else ENS21x
#   BME69X  -> SENSOR_ID_TEMP_3 + SENSOR_ID_RH_2 + SENSOR_ID_PRESS_2
# Only one name per family: the variants within a family give identical sensor_id_t bits. The order
# here is the order the SMAC MFG station UI lists them in.
# External sensors (2SMPB, SHTC3 -- SENSOR_ID_TEMP_4/_5, RH_3, PRESS_3) have no env_sens_ic_id_t
# entry (see sensor_manager/env_sens_ic_id.h) and are therefore not selectable by IC name here.
IC_SENSOR_BITS = {
    'LPS22': (SENSOR_ID_TEMP_1, SENSOR_ID_PRESS_1),
    'ENS21X': (SENSOR_ID_TEMP_2, SENSOR_ID_RH_1),
    'SHT4X': (SENSOR_ID_TEMP_2, SENSOR_ID_RH_1),
    'BME69X': (SENSOR_ID_TEMP_3, SENSOR_ID_RH_2, SENSOR_ID_PRESS_2),
}


class InvalidLabelError(Exception):
    pass


class InvalidEnvSensorsMapError(Exception):
    pass


class InvalidIcNameError(Exception):
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


def parse_ic_names(ic_names) -> int:
    value = 0

    for name in ic_names:
        key = name.strip().upper()
        bits = IC_SENSOR_BITS.get(key)

        if bits is None:
            valid = ', '.join(sorted(IC_SENSOR_BITS))
            raise InvalidIcNameError(f"'{name}' is not a known IC name. Valid names: {valid}")

        for bit in bits:
            value |= (1 << bit)

    return value


def encode_label(label_str: str) -> bytes:
    match = LABEL_RE.match(label_str)
    if not match:
        raise InvalidLabelError(f"'{label_str}' does not match the expected label form XX-XXXXXX (dash optional, hex digits 0-9/a-f)")

    digits = [int(c, 16) for c in match.group(1) + match.group(2)]
    return bytes((digits[i] << 4) | digits[i + 1] for i in range(0, len(digits), 2))


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    env_sensors_group = parser.add_mutually_exclusive_group()
    env_sensors_group.add_argument('-m', '--env-sensors-map', default=None,
                                   help='Environmental sensors bitmap, in HEX (e.g. "7FF" or "0x7FF"). '
                                        'Left unpopulated (0xFF) if omitted.')
    env_sensors_group.add_argument('-i', '--ics', nargs='+', metavar='IC_NAME', default=None,
                                   help='List of internal environmental-sensor IC names present on the '
                                        'device (see env_sens_ic_id_t), e.g. "-i LPS22 BME69X". Builds '
                                        'the env_sensors_map bitmask from sensor_id_t bit positions. '
                                        'Valid names: ' + ', '.join(sorted(IC_SENSOR_BITS)))

    parser.add_argument('-l', '--label', default=None,
                         help='Device back-label, form XX-XXXXXX or XXXXXXXX (hex digits 0-9/a-f). '
                              'Left unpopulated (0xFF) if omitted.')
    parser.add_argument('-o', '--output', default=str(DEFAULT_OUTPUT),
                         help=f'Output binary file path (default: {DEFAULT_OUTPUT})')

    args = parser.parse_args(argv)

    try:
        if args.ics is not None:
            env_sensors_map = parse_ic_names(args.ics)
        elif args.env_sensors_map is not None:
            env_sensors_map = parse_env_sensors_map(args.env_sensors_map)
        else:
            env_sensors_map = None

        factory_data = build_factory_data(env_sensors_map, args.label)
        assert len(factory_data) == FACTORY_DATA_SIZE

        with open(args.output, 'wb') as f:
            f.write(factory_data)

        if args.ics is not None:
            print('[INFO] ICs             = ' + ', '.join(args.ics))
        print('[INFO] env_sensors_map = ' +
              (f'0x{env_sensors_map:08X}' if env_sensors_map is not None else 'UNPOPULATED (0xFF)'))
        print('[INFO] label           = ' + (args.label if args.label is not None else 'UNPOPULATED (0xFF)'))
        print(f'[INFO] Wrote {len(factory_data)} bytes to {args.output}')
        print(f'[INFO] Flash at address 0x{FACTORY_DATA_ADDRESS:08X} (.factory_data section, '
              f'STM32WLE5CCUX_FLASH.ld)')

    except (InvalidLabelError, InvalidEnvSensorsMapError, InvalidIcNameError) as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
