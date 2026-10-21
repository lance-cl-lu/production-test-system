#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_CONFIRM=0

usage() {
  cat <<EOF
Usage: $0 [--yes]

Automatically identify connected STM32WBA and STM32WL/WLE targets through
STM32CubeProgrammer, then flash the matching bootloader and application files
from this directory. With one ST-Link, only its detected MCU is flashed.
Connection detection retries at a lower SWD frequency and under-reset mode.

Options:
  --yes   Skip the confirmation prompt.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y)
      AUTO_CONFIRM=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

WBA_BOOT="${SCRIPT_DIR}/wba_boot_release.hex"
WBA_APP="${SCRIPT_DIR}/wba_app_release_no_ble.hex"
WLE_BOOT="${SCRIPT_DIR}/wle_boot_release_hw_2_0_3.hex"
WLE_APP="${SCRIPT_DIR}/wle_app_release_logs_hw_2_0_3.hex"
INTERTEK_BIN="${SCRIPT_DIR}/../fwpack-special/intertek002.bin"
INTERTEK_ADDRESS="0x080FE000"

for firmware in "$WBA_BOOT" "$WBA_APP" "$WLE_BOOT" "$WLE_APP" "$INTERTEK_BIN"; do
  if [[ ! -s "$firmware" ]]; then
    echo "Firmware file is missing or empty: $firmware" >&2
    exit 1
  fi
done

find_programmer() {
  local candidate
  for candidate in \
    "${STM32_PROGRAMMER_CLI:-}" \
    "/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI" \
    "/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.macos64_2.2.300.202508131133/tools/bin/STM32_Programmer_CLI"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  if command -v STM32_Programmer_CLI >/dev/null 2>&1; then
    command -v STM32_Programmer_CLI
    return 0
  fi
  echo "STM32_Programmer_CLI not found. Install STM32CubeProgrammer or set STM32_PROGRAMMER_CLI." >&2
  return 1
}

CLI="$(find_programmer)"
LIST_OUTPUT="$("$CLI" -l st-link-only 2>&1 | sed $'s/\\033\\[[0-9;]*[[:alpha:]]//g')" || {
  echo "Failed to enumerate ST-Link probes:" >&2
  echo "$LIST_OUTPUT" >&2
  exit 1
}

PROBE_COUNT="$(grep -Eic 'ST-LINK SN|STLink SN' <<<"$LIST_OUTPUT" || true)"
if [[ "$PROBE_COUNT" -lt 1 || "$PROBE_COUNT" -gt 2 ]] || grep -qi 'No ST-Link detected' <<<"$LIST_OUTPUT"; then
  echo "Expected one or two ST-Link probes; found $PROBE_COUNT. No firmware was flashed." >&2
  echo "$LIST_OUTPUT" >&2
  exit 1
fi

echo "Detected $PROBE_COUNT ST-Link probe(s)."
WBA_INDEX=""
WLE_INDEX=""
PROBE_OPTIONS_0=""
PROBE_OPTIONS_1=""
SWD_FREQ="${STM32_SWD_FREQ:-1000}"

probe_target() {
  local index="$1" options output
  for options in "freq=${SWD_FREQ}" "mode=UR freq=${SWD_FREQ}"; do
    output="$("$CLI" -c "port=SWD index=${index} ${options}" 2>&1 | sed $'s/\\033\\[[0-9;]*[[:alpha:]]//g' || true)"
    if grep -Eqi 'STM32WBA5' <<<"$output" || \
      { grep -Eqi 'STM32(WLE5|WLxx)' <<<"$output" && grep -Eqi 'Device ID[[:space:]]*:[[:space:]]*0x0*497([[:space:]]|$)' <<<"$output"; }; then
      INFO="$output"
      CONNECTION_OPTIONS="$options"
      return 0
    fi
  done
  INFO="$output"
  return 1
}

connection_options() {
  case "$1" in
    0) printf '%s' "$PROBE_OPTIONS_0" ;;
    1) printf '%s' "$PROBE_OPTIONS_1" ;;
    *) return 1 ;;
  esac
}

for index in 0 1; do
  [[ "$index" -lt "$PROBE_COUNT" ]] || continue
  if ! probe_target "$index"; then
    echo "Could not connect to a supported MCU on ST-Link index $index, even at ${SWD_FREQ} kHz or under reset." >&2
    echo "$INFO" >&2
    exit 1
  fi
  if [[ "$index" -eq 0 ]]; then
    PROBE_OPTIONS_0="$CONNECTION_OPTIONS"
  else
    PROBE_OPTIONS_1="$CONNECTION_OPTIONS"
  fi
  if grep -Eqi 'STM32WBA5' <<<"$INFO"; then
    if [[ -n "$WBA_INDEX" ]]; then
      echo "Multiple WBA targets found; refusing to guess. No firmware was flashed." >&2
      exit 1
    fi
    WBA_INDEX="$index"
    echo "ST-Link index $index: WBA"
    grep -Ei 'Device name|Device ID|Revision ID|STM32WBA' <<<"$INFO" | head -10 || true
  elif { grep -Eqi 'STM32WLE5' <<<"$INFO" || grep -Eqi 'STM32WLxx' <<<"$INFO"; } &&
    grep -Eqi 'Device ID[[:space:]]*:[[:space:]]*0x0*497([[:space:]]|$)' <<<"$INFO"; then
    if [[ -n "$WLE_INDEX" ]]; then
      echo "Multiple WL/WLE targets found; refusing to guess. No firmware was flashed." >&2
      exit 1
    fi
    WLE_INDEX="$index"
    echo "ST-Link index $index: WLE-compatible target (Device ID 0x497)"
    grep -Ei 'Device name|Device ID|Revision ID|STM32WL' <<<"$INFO" | head -10 || true
  else
    echo "Unsupported MCU on ST-Link index $index; only STM32WBA5 and STM32WLE5 are supported." >&2
    echo "$INFO" >&2
    exit 1
  fi
done

if [[ -z "$WBA_INDEX" && -z "$WLE_INDEX" ]]; then
  echo "No supported WBA or WLE target was identified. No firmware was flashed." >&2
  exit 1
fi

printf '\nFirmware plan:\n'
if [[ -n "$WBA_INDEX" ]]; then
  printf '  WBA (ST-Link %s): %s, then %s, then %s at %s\n' \
    "$WBA_INDEX" "$(basename "$WBA_BOOT")" "$(basename "$WBA_APP")" \
    "$(basename "$INTERTEK_BIN")" "$INTERTEK_ADDRESS"
fi
if [[ -n "$WLE_INDEX" ]]; then
  printf '  WLE (ST-Link %s): %s, then %s\n' "$WLE_INDEX" "$(basename "$WLE_BOOT")" "$(basename "$WLE_APP")"
fi

if [[ "$AUTO_CONFIRM" -ne 1 ]]; then
  if [[ ! -t 0 ]]; then
    echo "Refusing to flash without an interactive confirmation. Re-run with --yes to proceed." >&2
    exit 2
  fi
  printf '\nThis will overwrite firmware on the detected target(s). Continue? [y/N] '
  read -r answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "Cancelled. No firmware was flashed."; exit 0 ;;
  esac
fi

flash_hex() {
  local name="$1" index="$2" firmware="$3" options
  options="$(connection_options "$index")"
  echo "Flashing ${name} using ST-Link index ${index}: $(basename "$firmware")"
  if ! "$CLI" -c "port=SWD index=${index} ${options}" -w "$firmware" -v; then
    echo "${name} flash failed; stopping immediately." >&2
    exit 1
  fi
  echo "${name} flash completed: $(basename "$firmware")"
}

reset_target() {
  local name="$1" index="$2" options
  options="$(connection_options "$index")"
  echo "Resetting ${name} target..."
  if ! "$CLI" -c "port=SWD index=${index} ${options}" -rst; then
    echo "Failed to reset ${name} target." >&2
    exit 1
  fi
}

# Flash each detected MCU's bootloader before its application. No other target is guessed.
if [[ -n "$WBA_INDEX" ]]; then
  flash_hex WBA "$WBA_INDEX" "$WBA_BOOT"
  flash_hex WBA "$WBA_INDEX" "$WBA_APP"
  options="$(connection_options "$WBA_INDEX")"
  echo "Flashing WBA using ST-Link index ${WBA_INDEX}: $(basename "$INTERTEK_BIN") at ${INTERTEK_ADDRESS}"
  if ! "$CLI" -c "port=SWD index=${WBA_INDEX} ${options}" -w "$INTERTEK_BIN" "$INTERTEK_ADDRESS" -v; then
    echo "WBA Intertek data flash failed; stopping immediately." >&2
    exit 1
  fi
  echo "WBA Intertek data flash completed: $(basename "$INTERTEK_BIN")"
  reset_target WBA "$WBA_INDEX"
fi
if [[ -n "$WLE_INDEX" ]]; then
  flash_hex WLE "$WLE_INDEX" "$WLE_BOOT"
  flash_hex WLE "$WLE_INDEX" "$WLE_APP"
  reset_target WLE "$WLE_INDEX"
fi

echo "Firmware flashing completed successfully."
