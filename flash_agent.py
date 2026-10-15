#!/usr/bin/env python3
"""Local bridge for running the host ST-Link flashing script from the UI."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading


ROOT_DIR = Path(__file__).resolve().parent
FLASH_SCRIPT = ROOT_DIR / "flash_smac.sh"
HOST = "127.0.0.1"
PORT = 8765
_flash_lock = threading.Lock()
_allowed_origins = {
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
}


class FlashHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _cors_headers(self):
        origin = self.headers.get("Origin")
        if origin in _allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

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
        body = b"{\"status\":\"ready\",\"flash_script\":\"flash_smac.sh\"}"
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
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
                ["bash", str(FLASH_SCRIPT), mode],
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
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
