from __future__ import annotations

import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _start_and_wait_for_output(command: list[str], port: int) -> str:
    if not _port_available(port):
        pytest.skip(f"Port {port} is already in use")

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


@pytest.mark.parametrize(
    ("command", "port"),
    [
        ([sys.executable, "app_web/server.py"], 18011),
        ([sys.executable, "-m", "app_web.server"], 18012),
    ],
)
def test_web_server_entrypoints_start(command: list[str], port: int) -> None:
    output = _start_and_wait_for_output(command, port)
    assert f"http://127.0.0.1:{port}" in output
