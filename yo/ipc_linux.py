"""Одноэкземплярный демон через UNIX-сокет."""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path

from yo.paths import pid_path, socket_path

CommandHandler = Callable[[str], str]


def daemon_alive(path: Path | None = None) -> bool:
    sock = path or socket_path()
    if not sock.exists():
        return False
    try:
        return send_command("ping") == "pong"
    except OSError:
        try:
            sock.unlink()
        except OSError:
            pass
        return False


def send_command(command: str, path: Path | None = None, timeout: float = 2.0) -> str:
    sock_path = str(path or socket_path())
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(sock_path)
    try:
        client.sendall((command.strip() + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8").strip()
    finally:
        client.close()


class IpcServer(threading.Thread):
    def __init__(self, handler: CommandHandler) -> None:
        super().__init__(daemon=True, name="yo-ipc")
        self.handler = handler
        self._running = True
        self._server: socket.socket | None = None

    def stop(self) -> None:
        self._running = False
        try:
            send_command("ping", timeout=0.2)
        except OSError:
            pass

    def run(self) -> None:
        path = socket_path()
        if path.exists():
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(8)
        server.settimeout(0.4)
        self._server = server
        pid_path().write_text(str(os.getpid()), encoding="utf-8")
        while self._running:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()
        try:
            server.close()
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass

    def _serve(self, conn: socket.socket) -> None:
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(1024)
                if not chunk:
                    break
                buf += chunk
            command = buf.decode("utf-8").strip() or "ping"
            if command == "ping":
                reply = "pong"
            else:
                reply = self.handler(command) or "ok"
            conn.sendall((reply + "\n").encode("utf-8"))
        except OSError:
            pass
        finally:
            conn.close()


def write_pid() -> None:
    pid_path().write_text(str(os.getpid()), encoding="utf-8")
