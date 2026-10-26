"""Start and stop the local Sensor IQC watcher with the FastAPI process."""

import asyncio
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import shutil
from urllib.error import URLError
from urllib.request import urlopen

from app.config import settings

logger = logging.getLogger("uvicorn.error")

_watcher_process: subprocess.Popen | None = None
_watcher_control_lock = asyncio.Lock()


def _status_endpoint_available() -> bool:
    try:
        with urlopen("http://127.0.0.1:8766/health", timeout=0.4) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _resolve_watcher() -> tuple[Path, Path] | None:
    if settings.SENSOR_WATCHER_EXECUTABLE:
        executable = Path(settings.SENSOR_WATCHER_EXECUTABLE).expanduser().resolve()
        working_dir = executable.parent
    else:
        repo_root = Path(__file__).resolve().parents[2]
        working_dir = repo_root / "tester"
        filename = "sensor_watcher.exe" if os.name == "nt" else "sensor_watcher"
        executable = working_dir / filename

    if not executable.is_file():
        return None
    if os.name != "nt" and not os.access(executable, os.X_OK):
        logger.warning("Sensor watcher exists but is not executable: %s", executable)
        return None
    return executable, working_dir


def _same_path(left: str, right: Path) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def _find_watcher_process_ids(executable: Path) -> list[int]:
    expected_path = os.path.realpath(executable)
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            return []
        escaped_path = expected_path.replace("'", "''")
        script = (
            f"$target = '{escaped_path}'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.ExecutablePath -and "
            "[String]::Equals([IO.Path]::GetFullPath($_.ExecutablePath), "
            "$target, [StringComparison]::OrdinalIgnoreCase) } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]

    if sys.platform.startswith("linux"):
        process_ids = []
        for process_path in Path("/proc").glob("[0-9]*/exe"):
            try:
                if _same_path(str(process_path.resolve(strict=True)), executable):
                    process_ids.append(int(process_path.parent.name))
            except (OSError, ValueError):
                continue
        return process_ids

    # macOS: lsof identifies listener PIDs, then the process's mapped executable
    # is checked so the restart cannot kill an unrelated service on port 8766.
    lsof = shutil.which("lsof")
    if not lsof:
        return []
    listeners = subprocess.run(
        [lsof, "-nP", "-t", "-iTCP:8766", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    process_ids = []
    for line in listeners.stdout.splitlines():
        if not line.strip().isdigit():
            continue
        pid = int(line)
        opened_files = subprocess.run(
            [lsof, "-nP", "-a", "-p", str(pid), "-d", "txt", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        executable_paths = [entry[1:] for entry in opened_files.stdout.splitlines()
                            if entry.startswith("n")]
        if any(_same_path(path, executable) for path in executable_paths):
            process_ids.append(pid)
    return process_ids


def _terminate_process_id(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)

    if os.name == "nt":
        taskkill = shutil.which("taskkill.exe") or shutil.which("taskkill")
        if taskkill:
            subprocess.run([taskkill, "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def _stop_running_watcher() -> None:
    global _watcher_process

    managed_process = _watcher_process
    _watcher_process = None
    if managed_process is not None and managed_process.poll() is None:
        logger.info("Stopping managed sensor_watcher (pid=%s)", managed_process.pid)
        managed_process.terminate()
        try:
            await asyncio.to_thread(managed_process.wait, timeout=3)
        except subprocess.TimeoutExpired:
            managed_process.kill()
            await asyncio.to_thread(managed_process.wait)
    else:
        resolved = _resolve_watcher()
        if resolved is None:
            raise RuntimeError("Cannot locate sensor_watcher.exe to safely restart the running watcher")
        external_process_ids = await asyncio.to_thread(_find_watcher_process_ids, resolved[0])
        if not external_process_ids:
            raise RuntimeError("Watcher is responding, but its process could not be identified safely")
        for pid in external_process_ids:
            logger.info("Stopping sensor_watcher (pid=%s)", pid)
            await asyncio.to_thread(_terminate_process_id, pid)

    for _ in range(30):
        if not await asyncio.to_thread(_status_endpoint_available):
            return
        await asyncio.sleep(0.1)
    raise RuntimeError("sensor_watcher did not stop; refusing to start a second instance")


async def _launch_sensor_watcher() -> bool:
    global _watcher_process

    resolved = _resolve_watcher()
    if resolved is None:
        logger.warning(
            "sensor_watcher was not started: executable not found. "
            "Set SENSOR_WATCHER_EXECUTABLE or install it under tester/"
        )
        return False

    executable, working_dir = resolved
    creationflags = 0
    popen_options: dict = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        popen_options["start_new_session"] = True

    try:
        _watcher_process = subprocess.Popen(
            [str(executable), "--auto"],
            cwd=working_dir,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            **popen_options,
        )
    except OSError:
        logger.exception("Failed to start sensor_watcher: %s", executable)
        _watcher_process = None
        return False

    # The watcher opens UARTs and starts its local status endpoint during startup.
    for _ in range(40):
        if await asyncio.to_thread(_status_endpoint_available):
            logger.info("Started sensor_watcher (pid=%s)", _watcher_process.pid)
            return True
        if _watcher_process.poll() is not None:
            logger.error(
                "sensor_watcher exited during startup (exit code %s); "
                "check available serial ports and watcher logs",
                _watcher_process.returncode,
            )
            _watcher_process = None
            return False
        await asyncio.sleep(0.1)

    logger.warning("sensor_watcher started (pid=%s), but its status endpoint is not ready", _watcher_process.pid)
    return False


async def start_sensor_watcher(force_restart: bool = False) -> bool:
    """Start the watcher, optionally restarting the existing watcher safely."""
    async with _watcher_control_lock:
        is_running = await asyncio.to_thread(_status_endpoint_available)
        if is_running and not force_restart:
            logger.info("sensor_watcher is already running")
            return True
        if is_running:
            await _stop_running_watcher()
        return await _launch_sensor_watcher()


async def stop_sensor_watcher() -> None:
    """Stop only the watcher process that this backend instance launched."""
    global _watcher_process

    async with _watcher_control_lock:
        process = _watcher_process
        _watcher_process = None
        if process is None or process.poll() is not None:
            return

        logger.info("Stopping sensor_watcher (pid=%s)", process.pid)
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)
