#!/usr/bin/env zsh

# 模擬 PCBA 測試：依序送出五個階段的事件到後端
# 用法：./run_pcba_demo.sh <serial>
# 例： ./run_pcba_demo.sh NL20231203001

set -euo pipefail

serial=${1:-}
if [[ -z "$serial" ]]; then
  echo "Usage: $0 <serial>"
  exit 1
fi

API="http://localhost:8000/api/pcba/events"

send() {
  local stage="$1"; shift
  local state="$1"; shift
  local detail_json="${1:-}"; shift || true

  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  local payload
  if [[ -n "$detail_json" ]]; then
    payload=$(printf '{"serial":"%s","stage":"%s","status":"%s","detail":%s,"timestamp":"%s"}' "$serial" "$stage" "$state" "$detail_json" "$ts")
  else
    payload=$(printf '{"serial":"%s","stage":"%s","status":"%s","timestamp":"%s"}' "$serial" "$stage" "$state" "$ts")
  fi

  echo "$payload" | curl -sS -X POST "$API" -H "Content-Type: application/json" -d @-
}

# wifi
send wifi testing '{"rssi":-55}'
sleep 1
send wifi pass   '{"rssi":-45}'

# firmware
send firmware testing '{"version":"checking"}'
sleep 1
send firmware pass   '{"version":"1.2.7"}'

# touch
send touch testing '{"progress":50}'
sleep 1
# 隨機 pass/fail
if (( RANDOM % 5 )); then
  send touch pass   '{"passed":3,"total":3}'
else
  send touch fail   '{"passed":2,"total":3}'
fi

# bluetooth
send bluetooth testing '{"rssi":-60}'
sleep 1
send bluetooth pass   '{"rssi":-48}'

# speaker
send speaker testing '{"spl_db":75}'
sleep 1
send speaker pass   '{"spl_db":82}'

echo "Done: $serial"
