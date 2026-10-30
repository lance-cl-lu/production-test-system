@echo off
rem SID registration (any HW)
cd /d "%~dp0"
python tools\run_ui\run_ui.py tools\run_ui\stations_config\sid_do_registration_station\config.json
if errorlevel 1 pause
