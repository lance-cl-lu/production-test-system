# sid_secure_prog

Production step for a sid_smartac device: writes static WLE and WBA images while keeping the device's data, checks the WBA bootloader's view of the sign key and the factory containers, burns the sign key into WBA OTP, checks the boot again and locks both MCUs at RDP level 1. It is the backend of the `SID secure programming` [run_ui](../../README.md) station.

**Steps 6 (OTP) and 8 (RDP) cannot be undone.** OTP is write-once. Going from RDP level 1 back to 0 mass-erases the MCU, including the Sidewalk registration, the Sidewalk and SMAC mfg data and NVM. Both steps run only after every earlier step passed. Try new images and keys on a bench board with `--no-rdp` first.

## Setup

- Two ST-Links, one per MCU, with NRST wired. Each ST-Link's virtual COM port is on its MCU's log UART (WBA USART1, WLE USART2, 115200), as for [sid_reg_wait](../sid_reg_wait/README.md).
- `pip install -r smac_tools/run_ui/requirements.txt` for pyserial and PyNaCl.
- **STM32CubeProgrammer must be patched for WBA OTP writes.** In `Data_Base/STM32_Prog_DB_0x492.xml`, next to `bin/STM32_Programmer_CLI`, the block with `address="0x0BF90000"` (512 Bytes Data OTP) has `<Alignment>0x4</Alignment>`. Change it to `0x10`. With 0x4 the CLI splits writes inside a 16-byte OTP line and leaves it half-programmed. A CubeProgrammer update reverts the patch. The tool checks the value and stops before touching the device if it is not 0x10.

## Inputs

```sh
smac_tools/run_ui/tools/sid_secure_prog/sid_secure_prog.py \
    --wle-boot wle_boot.hex --wle-app wle_app.hex --wba-boot wba_boot.hex --wba-app wba_app.hex \
    --sign-key sign_key_pub.pem --ext-flash spi_flash_factory.bin
```

| Option | Meaning |
| --- | --- |
| `--wle-boot`, `--wle-app FILE` | WLE bootloader and app (.hex or .elf). Merged by the station; the data must lie below 0x0803E800. |
| `--wba-boot`, `--wba-app FILE` | WBA bootloader and app (.hex or .elf). Merged by the station; the data must lie below 0x080EA000. The app must be signed with the sign key. |
| `--sign-key KEY` | Ed25519 public key: a key file with an `ED25519 PUBLIC KEY` block (as made by the signing tools), or 64 hex digits. |
| `--ext-flash BIN` | The external-flash (SPI NOR) factory image, as made by `smac_tools/container/spi_flash_image.py`, i.e. what is already in the device's SPI NOR. |
| `--app-window S` | Seconds of app log checked after the final boot (default 10). |
| `--boot-timeout S` | Seconds to wait for the app to start after each reset (default 30). |
| `--wle-sn`, `--wba-sn`, `--wba-port`, `--wle-port`, `--mode`, `--freq`, `--cli` | As in stflash / sid_reg_wait. ST-Links and ports are found automatically. |
| `--check-only` | Only step 1. No hardware needed, useful when setting up a station. |
| `--no-rdp` | Skip step 8 (bench use). OTP is still written. |

## Steps

Each step prints `[INFO] [STEP n/8] ...`. The first failure prints `[ERROR] <reason>` and exits with 1. [SEQUENCE.md](SEQUENCE.md) walks through the station's sequence step by step, including what each step expects in the boot log and a checklist for the first run.

1. **Offline checks.**
   - Each MCU's bootloader and app are merged into one image with [combine_binaries](../combine_binaries/README.md), and its memory map is printed. Overlapping files are refused.
   - Both images stay inside the area that is erased.
   - The WBA image has a bootloader at 0x08000000 and an app OTA header at 0x08012188.
   - The app's footer signature verifies with the key.
   - The app's validity marker address (from the header) is a free flash word in the erased area.
   - Both factory containers in the SPI NOR image pass the bootloader's header and CRC checks and verify with the key. Their signatures are what step 5 expects. Their versions are printed.
   - The installed container version for step 4 (WBA app version + WLE app version) can be computed, and its metadata lines are free.
   - The SID factory container's version equals that installed version, i.e. the SPI NOR image's SID container was built from the apps being programmed (as `container.py` sets its version). Otherwise the run stops: the bootloader compares the two versions when it decides whether to reinstall the factory container.
   - The WLE app inside the SID factory container is for the same hardware as the WLE app being programmed: the `verhw` (SMAC_HW_VERSION) of both info blocks is equal. The hw_2_0_2 and hw_2_0_3 builds share a firmware version and differ only in this.
   - CubeProgrammer's OTP alignment is 0x10.
2. **ST-Links.** Matches the two ST-Links to the WLE and WBA. Both RDP option bytes must be 0xAA (level 0); a locked device stops here.
3. **WLE.** Erases pages 0..124 (up to NVM_STORAGE at 0x0803E800), then writes and verifies the image in one CLI run. NVM_STORAGE and PERMANENT_DATA (the SMAC mfg data) are kept.
4. **WBA.** Uses [wba_confirm](../wba_confirm/README.md) to merge the image with:
   - the 16-byte "confirmed" validity marker (`7AC3F91E D45E8B20 31B7C4DA E9A0625F` at the header's marker address);
   - the [bootloader metadata](../wba_confirm/README.md#bootloader-metadata): the installed container version (WBA + WLE app version) and the app implementation (SID). The erase removes both, and without the version the bootloader warns `metadata.c:306 err=15` on every boot, which fails step 7.

   It then erases pages 0..116 (up to LITTLE_FS at 0x080EA000) and writes and verifies the merged file.
   - **Kept:** LITTLE_FS (the Sidewalk registration), SNVMA (BLE) and MFG_DATA (the Sidewalk mfg data).
   - **Rewritten:** the bootloader's OTA status and metadata pages, as after a factory install of these images. The trial counter is 0.
   - **App state:** with the marker, the bootloader treats the app as confirmed (VALID). It does not run on trial or fall back to the factory container.
5. **Boot check.** Opens the logs, resets the WLE and then the WBA, and reads the WBA log up to `Starting user application`. Expected:
   - `SIGN KEY: not installed`, or already the given key (then step 6 has nothing to write).
   - `FACTORY SID SIGN` and `FACTORY GEN2 SIGN` equal to the signatures in `--ext-flash`.
   - `META APP: state=1` (VALID).
6. **OTP.** Reads the WBA OTP (0x0BF90000, 512 bytes).
   - Already holds this key: nothing to do.
   - Holds another key or an invalid record: fail. The bootloader uses the first record and OTP cannot be erased.
   - Otherwise: writes the 48-byte key record (`smac_tools/signing`, 3 slots with index 0xB0..0xB2) into the first three free slots, so records of ST's own, such as the HSE trim in slot 0, stay. It then reads it back.
7. **Secure boot check.** Resets again and checks the bootloader part of the log:
   - `SIGN KEY` is the key;
   - both FACTORY lines still match;
   - the app is VALID;
   - exactly one `Sign check OK`;
   - no `[ERROR]` or `[WARNING]` line.

   Then it reads `--app-window` seconds of app log, which must contain no `[ERROR]`, `ASSERT`, `FATAL` or `Hard Fault`. A Release app logs nothing.
8. **RDP level 1.** Sets `RDP=0xBB` on the WLE, then the WBA. Each MCU reloads its option bytes and resets. It then reads both back.

## Unlocking a device later

From RDP level 1, setting `RDP=0xAA` (e.g. `STM32_Programmer_CLI -c port=SWD mode=UR -ob RDP=0xAA`) mass-erases the MCU's flash and returns it to level 0. OTP is not affected. After that the device needs its full programming again, including the Sidewalk and SMAC mfg data.

## Python

A package, like the other tools here. Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`):

```python
import sid_secure_prog

result = sid_secure_prog.program("wle_boot.hex", "wle_app.hex", "wba_boot.hex", "wba_app.hex",
                                 "sign_key_pub.pem", "spi_flash_factory.bin")
# {"key_fp": "160f3abbf4fd195d", "otp_slot": 1, "rdp": {"WLE": 0xBB, "WBA": 0xBB}}
```

`program()` takes the CLI options as keyword arguments (`app_window`, `rdp=False`, `check_only=True`, ...) and raises `SidSecureProgError`. `offline_checks()`, `check_boot()`, `otp_plan()` and `factory_signatures()` are the pieces. `python3 -m sid_secure_prog ...`, run from `smac_tools/run_ui/tools`, is the CLI.

It reuses:
- [stflash's stlink module](../stflash/README.md#shared-st-link-module-stlinkpy): erase and write, memory read, RDP;
- [sid_reg_wait](../sid_reg_wait/README.md): log ports and reset;
- [wba_confirm](../wba_confirm/README.md): the confirmed validity marker, the bootloader metadata and Intel HEX reading;
- `smac_tools/signing/sign_key.py`: key files and the OTP record;
- `smac_tools/container/spi_flash_image.py`: container checks.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/sid_secure_prog/tests
```

Run them with a Python that has PyNaCl; most tests are skipped without it.
- The end-to-end tests use a fake `STM32_Programmer_CLI` that keeps RDP, OTP (bits only cleared) and resets in files, plus log ports that print a boot log following that state.
- The fake boot log carries the bootloader's `metadata.c:306` warning unless the WBA write held the installed container version.
- They check the erase ranges, the merged marker and metadata, the OTP slot, that RDP comes last, and that nothing irreversible happens after a failure.
- Not tried on hardware yet. In particular the `-ob displ` output format (`RDP : 0x..`) and the CLI's behaviour while the option bytes reload are unverified.
