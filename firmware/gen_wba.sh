#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

arm-none-eabi-objcopy -O ihex wba_boot.elf wba_boot.hex
arm-none-eabi-objcopy -O ihex wba_app.elf wba_app.hex

srec_cat \
    wba_boot.hex -Intel \
    wba_app.hex -Intel \
    mfg.bin -Binary -offset 0x080FE000 \
    -o wba_combined.hex -Intel

srec_info wba_combined.hex -Intel
