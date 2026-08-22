# Windows Sensor Watcher

`sensor_watcher.c` remains the reference test workflow. macOS/Linux and Windows compile
the same watcher, UART protocol and Sensor test sources. Only the platform adapters differ:

```text
Shared test behavior
  sensor_watcher.c + uart_hvf.c + uart_hvf_sensors.c

macOS / Linux                 Windows
  platform_posix.c              platform_windows.c
  platform_http_posix.c         platform_http_windows.c (WinHTTP)
```

This arrangement prevents UART timing, command order, parsing and Backend JSON from being
independently rewritten for Windows.

## Port selection

List ports:

```powershell
sensor_watcher.exe --list-ports
```

Windows defaults to `--port auto`. Auto-selection succeeds only when exactly one serial
port exists; it deliberately refuses to send commands when multiple ports are present.
Select explicitly in that case:

```powershell
sensor_watcher.exe --port COM5
```

Windows accepts `COM1` through `COM256`; the platform adapter automatically converts them
to the Win32 `\\.\COMx` device path. Use Device Manager or this PowerShell command to
identify USB VID, PID and PNP identity:

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID
```

## Build on Windows

Install MSYS2, open its **MinGW64** shell, then install the compiler:

```bash
pacman -S --needed mingw-w64-x86_64-gcc make
cd /path/to/production-test-system/tester
make -f Makefile.windows
```

The result is `sensor_watcher.exe`. It uses Windows WinHTTP and does not require
`libcurl.dll`.

## Run

Run from the `tester` directory so the default `../shared/sensor_test.txt` path resolves:

```powershell
.\sensor_watcher.exe --port COM5
```

Optional settings useful for installation and testing:

```powershell
.\sensor_watcher.exe `
  --port COM5 `
  --command-file C:\ProductionTest\shared\sensor_test.txt `
  --api-base-url http://localhost:8000
```

Simulation remains available without UART hardware:

```powershell
.\sensor_watcher.exe --simulate
```

## Cross-platform behavior comparison

The black-box contract test launches the watcher in simulation mode, uses an isolated
command file and mock Backend, and verifies stage order, terminal status, detail shape and
`expected_stages`.

macOS/Linux reference:

```bash
make sensor_watcher
python3 tests/test_sensor_watcher_contract.py ./sensor_watcher \
  --output reference-contract.json
```

Windows (from a terminal with Python available):

```powershell
python tests\test_sensor_watcher_contract.py .\sensor_watcher.exe `
  --output windows-contract.json
```

The test must report `PASS` on both systems. The two JSON files can also be compared after
normalizing the simulated numeric values; their stage/status order and detail keys must be
identical.

Hardware validation is still required on at least one Windows station because a simulation
cannot verify USB driver behavior or UART timing. Validate WLE/WBA, all four sensors,
button, both LEDs, buzzer, SPI, board replacement, unplug/replug and timeout recovery.
