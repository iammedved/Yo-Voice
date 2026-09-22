"""Одноэкземплярный демон через localhost TCP (Windows)."""

from __future__ import annotations

import ctypes
import os
import socket
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

from yo.paths import pid_path, socket_path
from yo.winapi import ERROR_ALREADY_EXISTS, kernel32

CommandHandler = Callable[[str], str]

_HOST = "127.0.0.1"
_MUTEX_NAME = "Local\\Yo-Voice-Daemon"
_mutex_handle = None


def pipe_port_path() -> Path:
    return socket_path()


def _port_file(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else pipe_port_path()


def _read_port(path: Path) -> int:
    try:
        port = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise OSError(f"invalid port file {path}") from exc
    if not 1 <= port <= 65535:
        raise OSError(f"invalid port {port} in {path}")
    return port


def _pid_alive() -> bool:
    try:
        raw = pid_path().read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return int(code.value) == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def daemon_alive(path: Path | None = None) -> bool:
    sock = _port_file(path)
    if sock.exists():
        try:
            return send_command("ping", path=sock) == "pong"
        except OSError:
            # A timeout/reset is not "dead". Only drop the port file if the
            # daemon PID is gone — otherwise double-click exits instantly
            # while the tray copy is still running.
            if _pid_alive():
                return False
            try:
                sock.unlink()
            except OSError:
                pass
            return False
    return False


def send_command(command: str, path: Path | None = None, timeout: float = 2.0) -> str:
    port = _read_port(_port_file(path))
    client = socket.create_connection((_HOST, port), timeout=timeout)
    try:
        client.settimeout(timeout)
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
        server = self._server
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        try:
            send_command("ping", timeout=0.2)
        except OSError:
            pass

    def run(self) -> None:
        path = pipe_port_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((_HOST, 0))
        server.listen(8)
        server.settimeout(0.4)
        self._server = server
        port = int(server.getsockname()[1])
        path.write_text(str(port), encoding="utf-8")
        pid_path().write_text(str(os.getpid()), encoding="utf-8")
        while self._running:
            try:
                if not path.exists():
                    path.write_text(str(port), encoding="utf-8")
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    time.sleep(0.2)
                    continue
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


def claim_singleton() -> bool:
    """True if this process owns the daemon mutex (or the mutex cannot be created)."""
    global _mutex_handle
    if _mutex_handle:
        return True
    handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    err = ctypes.get_last_error()
    if not handle:
        return True
    _mutex_handle = handle
    return err != ERROR_ALREADY_EXISTS
