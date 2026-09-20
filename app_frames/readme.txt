mnv@31052322
python3 gen_smac_mfg.py -m 0x266 -l 15000148
python3 ./sid_fwtool.py --upload SID ./factory_sid.bin /dev/tty.usbserial-1120 
python3 combine_binaries.py sid_smartac_stm32wle5.elf ../bootloaders/wle_boot.elf smac_mfg.bin 0x0803F800