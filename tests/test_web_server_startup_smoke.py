from __future__ import annotations

import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_and_wait_for_output(command: list[str], port: int) -> str:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["DATALAB_PORT"] = str(port)
    env["DATALAB_HOST"] = "127.0.0.1"
    env["DATALAB_WEB_SECRET"] = "test-secret"

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_queue: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output_queue.put(line)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    collected: list[str] = []
    deadline = time.monotonic() + 15.0
    marker = f"http://127.0.0.1:{port}"

    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                line = output_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            collected.append(line)
            if marker in line:
                return "".join(collected)
        while True:
            try:
                collected.append(output_queue.get_nowait())
            except queue.Empty:
                break
        raise AssertionError(f"Server did not report startup on port {port}.\nOutput:\n{''.join(collected)}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_web_server_script_entrypoint_starts() -> None:
    port = _unused_local_port()
    output = _start_and_wait_for_output([sys.executable, "app_web/server.py"], port)
    assert f"http://127.0.0.1:{port}" in output


def test_web_server_module_entrypoint_starts() -> None:
    port = _unused_local_port()
    output = _start_and_wait_for_output([sys.executable, "-m", "app_web.server"], port)
    assert f"http://127.0.0.1:{port}" in output
