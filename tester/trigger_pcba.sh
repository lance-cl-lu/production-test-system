#!/usr/bin/env zsh
# Trigger a PCBA test by writing a command to ../shared/pcba_test.txt
# Usage:
#   ./trigger_pcba.sh                # interactive mode
#   ./trigger_pcba.sh <SERIAL> <START|STOP>

set -euo pipefail

SHARED_FILE="$(dirname $0)/../shared/pcba_test.txt"

function usage() {
  echo "Usage: $0 <SERIAL> <START|STOP>"
  echo "Or run without args for interactive mode."
}

serial="${1:-}"
action="${2:-}"

if [[ -z "$serial" || -z "$action" ]]; then
  echo "Interactive mode:"
  read -r "serial?Enter SERIAL: "
  read -r "action?Enter ACTION (START/STOP): "
fi

action_upper=$(echo "$action" | tr '[:lower:]' '[:upper:]')
if [[ "$action_upper" != "START" && "$action_upper" != "STOP" ]]; then
  echo "Error: ACTION must be START or STOP"
  usage
  exit 1
fi

cmd="SERIAL ${serial} ${action_upper}"

echo "$cmd" > "$SHARED_FILE"
# ensure mtime updates even if content happens to be identical
/usr/bin/touch "$SHARED_FILE"

echo "Triggered: $cmd"
echo "Written to: $SHARED_FILE"
