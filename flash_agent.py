#!/usr/bin/env python3
"""Local bridge for running the host ST-Link flashing script from the UI."""

from http.server import BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:  # Python < 3.7
    from http.server import HTTPServer
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parent
FLASH_SCRIPT = ROOT_DIR / "flash_smac.sh"
HOST = "127.0.0.1"
PORT = 8765
_flash_lock = threading.Lock()
_watcher_lock = threading.Lock()
_watcher_process = None
_allowed_origins = {
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
}


def _bash_executable():
    configured = os.environ.get("FLASH_BASH")
    if configured:
        return configured
    if sys.platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates = (
            program_files / "Git" / "bin" / "bash.exe",
            program_files / "Git" / "usr" / "bin" / "bash.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "bin" / "bash.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        path_bash = shutil.which("bash")
        if path_bash and "\\windows\\system32\\bash.exe" not in path_bash.casefold():
            return path_bash
        raise FileNotFoundError(
            "Git for Windows Bash was not found. Install Git for Windows or set FLASH_BASH to bash.exe."
        )
    return shutil.which("bash") or "bash"


def _watcher_executable():
    configured = os.environ.get("SENSOR_WATCHER_EXECUTABLE")
    if configured:
        return Path(configured).expanduser().resolve()
    name = "sensor_watcher.exe" if os.name == "nt" else "sensor_watcher"
    return ROOT_DIR / "tester" / name


def _watcher_running():
    try:
        with urlopen("http://127.0.0.1:8766/health", timeout=0.4) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _find_watcher_pids(executable):
    expected_path = os.path.normcase(os.path.realpath(executable))
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            return []
        escaped_path = os.path.realpath(executable).replace("'", "''")
        script = (
            f"$target = '{escaped_path}'; Get-CimInstance Win32_Process | "
            "Where-Object { $_.ExecutablePath -and "
            "[String]::Equals([IO.Path]::GetFullPath($_.ExecutablePath), "
            "$target, [StringComparison]::OrdinalIgnoreCase) } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=8, check=False,
        )
        return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]

    if sys.platform.startswith("linux"):
        pids = []
        for process_path in Path("/proc").glob("[0-9]*/exe"):
            try:
                actual_path = os.path.normcase(os.path.realpath(process_path.resolve(strict=True)))
                if actual_path == expected_path:
                    pids.append(int(process_path.parent.name))
            except (OSError, ValueError):
                continue
        return pids

    lsof = shutil.which("lsof")
    if not lsof:
        return []
    listeners = subprocess.run(
        [lsof, "-nP", "-t", "-iTCP:8766", "-sTCP:LISTEN"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, timeout=5, check=False,
    )
    pids = []
    for line in listeners.stdout.splitlines():
        if not line.strip().isdigit():
            continue
        pid = int(line)
        opened = subprocess.run(
            [lsof, "-nP", "-a", "-p", str(pid), "-d", "txt", "-Fn"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=5, check=False,
        )
        paths = [entry[1:] for entry in opened.stdout.splitlines() if entry.startswith("n")]
        if any(os.path.normcase(os.path.realpath(path)) == expected_path for path in paths):
            pids.append(pid)
    return pids


def _terminate_pid(pid):
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
            subprocess.run(
                [taskkill, "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _stop_watcher():
    global _watcher_process
    process = _watcher_process
    _watcher_process = None
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    else:
        executable = _watcher_executable()
        pids = _find_watcher_pids(executable)
        if not pids:
            raise RuntimeError("Watcher is responding, but its executable could not be identified safely")
        for pid in pids:
            _terminate_pid(pid)

    for _ in range(30):
        if not _watcher_running():
            return
        time.sleep(0.1)
    raise RuntimeError("sensor_watcher did not stop; refusing to start another instance")


def _start_watcher(restart=False):
    global _watcher_process
    with _watcher_lock:
        if _watcher_running() and not restart:
            return {"status": "running", "action": "start"}
        if _watcher_running():
            _stop_watcher()

        executable = _watcher_executable()
        if not executable.is_file():
            raise FileNotFoundError(
                f"sensor_watcher executable not found: {executable}; build it first or set SENSOR_WATCHER_EXECUTABLE"
            )
        if os.name != "nt" and not os.access(executable, os.X_OK):
            raise PermissionError(f"sensor_watcher is not executable: {executable}")

        options = {}
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
        else:
            options["start_new_session"] = True
        _watcher_process = subprocess.Popen(
            [str(executable), "--auto"],
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            **options,
        )
        for _ in range(150):
            if _watcher_running():
                return {"status": "running", "action": "restart" if restart else "start"}
            if _watcher_process.poll() is not None:
                code = _watcher_process.returncode
                _watcher_process = None
                raise RuntimeError(f"sensor_watcher exited during startup (exit code {code}); check serial ports")
            time.sleep(0.1)
        raise RuntimeError("sensor_watcher did not expose its status endpoint within 15 seconds")


class FlashHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _cors_headers(self):
        origin = self.headers.get("Origin")
        if origin in _allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        body = b"{\"status\":\"ready\",\"flash_script\":\"flash_smac.sh\",\"sensor_watcher_control\":true}"
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        watcher_actions = {
            "/api/sensor/watcher/start": False,
            "/api/sensor/watcher/restart": True,
        }
        if self.path in watcher_actions:
            try:
                result = _start_watcher(restart=watcher_actions[self.path])
                self._send_json(200, result)
            except FileNotFoundError as error:
                self._send_json(503, {"detail": str(error)})
            except PermissionError as error:
                self._send_json(503, {"detail": str(error)})
            except RuntimeError as error:
                self._send_json(409, {"detail": str(error)})
            except (OSError, subprocess.SubprocessError) as error:
                self._send_json(500, {"detail": f"sensor_watcher control failed: {error}"})
            return

        modes = {
            "/api/firmware/hvf/flash": "hvf",
            "/api/firmware/diagnostics/flash": "diagnostics",
        }
        mode = modes.get(self.path)
        if mode is None:
            self.send_error(404)
            return
        if not _flash_lock.acquire(blocking=False):
            self.send_error(409, "A firmware flash is already running")
            return
        if not FLASH_SCRIPT.is_file():
            _flash_lock.release()
            self.send_error(500, "flash_smac.sh not found")
            return

        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def write_line(line):
            try:
                self.wfile.write(line.encode("utf-8", errors="replace"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # Let flashing finish even if the browser closes its log view.
                pass

        try:
            process = subprocess.Popen(
                [_bash_executable(), str(FLASH_SCRIPT), mode],
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                write_line(line)
            return_code = process.wait()
            write_line(f"FLASH_EXIT_CODE={return_code}\n")
        except Exception as error:
            write_line(f"Flash agent error: {error}\nFLASH_EXIT_CODE=1\n")
        finally:
            _flash_lock.release()

    def log_message(self, format_string, *args):
        print(f"[flash-agent] {format_string % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), FlashHandler)
    print(f"Flash agent listening on http://{HOST}:{PORT}")
    server.serve_forever()
