@echo off
rem SID secure programming, HW 2.0.2
cd /d "%~dp0"
python tools\run_ui\run_ui.py tools\run_ui\stations_config\sid_secure_programming_station\config_hw_2_0_2.json
if errorlevel 1 pause
