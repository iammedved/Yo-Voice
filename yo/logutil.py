"""Журнал Ёхо: %LOCALAPPDATA%\\yo-voice\\daemon.log, плюс stderr в консоли.

Распознанные фразы пишутся в этот же файл. Он живёт 6 часов с первой строки,
потом удаляется сам. Новый файл появляется на следующей записи, когда котом
снова пользуются, а не пустой заготовкой сразу после удаления.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 6 часов с первой строки журнала. Проверка раз в минуту, пока кот запущен.
DICTATION_LOG_TTL_S = 6 * 60 * 60
DICTATION_LOG_CHECK_MS = 60_000

_STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_stdio_log = None
_stdio_managed = False


def hush_progress_bars() -> None:
    """Windowed PyInstaller has sys.stdout is None; tqdm/HF must not write there."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from tqdm import tqdm

        tqdm.disable = True
    except Exception:
        pass
    try:
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
    except Exception:
        pass


def attach_stdio(log_path=None) -> None:
    """Frozen windowed exe: give tqdm/httpx a real stream so they cannot crash."""
    global _stdio_log, _stdio_managed
    if sys.stdout is not None and sys.stderr is not None:
        return
    path = log_path
    if path is None:
        try:
            from yo.paths import xdg_cache

            path = xdg_cache() / "daemon.log"
        except Exception:
            path = os.devnull
    try:
        fh = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
        _stdio_log = fh
        _stdio_managed = True
    except OSError:
        fh = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if sys.stdout is None:
        sys.stdout = fh
    if sys.stderr is None:
        sys.stderr = fh


def log_path():
    from yo.paths import xdg_cache

    return xdg_cache() / "daemon.log"


def setup_logging() -> None:
    hush_progress_bars()
    path = log_path()
    # Старый журнал не должен пережить запуск: сначала срок, потом новый файл.
    expire_dictation_log(path)
    attach_stdio(path)
    root = logging.getLogger()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    have_file = False
    for handler in root.handlers:
        base = getattr(handler, "baseFilename", None)
        if not base:
            continue
        try:
            if _same_path(base, path):
                have_file = True
                break
        except OSError:
            continue
    if not have_file:
        try:
            file_handler = ExpiringFileHandler(path, encoding="utf-8")
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
        except OSError:
            pass
    stream = sys.stderr
    if stream is not None:
        try:
            tty = bool(stream.isatty())
        except Exception:
            tty = False
        if tty:
            have_stream = any(
                isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                for h in root.handlers
            )
            if not have_stream:
                stream_handler = logging.StreamHandler(stream)
                stream_handler.setFormatter(fmt)
                root.addHandler(stream_handler)
    root.setLevel(logging.INFO)


def dictation_log_started(path: Path) -> float | None:
    """Секунды эпохи первой строки. Без даты — время создания файла, если оно есть."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.readline(180)
    except OSError:
        return None
    match = _STAMP_RE.match(head)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            pass
    try:
        st = path.stat()
    except OSError:
        return None
    birth = getattr(st, "st_birthtime", None)
    if isinstance(birth, (int, float)) and birth > 0:
        return float(birth)
    if sys.platform == "win32":
        return float(st.st_ctime)
    return None


def expire_dictation_log(path: Path | None = None, *, now: float | None = None) -> bool:
    """Удалить журнал и его старые копии, если им уже 6 часов. Новый файл не создавать."""
    target = Path(path) if path is not None else Path(log_path())
    moment = time.time() if now is None else float(now)
    stale = [item for item in _log_family(target) if _is_stale(item, moment)]
    if not stale:
        return False
    active_is_stale = any(_same_path(item, target) for item in stale)
    if active_is_stale:
        _drop_handlers(target)
        _detach_stdio()
        if target.exists() and not _try_delete(target):
            _attach_stdio_to(target)
            return False
    deleted = active_is_stale and not target.exists()
    for item in stale:
        if _same_path(item, target):
            continue
        if _try_delete(item):
            deleted = True
    return deleted


class ExpiringFileHandler(logging.FileHandler):
    """Перед записью выбрасывает журнал старше 6 часов и открывает новый."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            expire_dictation_log(self.baseFilename)
            if self.stream is None:
                self.stream = self._open()
            logging.StreamHandler.emit(self, record)
        except Exception:
            self.handleError(record)

    def _open(self):
        stream = logging.FileHandler._open(self)
        _attach_stdio_to(self.baseFilename)
        return stream


def _log_family(path: Path) -> list[Path]:
    parent = path.parent
    name = path.name
    if not parent.is_dir():
        return [path] if path.is_file() else []
    found: list[Path] = []
    try:
        entries = list(parent.iterdir())
    except OSError:
        return [path] if path.is_file() else []
    for item in entries:
        if not item.is_file():
            continue
        if item.name == name or item.name.startswith(name + "."):
            found.append(item)
    return found


def _is_stale(path: Path, now: float) -> bool:
    started = dictation_log_started(path)
    if started is None:
        return False
    return now - started >= DICTATION_LOG_TTL_S


def _same_path(left, right) -> bool:
    try:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
    except OSError:
        return False


def _handlers_for(path: Path) -> list[logging.FileHandler]:
    found: list[logging.FileHandler] = []
    seen: set[int] = set()
    names = list(logging.root.manager.loggerDict)
    loggers = [logging.getLogger()] + [logging.getLogger(name) for name in names]
    for logger in loggers:
        for handler in getattr(logger, "handlers", ()):
            if id(handler) in seen or not isinstance(handler, logging.FileHandler):
                continue
            base = getattr(handler, "baseFilename", None)
            if base and _same_path(base, path):
                seen.add(id(handler))
                found.append(handler)
    return found


def _drop_handlers(path: Path) -> None:
    for handler in _handlers_for(path):
        handler.acquire()
        try:
            stream = handler.stream
            handler.stream = None
            if stream is None:
                continue
            try:
                stream.flush()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        finally:
            handler.release()


def _detach_stdio() -> None:
    global _stdio_log
    fh = _stdio_log
    if fh is None:
        return
    if sys.stdout is fh or sys.stderr is fh:
        sink = open(os.devnull, "w", encoding="utf-8", errors="replace")
        if sys.stdout is fh:
            sys.stdout = sink
        if sys.stderr is fh:
            sys.stderr = sink
    try:
        fh.close()
    except OSError:
        pass
    _stdio_log = None


def _attach_stdio_to(path) -> None:
    global _stdio_log
    if not _stdio_managed or _stdio_log is not None:
        return
    try:
        fh = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        return
    _stdio_log = fh
    if sys.stdout is None or _is_devnull(sys.stdout):
        sys.stdout = fh
    if sys.stderr is None or _is_devnull(sys.stderr):
        sys.stderr = fh


def _is_devnull(stream) -> bool:
    name = getattr(stream, "name", None)
    if not name:
        return False
    try:
        return os.path.normcase(os.path.abspath(name)) == os.path.normcase(os.path.abspath(os.devnull))
    except OSError:
        return False


def _try_delete(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True
