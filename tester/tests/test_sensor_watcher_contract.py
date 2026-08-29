#!/usr/bin/env python3
"""Black-box contract test shared by POSIX reference and Windows builds."""

import argparse
import json
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class EventStore:
    def __init__(self):
        self.events = []
        self.condition = threading.Condition()

    def append(self, path, payload):
        with self.condition:
            self.events.append((path, payload))
            self.condition.notify_all()

    def wait_for_complete(self, timeout):
        deadline = time.monotonic() + timeout
        with self.condition:
            while time.monotonic() < deadline:
                if any(payload.get("stage") == "testComplete"
                       for _, payload in self.events):
                    return True
                self.condition.wait(deadline - time.monotonic())
        return False


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            store.append(self.path, payload)
            body = b'{"status":"accepted"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    return Handler


def normalized_contract(events):
    result = []
    for path, payload in events:
        if path.endswith("/events"):
            result.append({
                "stage": payload.get("stage"),
                "status": payload.get("status"),
                "detail_keys": sorted((payload.get("detail") or {}).keys()),
            })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--output", type=Path,
                        help="write the normalized contract JSON for cross-platform comparison")
    parser.add_argument("--single-buzzer", action="store_true",
                        help="verify that a single buzzer test does not trigger a sensor probe")
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.exists():
        parser.error(f"binary does not exist: {binary}")

    store = EventStore()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(store))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    with tempfile.TemporaryDirectory() as directory:
        command_file = Path(directory) / "sensor_test.txt"
        command_file.write_text("", encoding="utf-8")
        process = subprocess.Popen(
            [str(binary), "--simulate", "--command-file", str(command_file),
             "--lock-file", str(Path(directory) / "sensor_watcher.lock"),
             "--api-base-url", f"http://127.0.0.1:{server.server_port}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            time.sleep(1.2)  # watcher records the initial file timestamp first
            command = ("STAGE testBuzzer CONTRACT-001\n" if args.single_buzzer
                       else "TEST CONTRACT-001\n")
            command_file.write_text(command, encoding="utf-8")
            if not store.wait_for_complete(15):
                raise AssertionError("watcher did not emit testComplete within 15 seconds")
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            server.shutdown()
            server.server_close()

    contract = normalized_contract(store.events)
    if args.single_buzzer:
        expected_contract = [
            {
                "stage": "testBuzzer",
                "status": "testing",
                "detail_keys": ["awaiting_user_confirmation"],
            },
            {
                "stage": "testComplete",
                "status": "pass",
                "detail_keys": ["expected_stages", "requested_stage", "run_mode", "serial_wba"],
            },
        ]
        if contract != expected_contract:
            raise AssertionError(
                f"single buzzer contract mismatch\nexpected={expected_contract}\nactual={contract}"
                f"\nstdout={stdout}\nstderr={stderr}"
            )
        print("PASS: single buzzer test emitted no getSensorIC event")
        return

    fixture = Path(__file__).with_name("sensor_watcher_reference_contract.json")
    expected_contract = json.loads(fixture.read_text(encoding="utf-8"))
    if contract != expected_contract:
        raise AssertionError(
            f"event contract mismatch\nexpected={expected_contract}\nactual={contract}"
            f"\nstdout={stdout}\nstderr={stderr}"
        )
    complete = next(payload for path, payload in store.events
                    if path.endswith("/events") and payload.get("stage") == "testComplete")
    expected_stages = complete["detail"]["expected_stages"]
    expected_names = ["getSensorIC", "ens210", "lps22df", "bme690", "testButton",
                      "testGreenLED", "testOrangeLED", "testBuzzer", "testSPI"]
    if expected_stages != expected_names:
        raise AssertionError(f"expected_stages mismatch: {expected_stages}")

    if args.output:
        args.output.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    print(f"PASS: {binary.name} emitted {len(contract)} contract events in the expected order")


if __name__ == "__main__":
    main()
