#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_FRAMES_DIR="$PROJECT_ROOT/app_frames"
BOOTLOADER="$PROJECT_ROOT/fwpack/bootloaders/wle_boot.elf"
APPLICATION="$SCRIPT_DIR/sid_smartac_stm32wle5.elf"
SERIAL_FILE="${1:-$SCRIPT_DIR/serial_num.txt}"
MFG_SOURCE="$APP_FRAMES_DIR/smac_mfg.bin"
MFG_LOCAL="$SCRIPT_DIR/smac_mfg.bin"

if [[ ! -f "$SERIAL_FILE" ]]; then
    echo "[ERROR] Serial number file not found: $SERIAL_FILE" >&2
    exit 1
fi

for required_file in \
    "$APP_FRAMES_DIR/gen_smac_mfg.py" \
    "$SCRIPT_DIR/combine_binaries.py" \
    "$APPLICATION" \
    "$BOOTLOADER"; do
    if [[ ! -f "$required_file" ]]; then
        echo "[ERROR] Required file not found: $required_file" >&2
        exit 1
    fi
done

normalize_serial() {
    printf '%s' "$1" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]'
}

# Validate the complete file before generating anything, so an invalid line
# cannot leave behind a partially completed batch.
SERIAL_COUNT=0
LINE_NUMBER=0
while IFS= read -r RAW_SERIAL || [[ -n "$RAW_SERIAL" ]]; do
    LINE_NUMBER=$((LINE_NUMBER + 1))
    SERIAL_NUMBER="$(normalize_serial "$RAW_SERIAL")"
    [[ -z "$SERIAL_NUMBER" ]] && continue

    if [[ ! "$SERIAL_NUMBER" =~ ^[0-9A-F]{8}$ ]]; then
        echo "[ERROR] Invalid serial number on line $LINE_NUMBER: $SERIAL_NUMBER" >&2
        echo "[ERROR] Each serial number must contain exactly 8 hexadecimal characters." >&2
        exit 1
    fi
    SERIAL_COUNT=$((SERIAL_COUNT + 1))
done < "$SERIAL_FILE"

if [[ "$SERIAL_COUNT" -eq 0 ]]; then
    echo "[ERROR] No serial numbers found in: $SERIAL_FILE" >&2
    exit 1
fi

cd "$SCRIPT_DIR"

GENERATED_COUNT=0
while IFS= read -r RAW_SERIAL || [[ -n "$RAW_SERIAL" ]]; do
    SERIAL_NUMBER="$(normalize_serial "$RAW_SERIAL")"
    [[ -z "$SERIAL_NUMBER" ]] && continue
    OUTPUT="$SCRIPT_DIR/${SERIAL_NUMBER}_wle.hex"

    echo "[INFO] Serial number: $SERIAL_NUMBER"

    python3 "$APP_FRAMES_DIR/gen_smac_mfg.py" \
        -m 0x266 \
        -l "$SERIAL_NUMBER" \
        -o "$MFG_SOURCE"

    cp "$MFG_SOURCE" "$MFG_LOCAL"
    echo "[INFO] Copied manufacturing data to $MFG_LOCAL"

    python3 combine_binaries.py \
        -o "$OUTPUT" \
        "$APPLICATION" \
        "$BOOTLOADER" \
        "$MFG_LOCAL" 0x0803F800

    GENERATED_COUNT=$((GENERATED_COUNT + 1))
    echo "[SUCCESS] Firmware generated: $OUTPUT"
done < "$SERIAL_FILE"

echo "[SUCCESS] Generated $GENERATED_COUNT firmware file(s)."
