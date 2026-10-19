mnv@31052322
python3 gen_smac_mfg.py -m 0x266 -l 15000148
python3 ./sid_fwtool.py --upload SID ./factory_sid.bin /dev/tty.usbserial-1120 
python3 combine_binaries.py sid_smartac_stm32wle5.elf ../bootloaders/wle_boot.elf smac_mfg.bin 0x0803F800

flash_smac.sh hvf
./sensor_watcher --port /dev/tty.usbserial-0001 --port2 /dev/tty.usbserial-A5069RR4 --debug

anjie
aj54122064

ctrl_interface=/var/run/wpa_supplicant
update_config=1

cat << 'EOF' > wpa.conf
ctrl_interface=/var/run/wpa_supplicant
update_config=1
network={
        ssid="anjie"
        psk="aj54122064"
        key_mgmt=WPA-PSK
}
EOF


140A0283A128