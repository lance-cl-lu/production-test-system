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
    ;;
  diagnostics)
    WBA_ELF_FILE="${ROOT_DIR}/diagnostics/sid_diagnostics_stm32wba55.elf"
    SECOND_ELF_FILE="${ROOT_DIR}/diagnostics/sid_diagnostics_stm32wl55.elf"
    SECOND_NAME="WL"
    SECOND_ID_NAME="WL"
    ;;
  *)
    echo "Usage: $0 {hvf|diagnostics}" >&2
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

if [[ ! -f "${WBA_ELF_FILE}" ]]; then
  echo "Firmware not found: ${WBA_ELF_FILE}" >&2
  exit 1
fi
if [[ ! -f "${SECOND_ELF_FILE}" ]]; then
  echo "Firmware not found: ${SECOND_ELF_FILE}" >&2
  exit 1
fi

CLI="$(find_programmer)"
LIST_OUTPUT="$("${CLI}" -l st-link-only 2>&1 | sed $'s/\033\\[[0-9;]*[[:alpha:]]//g')" || {
  echo "Failed to enumerate ST-Link probes:" >&2
  echo "${LIST_OUTPUT}" >&2
  exit 1
}

# Probe indices are assigned by CubeProgrammer. Require exactly two probes,
# identify the WBA by its device name, and use the other probe for the selected mode.
if ! grep -qi 'STLink Interface\|ST-Link Interface' <<<"${LIST_OUTPUT}" || grep -qi 'No ST-Link detected' <<<"${LIST_OUTPUT}"; then
  echo "No ST-Link probes detected. Connect both probes and try again." >&2
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
WBA_INFO=""
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

# The WBA5 96-bit UID starts at DESIG_UIDR1; the WLE5 UID is in system memory.
read_uid WBA "${WBA_INDEX}" 0x0BF90500 || exit 1
read_uid "${SECOND_ID_NAME}" "${WLE_INDEX}" 0x1FFF7590 || exit 1

echo "Flashing WBA: ${WBA_ELF_FILE}"
"${CLI}" -c "port=SWD index=${WBA_INDEX}" -w "${WBA_ELF_FILE}" -v -rst || {
  echo "WBA flash failed; stopping." >&2
  exit 1
}
echo "WBA flash completed."

echo "Flashing ${SECOND_NAME}: ${SECOND_ELF_FILE}"
"${CLI}" -c "port=SWD index=${WLE_INDEX}" -w "${SECOND_ELF_FILE}" -v -rst || {
  echo "${SECOND_NAME} flash failed." >&2
  exit 1
}
echo "${SECOND_NAME} flash completed."
