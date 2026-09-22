"""Одноэкземплярный демон: UNIX-сокет на Linux, TCP 127.0.0.1 на Windows."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from yo.ipc_win import IpcServer, daemon_alive, send_command, write_pid
else:
    from yo.ipc_linux import IpcServer, daemon_alive, send_command, write_pid
