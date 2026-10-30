# SID secure programming station: sequence

The `SID secure programming` station (`smac_tools/run_ui/stations_config/sid_secure_programming_station/`) runs [sid_secure_prog](README.md) with the files named in its `config.json`. There are 8 steps, each logged as `[INFO] [STEP n/8] …`. The first failure stops the run with `[ERROR] <reason>` and the panel shows FAIL.

Steps 6 (OTP) and 8 (RDP) cannot be undone. They run only after every earlier step passed.

## 1. Offline checks

No hardware is touched in this step.

- **Merge:** each MCU's bootloader and app are merged into one image with [combine_binaries](../combine_binaries/README.md), and the memory map is printed.
- **Image limits:**
  - WLE data must stay below 0x0803E800 (NVM_STORAGE).
  - WBA data must stay below 0x080EA000 (LITTLE_FS).
- **WBA image:**
  - it has a bootloader at 0x08000000 and the app's OTA header at 0x08012188;
  - the app is signed with the station's sign key, otherwise the bootloader would refuse it once RDP is 1;
  - its validity-marker address is free.
- **SPI-flash image:** the SID and GEN2 factory containers in the SPI NOR image (`--ext-flash`) must be valid and signed with the key. Their signatures become the expected values for steps 5 and 7.
- **Bootloader metadata:** the installed container version for step 4 is computed from the images (WBA app version + WLE app version).
- **SID container version:** the SID factory container in the SPI-flash image must have that same version, so that it holds the apps being programmed. A mismatch stops the run, e.g. a NOR image built from another release.
- **Hardware version:** the WLE app inside the SID factory container must be built for the same hardware as the WLE app being programmed (the info block's hardware version, e.g. 2.0.2 vs 2.0.3). Builds for different board revisions share a firmware version, so the version check alone can't tell them apart.
- **CubeProgrammer:** its WBA OTP write alignment must be patched to 0x10 (see [Setup](README.md#setup)).

## 2. ST-Links

- Finds which ST-Link is on which MCU, by Device ID.
- Both MCUs must still be at RDP level 0. An already locked device stops here.

## 3. WLE

Erases pages 0–124, then writes and verifies the merged WLE image in one CLI run. NVM_STORAGE and PERMANENT_DATA (the SMAC mfg data) are kept.

## 4. WBA

- **Confirmed marker:** [wba_confirm](../wba_confirm/README.md) adds the confirmed app validity marker to the merged image, so the app does not run on trial.
- **Bootloader metadata:** it also adds the installed container version and the app implementation (SID), as a factory install leaves them. The erase removes both. Without the version, the bootloader logs `[WARNING] metadata.c:306 err=15` on every boot, and step 7 fails on it.
- **Erase and write:** erases pages 0–116, then writes and verifies the image in one run.
- **Kept:** LITTLE_FS (Sidewalk registration), BLE NVM and the Sidewalk MFG_DATA.

## 5. Boot check

Opens both log ports, resets the WLE and then the WBA, and reads the WBA bootloader log until `Starting user application`. It expects:

- `SIGN KEY: not installed`, or already the station's key (then step 6 has nothing to write);
- `FACTORY SID SIGN` and `FACTORY GEN2 SIGN` equal to the signatures in the SPI-flash image;
- `META APP: state=1` (app valid).

## 6. OTP (irreversible)

Reads the WBA OTP area (512 bytes at 0x0BF90000).

- **Already the station's key:** skipped.
- **Another key or a broken record:** FAIL. OTP cannot be erased, and the bootloader uses the first record.
- **Otherwise:** writes the 48-byte key record into the first 3 free slots, leaving ST's own records (such as the HSE trim) in place, then reads it back to confirm.

## 7. Secure boot check

Resets again and reads the bootloader log. It requires:

- `SIGN KEY` equal to the station's key;
- both FACTORY lines still matching;
- the app valid;
- exactly one `Sign check OK`;
- no `[ERROR]` or `[WARNING]` lines.

Then it watches the app log for `--app-window` seconds (10 by default) for `[ERROR]`, `ASSERT`, `FATAL` or `Hard Fault`. A Release app logs nothing, so this window only catches problems with Debug builds.

## 8. RDP level 1 (irreversible except by mass erase)

Sets RDP to 0xBB on the WLE, then the WBA, and reads both back. From now on the bootloader refuses badly signed images. Going back to level 0 mass-erases the MCU, including the Sidewalk registration and both sets of mfg data.

## Compared with the SMAC MFG station

The SMAC MFG station fully erases the WLE, and the WBA except MFG_DATA. This station keeps the device's existing NVM and mfg data. It expects a device that has already passed the earlier stations.

## Before the first real run

- Copy the bootloader and app images, the public key (`sign_key_pub.pem`) and the SPI-flash image (`spi_flash_factory.bin`) into the station folder, as named in `config.json`.
- Patch CubeProgrammer's OTP alignment to 0x10 (see [Setup](README.md#setup)).
- Confirm that the key in `sign_key_pub.pem` is the one to burn into OTP. Its fingerprint is printed in step 1.
- Do a bench run with `--no-rdp` first. It does everything except step 8; OTP is still written.
