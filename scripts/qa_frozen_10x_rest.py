"""Continue 10x QA: bind, tray, record, reload. Dismiss frozen bind MessageBox."""
from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

EXE = Path(r"D:\ProgramFiles\Yo-Voice\Yo-Voice.exe")
CACHE = Path(os.environ.get("LOCALAPPDATA", "")) / "yo-voice"
CONFIG = Path(os.environ.get("APPDATA", "")) / "yo-voice" / "config.json"
LOG = CACHE / "daemon.log"
PORT = CACHE / "yo.port"
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 5
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
IDOK = 1

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.c_void_p
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
user32.PostMessageW.restype = ctypes.c_int
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]

FAILS: list[str] = []
PASSES: list[str] = []
STOP = False


def ok(msg: str) -> None:
    PASSES.append(msg)
    print("PASS", msg, flush=True)


def fail(msg: str) -> None:
    FAILS.append(msg)
    print("FAIL", msg, flush=True)


def run_exe(*args: str, timeout: float = 8.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(EXE), *args],
        capture_output=True,
        timeout=timeout,
        cwd=str(EXE.parent),
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def yo_procs() -> list[int]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Yo-Voice.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pids: list[int] = []
    for line in (out.stdout or "").splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2 and parts[0].lower().startswith("yo-voice"):
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def dismiss_yo_dialogs() -> int:
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lp):
        title = ctypes.create_unicode_buffer(256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        user32.GetClassNameW(hwnd, cls, 256)
        if title.value == "Ёхо" and cls.value == "#32770":
            found.append(hwnd)
            user32.PostMessageW(hwnd, WM_COMMAND, IDOK, 0)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return 1

    user32.EnumWindows(cb, 0)
    return len(found)


def dialog_watch() -> None:
    while not STOP:
        dismiss_yo_dialogs()
        time.sleep(0.08)


def ipc(cmd: str, timeout: float = 2.5) -> str:
    port = int(PORT.read_text(encoding="utf-8").strip())
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        s.sendall((cmd.strip() + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(256)
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8", "replace").strip()
    finally:
        s.close()


def spawn_daemon() -> None:
    subprocess.Popen(
        [str(EXE), "daemon"],
        cwd=str(EXE.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_alive(timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if ipc("status") in {"idle", "listening"}:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def log_text() -> str:
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def assert_no_fatal(context: str) -> None:
    text = log_text()
    if "Fatal Python error" in text or "PyEval_RestoreThread" in text:
        fail(f"{context}: crash in log")
        return
    if "NoneType" in text and "write" in text.lower():
        fail(f"{context}: tqdm/stdout NoneType")
        return
    ok(f"{context}: no GIL/tqdm abort")


def loop_hwnd():
    return user32.FindWindowW("YoVoiceLoop", None) or user32.FindWindowW(None, "yo-loop")


def load_cfg() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save_cfg(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_daemon() -> None:
    if yo_procs():
        try:
            if ipc("status") in {"idle", "listening"}:
                return
        except Exception:
            pass
    spawn_daemon()
    if not wait_alive(25.0):
        raise SystemExit("daemon not up")


def stamp_intro_already_shown() -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if CONFIG.is_file():
        try:
            loaded = json.loads(CONFIG.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    data["tray_intro_shown"] = True
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    global STOP
    stamp_intro_already_shown()
    watcher = threading.Thread(target=dialog_watch, daemon=True)
    watcher.start()
    dismiss_yo_dialogs()
    ensure_daemon()
    ok("rest: daemon up")

    print("--- bind CLI F8/ё 10x ---", flush=True)
    for i in range(1, 11):
        spec = "F8" if i % 2 else "ё"
        try:
            r = run_exe("bind", spec, timeout=6.0)
        except subprocess.TimeoutExpired:
            dismiss_yo_dialogs()
            fail(f"bind-cli {i} {spec}: timeout")
            continue
        cfg = load_cfg()
        code = int(cfg.get("hotkey_keycode") or 0)
        if spec == "F8" and code not in (0x77, 119):
            fail(f"bind-cli {i}: wanted F8 got {code} out={(r.stdout or '')!r}")
        elif spec == "ё" and code not in (49, 0xC0):
            fail(f"bind-cli {i}: wanted ё got {code} out={(r.stdout or '')!r}")
        else:
            ok(f"bind-cli {i}: {spec} code={code}")
        if not yo_procs():
            fail(f"bind-cli {i}: daemon died")
            break
    run_exe("bind", "ё", timeout=6.0)
    dismiss_yo_dialogs()

    print("--- bind via config+reload 10x ---", flush=True)
    for i in range(1, 11):
        cfg = load_cfg()
        if i % 2:
            cfg["hotkey_kind"] = "key"
            cfg["hotkey_keycode"] = 0x77
            expect = {0x77, 119}
            label = "F8"
        else:
            cfg["hotkey_kind"] = "key"
            cfg["hotkey_keycode"] = 49
            expect = {49, 0xC0}
            label = "ё"
        save_cfg(cfg)
        try:
            reply = ipc("reload")
        except Exception as exc:
            fail(f"bind-reload {i}: {exc}")
            continue
        time.sleep(0.2)
        got = int(load_cfg().get("hotkey_keycode") or 0)
        if got not in expect:
            fail(f"bind-reload {i}: {label} cfg={got} reply={reply!r}")
        elif reply != "ok":
            fail(f"bind-reload {i}: reply {reply!r}")
        else:
            ok(f"bind-reload {i}: {label} reply ok")
        if not yo_procs():
            fail(f"bind-reload {i}: daemon died")
            break
    cfg = load_cfg()
    cfg["hotkey_kind"] = "key"
    cfg["hotkey_keycode"] = 49
    save_cfg(cfg)
    ipc("reload")
    assert_no_fatal("bind")

    print("--- rebind IPC 10x ---", flush=True)
    for i in range(1, 11):
        try:
            reply = ipc("rebind")
        except Exception as exc:
            fail(f"rebind {i}: {exc}")
            continue
        if reply != "ok":
            fail(f"rebind {i}: {reply!r}")
        else:
            ok(f"rebind {i}: ok")
        time.sleep(0.25)
        if not yo_procs():
            fail(f"rebind {i}: daemon died")
            break
    time.sleep(0.4)
    assert_no_fatal("rebind")

    print("--- tray L/R 10x ---", flush=True)
    hwnd = loop_hwnd()
    if not hwnd:
        fail("tray: no loop hwnd")
    else:
        ok(f"tray: hwnd {hwnd}")
        for i in range(1, 11):
            user32.PostMessageW(hwnd, WM_TRAYICON, 0, WM_LBUTTONUP)
            time.sleep(0.55)
            try:
                st = ipc("status")
            except Exception as exc:
                fail(f"tray L {i}: {exc}")
                break
            if not yo_procs():
                fail(f"tray L {i}: daemon died")
                break
            ok(f"tray L {i}: {st}")
        try:
            if ipc("status") == "listening":
                ipc("stop")
                time.sleep(0.4)
        except Exception:
            pass
        for i in range(1, 11):
            user32.PostMessageW(hwnd, WM_TRAYICON, 0, WM_RBUTTONUP)
            time.sleep(0.35)
            user32.PostMessageW(hwnd, 0x0100, 0x1B, 0)
            if not yo_procs():
                fail(f"tray R {i}: daemon died")
                break
            ok(f"tray R {i}: alive")
        assert_no_fatal("tray")

    print("--- record/listen 10x ---", flush=True)
    for i in range(1, 11):
        try:
            ipc("start")
        except Exception as exc:
            fail(f"record {i}: start {exc}")
            continue
        deadline = time.monotonic() + 20.0
        st = ""
        while time.monotonic() < deadline:
            try:
                st = ipc("status")
            except Exception as exc:
                st = str(exc)
                break
            if st == "listening":
                break
            time.sleep(0.3)
        if st != "listening":
            fail(f"record {i}: status {st!r}")
        else:
            time.sleep(1.2)
            try:
                ipc("stop")
            except Exception as exc:
                fail(f"record {i}: stop {exc}")
                continue
            st2 = ""
            idle_deadline = time.monotonic() + 5.0
            while time.monotonic() < idle_deadline:
                try:
                    st2 = ipc("status")
                except Exception as exc:
                    st2 = str(exc)
                    break
                if st2 == "idle":
                    break
                time.sleep(0.2)
            if st2 == "idle":
                ok(f"record {i}: listen->idle")
            else:
                fail(f"record {i}: after stop {st2!r}")
        if not yo_procs():
            fail(f"record {i}: daemon died")
            break
    text = log_text()
    if "микрофон молчит" in text or "MIC_SILENT" in text or "захват устройства" in text:
        ok("record: capture/silent path present in log")
    else:
        fail("record: no capture log")
    if "Fatal Python error" not in text:
        ok("record: no fatal")
    else:
        fail("record: fatal")

    print("--- reload 10x ---", flush=True)
    for i in range(1, 11):
        try:
            reply = ipc("reload")
        except Exception as exc:
            fail(f"reload {i}: {exc}")
            continue
        if reply == "ok":
            ok(f"reload {i}: ok")
        else:
            fail(f"reload {i}: {reply!r}")
        if not yo_procs():
            fail(f"reload {i}: daemon died")
            break
    assert_no_fatal("reload")

    STOP = True
    print("=== SUMMARY REST ===")
    print("PASS", len(PASSES))
    print("FAIL", len(FAILS))
    for msg in FAILS:
        print(" -", msg)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
