#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

arm-none-eabi-objcopy -O ihex wle_boot.elf wle_boot.hex
arm-none-eabi-objcopy -O ihex wle_app.elf wle_app.hex

srec_cat \
    wle_boot.hex -Intel \
    wle_app.hex -Intel \
    -o wle_combined.hex -Intel

srec_info wle_combined.hex -Intel
