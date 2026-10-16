#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW_DIR="${ROOT_DIR}/fwpack-special"
WBA_BOOT="${FW_DIR}/wba_boot.hex"
WBA_APP="${FW_DIR}/wba_app.hex"
WLE_BOOT="${FW_DIR}/wle_boot.hex"
WLE_APP="${FW_DIR}/wle_app.hex"
INTERTEK_BIN="${FW_DIR}/intertek001.bin"
INTERTEK_ADDRESS="0x080FE000"

find_programmer() {
  local candidate
  for candidate in \
    "${STM32_PROGRAMMER_CLI:-}" \
    "/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI" \
    "/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.macos64_2.2.300.202508131133/tools/bin/STM32_Programmer_CLI"; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
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

for firmware in "${WBA_BOOT}" "${WBA_APP}" "${WLE_BOOT}" "${WLE_APP}" "${INTERTEK_BIN}"; do
  if [[ ! -f "${firmware}" ]]; then
    echo "Firmware file not found: ${firmware}" >&2
    exit 1
  fi
done

CLI="$(find_programmer)"
if ! LIST_OUTPUT="$("${CLI}" -l st-link-only 2>&1 | sed $'s/\033\\[[0-9;]*[[:alpha:]]//g')"; then
  echo "Failed to enumerate ST-Link probes." >&2
  exit 1
fi

if grep -qi 'No ST-Link detected' <<<"${LIST_OUTPUT}"; then
  echo "No ST-Link probes detected. Connect the WBA and WLE probes and try again." >&2
  exit 1
fi

PROBE_COUNT="$(grep -Eic 'ST-LINK SN|STLink SN' <<<"${LIST_OUTPUT}" || true)"
if [[ "${PROBE_COUNT}" -ne 2 ]]; then
  echo "Expected exactly two ST-Link probes, found ${PROBE_COUNT}." >&2
  echo "CubeProgrammer enumeration output:" >&2
  echo "${LIST_OUTPUT}" >&2
  exit 1
fi

WBA_INDEX=""
PROBE_INFO_0=""
PROBE_INFO_1=""
for index in 0 1; do
  INFO="$("${CLI}" -c "port=SWD index=${index}" 2>&1 | sed $'s/\033\\[[0-9;]*[[:alpha:]]//g' || true)"
  if [[ "${index}" -eq 0 ]]; then
    PROBE_INFO_0="${INFO}"
  else
    PROBE_INFO_1="${INFO}"
  fi
  if grep -Eqi 'STM32WBA5|STM32WBA55' <<<"${INFO}"; then
    if [[ -n "${WBA_INDEX}" ]]; then
      echo "Multiple WBA targets found; aborting." >&2
      exit 1
    fi
    WBA_INDEX="${index}"
    WBA_INFO="${INFO}"
  fi
done

if [[ -z "${WBA_INDEX}" ]]; then
  echo "Could not identify a WBA target; aborting." >&2
  echo "WBA index: not found" >&2
  exit 1
fi

if [[ "${WBA_INDEX}" -eq 0 ]]; then
  WLE_INDEX=1
  WLE_INFO="${PROBE_INFO_1}"
else
  WLE_INDEX=0
  WLE_INFO="${PROBE_INFO_0}"
fi

if ! grep -Eqi 'Device ID[[:space:]]*:' <<<"${WLE_INFO}"; then
  echo "The other ST-Link (index ${WLE_INDEX}) did not report a connected MCU; aborting." >&2
  echo "WBA index: ${WBA_INDEX}; WLE index: ${WLE_INDEX} (connection not confirmed)" >&2
  exit 1
fi

echo "WBA target found on ST-Link index ${WBA_INDEX}:"
grep -Ei 'Device name|Device ID|Revision ID' <<<"${WBA_INFO}" | head -10 || true
echo "The other connected target will be used as WLE on ST-Link index ${WLE_INDEX}:"
grep -Ei 'Device name|Device ID|Revision ID' <<<"${WLE_INFO}" | head -10 || true

write_file() {
  local target_name="$1" index="$2" file="$3" address="${4:-}"
  echo "Flashing ${target_name}: ${file}${address:+ at ${address}}"
  if [[ -n "${address}" ]]; then
    "${CLI}" -c "port=SWD index=${index}" -w "${file}" "${address}" -v || {
      echo "Failed to flash ${file} to ${target_name}; stopping." >&2
      exit 1
    }
  else
    "${CLI}" -c "port=SWD index=${index}" -w "${file}" -v || {
      echo "Failed to flash ${file} to ${target_name}; stopping." >&2
      exit 1
    }
  fi
  echo "Completed: ${file}"
}

reset_target() {
  local target_name="$1" index="$2"
  echo "Resetting ${target_name} target..."
  "${CLI}" -c "port=SWD index=${index}" -rst || {
    echo "Failed to reset ${target_name} target." >&2
    exit 1
  }
}

write_file WBA "${WBA_INDEX}" "${WBA_BOOT}"
write_file WBA "${WBA_INDEX}" "${WBA_APP}"
write_file WBA "${WBA_INDEX}" "${INTERTEK_BIN}" "${INTERTEK_ADDRESS}"
reset_target WBA "${WBA_INDEX}"
write_file WLE "${WLE_INDEX}" "${WLE_BOOT}"
write_file WLE "${WLE_INDEX}" "${WLE_APP}"
reset_target WLE "${WLE_INDEX}"

echo "Special firmware flashing completed."
