#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"

case "${MODE}" in
  hvf)
    WBA_ELF_FILE="${ROOT_DIR}/hvf/smac_stm32wba5.elf"
    SECOND_ELF_FILE="${ROOT_DIR}/hvf/smac_fw.elf"
    SECOND_NAME="WLE"
    SECOND_ID_NAME="WLE"
    WBA_BOOT_FILE=""
    SECOND_BOOT_FILE=""
    ;;
  diagnostics)
    WBA_ELF_FILE="${ROOT_DIR}/diagnostics/sid_diagnostics_stm32wba55.elf"
    SECOND_ELF_FILE="${ROOT_DIR}/diagnostics/sid_diagnostics_stm32wl55.elf"
    SECOND_NAME="WL"
    SECOND_ID_NAME="WL"
    WBA_BOOT_FILE=""
    SECOND_BOOT_FILE=""
    ;;
  smac_prod)
    WBA_BOOT_FILE="${ROOT_DIR}/fwpack/bootloaders/wba_boot.elf"
    WBA_ELF_FILE="${ROOT_DIR}/fwpack/app_with_logs/sid_smartac_stm32wba5m.elf"
    SECOND_BOOT_FILE="${ROOT_DIR}/fwpack/bootloaders/wle_boot.elf"
    SECOND_ELF_FILE="${ROOT_DIR}/fwpack/app_with_logs/sid_smartac_stm32wle5.elf"
    SECOND_NAME="WLE"
    SECOND_ID_NAME="WLE"
    ;;
  smac_debug)
    WBA_BOOT_FILE="${ROOT_DIR}/fwpack/bootloaders/wba_boot.elf"
    WBA_ELF_FILE="${ROOT_DIR}/fwpack/app_no_logs/sid_smartac_stm32wba5m.elf"
    SECOND_BOOT_FILE="${ROOT_DIR}/fwpack/bootloaders/wle_boot.elf"
    SECOND_ELF_FILE="${ROOT_DIR}/fwpack/app_no_logs/sid_smartac_stm32wle5.elf"
    SECOND_NAME="WLE"
    SECOND_ID_NAME="WLE"
    ;;
  *)
    echo "Usage: $0 {hvf|diagnostics|smac_prod|smac_debug}" >&2
    exit 2
    ;;
esac

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

for firmware in "${WBA_BOOT_FILE}" "${WBA_ELF_FILE}" "${SECOND_BOOT_FILE}" "${SECOND_ELF_FILE}"; do
  if [[ -n "${firmware}" && ! -f "${firmware}" ]]; then
    echo "Firmware not found: ${firmware}" >&2
    exit 1
  fi
done

CLI="$(find_programmer)"
LIST_OUTPUT="$("${CLI}" -l st-link-only 2>&1 | sed $'s/\033\\[[0-9;]*[[:alpha:]]//g')" || {
  echo "Failed to enumerate ST-Link probes:" >&2
  echo "${LIST_OUTPUT}" >&2
  exit 1
}

PROBE_COUNT="$(grep -Eic 'ST-LINK SN|STLink SN' <<<"${LIST_OUTPUT}" || true)"
if [[ "${PROBE_COUNT}" -eq 0 ]] || grep -qi 'No ST-Link detected' <<<"${LIST_OUTPUT}"; then
  echo "No ST-Link probes detected." >&2
  exit 1
fi

WBA_INDEX=""
WLE_INDEX=""
WBA_INFO=""
FLASH_WBA=1
FLASH_WLE=1

if [[ "${PROBE_COUNT}" -eq 1 && ( "${MODE}" == "hvf" || "${MODE}" == "diagnostics" ) ]]; then
  INFO="$("${CLI}" -c "port=SWD index=0" 2>&1 | sed $'s/\033\\[[0-9;]*[[:alpha:]]//g' || true)"
  if grep -Eqi 'STM32WBA5|STM32WBA55' <<<"${INFO}"; then
    WBA_INDEX=0
    WBA_INFO="${INFO}"
    FLASH_WLE=0
    TARGET_NAME="WBA"
    TARGET_INDEX="${WBA_INDEX}"
  elif grep -Eqi 'STM32WL' <<<"${INFO}"; then
    WLE_INDEX=0
    FLASH_WBA=0
    TARGET_NAME="${SECOND_NAME}"
    TARGET_INDEX="${WLE_INDEX}"
  else
    echo "Could not identify the MCU connected to the only ST-Link; aborting." >&2
    echo "CubeProgrammer connection output:" >&2
    echo "${INFO}" >&2
    exit 1
  fi
  echo "Detected one ST-Link connected to ${TARGET_NAME} (index ${TARGET_INDEX}):"
  grep -Ei 'Device name|Device ID|Revision ID|STM32WBA|STM32WL' <<<"${INFO}" | head -10 || true
elif [[ "${PROBE_COUNT}" -eq 2 ]]; then
  for index in 0 1; do
    INFO="$("${CLI}" -c "port=SWD index=${index}" 2>&1 | sed $'s/\033\\[[0-9;]*[[:alpha:]]//g' || true)"
    if grep -Eqi 'STM32WBA5|STM32WBA55' <<<"${INFO}"; then
      if [[ -n "${WBA_INDEX}" ]]; then
        echo "Multiple WBA targets found (indices ${WBA_INDEX} and ${index}); aborting to avoid flashing the wrong target." >&2
        exit 1
      fi
      WBA_INDEX="${index}"
      WBA_INFO="${INFO}"
    fi
  done

  if [[ -z "${WBA_INDEX}" ]]; then
    echo "No connectable STM32WBA5 target found on either ST-Link; aborting." >&2
    exit 1
  fi
  if [[ "${WBA_INDEX}" -eq 0 ]]; then
    WLE_INDEX=1
  else
    WLE_INDEX=0
  fi
  echo "WBA target found on ST-Link index ${WBA_INDEX}:"
  grep -Ei 'Device name|Device ID|Revision ID|STM32WBA' <<<"${WBA_INFO}" | head -10 || true
  echo "The other ST-Link (index ${WLE_INDEX}) will be used for ${SECOND_NAME}."
else
  echo "Expected one or two ST-Link probes, found ${PROBE_COUNT}." >&2
  echo "CubeProgrammer enumeration output:" >&2
  echo "${LIST_OUTPUT}" >&2
  exit 1
fi

read_uid() {
  local name="$1" index="$2" address="$3" output uid
  echo "Reading ${name} MCU ID..."
  output="$("${CLI}" -q -c "port=SWD index=${index}" -r32 "${address}" 12 2>&1)" || {
    echo "Failed to read ${name} MCU ID:" >&2
    echo "${output}" >&2
    return 1
  }
  uid="$(sed -nE 's/^0[xX][[:xdigit:]]{8}[[:space:]]*:[[:space:]]*//p' <<<"${output}" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  if [[ ! "${uid}" =~ ^[[:xdigit:]]{24}$ ]]; then
    echo "Could not parse the ${name} MCU ID from CubeProgrammer output:" >&2
    echo "${output}" >&2
    return 1
  fi
  echo "${name}_ID=${uid}"
}

# The WBA5 UID starts at DESIG_UIDR1; the WL-family UID is in system memory.
if [[ "${FLASH_WBA}" -eq 1 ]]; then
  if ! read_uid WBA "${WBA_INDEX}" 0x0BF90500; then
    if [[ "${PROBE_COUNT}" -eq 1 && ( "${MODE}" == "hvf" || "${MODE}" == "diagnostics" ) ]]; then
      echo "Warning: WBA ID read failed; continuing with the detected WBA flash." >&2
    else
      exit 1
    fi
  fi
fi
if [[ "${FLASH_WLE}" -eq 1 ]]; then
  if ! read_uid "${SECOND_ID_NAME}" "${WLE_INDEX}" 0x1FFF7590; then
    if [[ "${PROBE_COUNT}" -eq 1 && ( "${MODE}" == "hvf" || "${MODE}" == "diagnostics" ) ]]; then
      echo "Warning: ${SECOND_NAME} ID read failed; continuing with the detected ${SECOND_NAME} flash." >&2
    else
      exit 1
    fi
  fi
fi

flash_elf() {
  local target_name="$1" index="$2" firmware="$3"
  echo "Flashing ${target_name}: ${firmware}"
  "${CLI}" -c "port=SWD index=${index}" -w "${firmware}" -v -rst || {
    echo "${target_name} flash failed; stopping." >&2
    exit 1
  }
  echo "${target_name} flash completed: ${firmware}"
}

if [[ "${FLASH_WBA}" -eq 1 ]]; then
  if [[ -n "${WBA_BOOT_FILE}" ]]; then
    flash_elf WBA "${WBA_INDEX}" "${WBA_BOOT_FILE}"
  fi
  flash_elf WBA "${WBA_INDEX}" "${WBA_ELF_FILE}"
fi
if [[ "${FLASH_WLE}" -eq 1 ]]; then
  if [[ -n "${SECOND_BOOT_FILE}" ]]; then
    flash_elf "${SECOND_NAME}" "${WLE_INDEX}" "${SECOND_BOOT_FILE}"
  fi
  flash_elf "${SECOND_NAME}" "${WLE_INDEX}" "${SECOND_ELF_FILE}"
fi
