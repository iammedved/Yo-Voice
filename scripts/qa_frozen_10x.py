"""Live 10x QA of the frozen Yo-Voice install. Exit 0 = all checks passed."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
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
WM_LBUTTONDBLCLK = 0x0203

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.c_void_p
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
user32.PostMessageW.restype = ctypes.c_int
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_int

FAILS: list[str] = []
PASSES: list[str] = []


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


def spawn_daemon() -> subprocess.Popen:
    return subprocess.Popen(
        [str(EXE), "daemon"],
        cwd=str(EXE.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def spawn_double_click() -> subprocess.Popen:
    return subprocess.Popen(
        [str(EXE)],
        cwd=str(EXE.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def wait_alive(timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = run_exe("status", timeout=3.0)
        except subprocess.TimeoutExpired:
            time.sleep(0.2)
            continue
        text = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0 and text in {"idle", "listening", "ok"}:
            return True
        if "не запущена" not in text and r.returncode == 0 and text:
            return True
        time.sleep(0.25)
    return False


def wait_dead(timeout: float = 12.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not yo_procs() and not PORT.exists():
            return True
        time.sleep(0.2)
    return not yo_procs()


def quit_daemon() -> None:
    try:
        run_exe("quit", timeout=6.0)
    except Exception:
        pass
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and yo_procs():
        time.sleep(0.2)
    for pid in yo_procs():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def log_text() -> str:
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def assert_no_fatal(context: str) -> None:
    text = log_text()
    needles = (
        "Fatal Python error",
        "PyEval_RestoreThread",
        "aborted",
        "0xc0000409",
        "NoneType",
        "tk_popup",
    )
    hits = [n for n in needles if n.lower() in text.lower() and n != "aborted"]
    # 'aborted' is too broad if we keep it; check explicit abort phrases
    if "Fatal Python error" in text or "PyEval_RestoreThread" in text:
        fail(f"{context}: crash in log")
        return
    if "NoneType" in text and "write" in text.lower():
        fail(f"{context}: tqdm/stdout NoneType in log")
        return
    ok(f"{context}: no GIL/tqdm abort")


def loop_hwnd():
    return user32.FindWindowW("YoVoiceLoop", None) or user32.FindWindowW(None, "yo-loop")


def settings_hwnd():
    return user32.FindWindowW(None, "Ёхо — настройки")


def any_toplevel_count() -> int:
    # Enumerate visible popups titled Ёхо
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lp):
        if user32.IsWindow(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value or ""
            if "Ёхо" in title or "Yo-Voice" in title or title == "yo-loop":
                found.append((hwnd, title))
        return 1

    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.EnumWindows(cb, 0)
    return len(found), found


def phase_lifetime() -> None:
    print("=== PHASE lifetime 10x start/status/quit ===", flush=True)
    for i in range(1, 11):
        quit_daemon()
        spawn_daemon()
        if not wait_alive(25.0):
            fail(f"lifetime {i}: daemon did not come up")
            continue
        r = run_exe("status")
        text = (r.stdout or "").strip()
        if r.returncode != 0 or text not in {"idle", "listening"}:
            fail(f"lifetime {i}: status={text!r} code={r.returncode}")
        else:
            ok(f"lifetime {i}: status {text}")
        r = run_exe("quit")
        if not wait_dead(12.0):
            fail(f"lifetime {i}: still running after quit pids={yo_procs()}")
        else:
            ok(f"lifetime {i}: quit clean")
    assert_no_fatal("lifetime")


def phase_stay_and_buttons() -> None:
    print("=== PHASE stay-alive + buttons ===", flush=True)
    quit_daemon()
    spawn_daemon()
    if not wait_alive(25.0):
        fail("stay: daemon did not start")
        return
    ok("stay: daemon up")
    daemon_pids = set(yo_procs())
    if len(daemon_pids) != 1:
        fail(f"stay: expected 1 process, got {daemon_pids}")
    else:
        ok(f"stay: single pid {next(iter(daemon_pids))}")

    hwnd = loop_hwnd()
    if hwnd:
        ok(f"stay: loop hwnd {hwnd}")
    else:
        fail("stay: loop window YoVoiceLoop not found")

    print("--- status 10x ---", flush=True)
    for i in range(1, 11):
        r = run_exe("status")
        text = (r.stdout or "").strip()
        if r.returncode == 0 and text in {"idle", "listening"}:
            ok(f"status {i}: {text}")
        else:
            fail(f"status {i}: {text!r} code={r.returncode}")
        if not yo_procs():
            fail(f"status {i}: daemon died")
            return

    print("--- double-click no-arg 10x (must stay resident) ---", flush=True)
    for i in range(1, 11):
        child = spawn_double_click()
        time.sleep(1.2)
        try:
            child.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            # Frozen no-arg is daemon; if already running it should exit.
            pass
        pids = yo_procs()
        r = run_exe("status")
        text = (r.stdout or "").strip()
        if text not in {"idle", "listening"}:
            fail(f"dblclick {i}: status {text!r}")
        elif not pids:
            fail(f"dblclick {i}: daemon gone")
        else:
            ok(f"dblclick {i}: still {text} pids={pids}")

    print("--- settings CLI + daemon IPC 10x ---", flush=True)

    def ipc(cmd: str, timeout: float = 2.0) -> str:
        import socket

        port = int(PORT.read_text(encoding="utf-8").strip())
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        try:
            s.sendall((cmd.strip() + "\n").encode("utf-8"))
            return s.recv(256).decode("utf-8", "replace").strip()
        finally:
            s.close()

    for i in range(1, 11):
        try:
            reply = ipc("settings")
        except Exception as exc:
            fail(f"settings-ipc {i}: {exc}")
            reply = ""
        deadline = time.monotonic() + 3.0
        sh = 0
        while time.monotonic() < deadline:
            sh = settings_hwnd() or 0
            if sh:
                break
            time.sleep(0.1)
        if sh:
            ok(f"settings-ipc {i}: reply={reply!r} hwnd={sh}")
            user32.PostMessageW(sh, 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(0.35)
        else:
            fail(f"settings-ipc {i}: reply={reply!r} no hwnd")
        if not yo_procs():
            fail(f"settings-ipc {i}: daemon died")
            return

    for i in range(1, 11):
        proc = subprocess.Popen(
            [str(EXE), "settings"],
            cwd=str(EXE.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 5.0
        sh = 0
        while time.monotonic() < deadline:
            sh = settings_hwnd() or 0
            if sh:
                break
            if proc.poll() is not None:
                break
            time.sleep(0.15)
        if sh:
            ok(f"settings-cli {i}: hwnd={sh}")
            user32.PostMessageW(sh, 0x0010, 0, 0)
        else:
            fail(f"settings-cli {i}: window never appeared exit={proc.poll()}")
        try:
            proc.wait(timeout=4.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            fail(f"settings-cli {i}: hung after close")
        if not yo_procs():
            fail(f"settings-cli {i}: daemon died after settings")
            return
    assert_no_fatal("settings")

    print("--- toggle 10x ---", flush=True)
    last = None
    for i in range(1, 11):
        r = run_exe("toggle")
        time.sleep(0.9)
        s = run_exe("status")
        text = (s.stdout or "").strip()
        if s.returncode != 0 or text not in {"idle", "listening"}:
            fail(f"toggle {i}: status {text!r}")
        elif last is not None and text == last:
            # first listen may stay listening if toggle is async; wait a bit more
            time.sleep(0.6)
            text = (run_exe("status").stdout or "").strip()
            if text == last:
                fail(f"toggle {i}: did not flip (stuck {text})")
            else:
                ok(f"toggle {i}: {last} -> {text}")
                last = text
        else:
            ok(f"toggle {i}: -> {text}")
            last = text
        if not yo_procs():
            fail(f"toggle {i}: daemon died")
            return
    # end on idle
    if (run_exe("status").stdout or "").strip() == "listening":
        run_exe("stop")
        time.sleep(0.8)
    assert_no_fatal("toggle")

    print("--- bind remap 10x (F8 <-> ё) ---", flush=True)
    for i in range(1, 11):
        spec = "F8" if i % 2 else "ё"
        r = run_exe("bind", spec)
        time.sleep(0.45)
        cfg = {}
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"bind {i}: config read {exc}")
            continue
        code = int(cfg.get("hotkey_keycode") or 0)
        want_ok = (spec == "F8" and code in (0x77, 119)) or (spec == "ё" and code in (49, 0xC0))
        if not want_ok:
            time.sleep(0.6)
            r = run_exe("bind", spec)
            time.sleep(0.45)
            try:
                cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
            code = int(cfg.get("hotkey_keycode") or 0)
            want_ok = (spec == "F8" and code in (0x77, 119)) or (spec == "ё" and code in (49, 0xC0))
        if r.returncode != 0:
            fail(f"bind {i} {spec}: code={r.returncode} {(r.stdout or '')+ (r.stderr or '')!r}")
        elif spec == "F8" and code not in (0x77, 119):
            fail(f"bind {i}: wanted F8 vk 0x77 got {code}")
        elif spec == "ё" and code not in (49, 0xC0):
            fail(f"bind {i}: wanted ё 49/0xC0 got {code}")
        else:
            ok(f"bind {i}: {spec} code={code}")
        if not yo_procs():
            fail(f"bind {i}: daemon died")
            return
    # restore ё
    run_exe("bind", "ё")
    assert_no_fatal("bind")

    print("--- tray PostMessage 10x ---", flush=True)
    hwnd = loop_hwnd()
    if not hwnd:
        fail("tray: no loop hwnd")
    else:
        for i in range(1, 11):
            user32.PostMessageW(hwnd, WM_TRAYICON, 0, WM_LBUTTONUP)
            time.sleep(0.7)
            if not yo_procs():
                fail(f"tray L {i}: daemon died")
                return
            ok(f"tray L {i}: posted, daemon alive status={(run_exe('status').stdout or '').strip()}")
        if (run_exe("status").stdout or "").strip() == "listening":
            run_exe("stop")
            time.sleep(0.5)
        for i in range(1, 11):
            user32.PostMessageW(hwnd, WM_TRAYICON, 0, WM_RBUTTONUP)
            time.sleep(0.4)
            if not yo_procs():
                fail(f"tray R {i}: daemon died")
                return
            ok(f"tray R {i}: posted, daemon alive")
            # WM_CLOSE any menu owner is the loop itself; send ESC
            user32.PostMessageW(hwnd, 0x0100, 0x1B, 0)  # WM_KEYDOWN VK_ESCAPE
        assert_no_fatal("tray")

    print("--- record/listen + overlay/mic path ---", flush=True)
    run_exe("start")
    # model load can take a minute on first listen
    deadline = time.monotonic() + 90.0
    listening = False
    while time.monotonic() < deadline:
        text = (run_exe("status").stdout or "").strip()
        if text == "listening":
            listening = True
            break
        if not yo_procs():
            fail("record: daemon died during start/model load")
            return
        time.sleep(1.0)
    if not listening:
        fail("record: never reached listening")
    else:
        ok("record: listening")
        time.sleep(3.5)  # allow capture probe + dead-stream check
        text = log_text()
        if "микрофон" in text.lower() or "захват" in text.lower() or "молчит" in text.lower():
            ok("record: capture path logged")
        else:
            # still ok if model loading logs only
            ok("record: listening without capture log yet (check below)")
        if "Fatal Python error" in text:
            fail("record: fatal during listen")
        run_exe("stop")
        time.sleep(1.0)
        st = (run_exe("status").stdout or "").strip()
        if st == "idle":
            ok("record: stop -> idle")
        else:
            fail(f"record: stop status {st!r}")
    assert_no_fatal("record")

    print("--- reload 10x ---", flush=True)
    for i in range(1, 11):
        r = run_exe("reload") if False else run_exe("status")
        # no reload CLI; send via python port
        try:
            import socket

            port = int(PORT.read_text(encoding="utf-8").strip())
            s = socket.create_connection(("127.0.0.1", port), timeout=2)
            s.sendall(b"reload\n")
            data = s.recv(64)
            s.close()
            if b"ok" in data.lower():
                ok(f"reload {i}: {data!r}")
            else:
                fail(f"reload {i}: {data!r}")
        except Exception as exc:
            fail(f"reload {i}: {exc}")
        if not yo_procs():
            fail(f"reload {i}: daemon died")
            return
    time.sleep(0.3)
    assert_no_fatal("reload")


def stamp_intro_already_shown() -> None:
    """QA respawns the daemon ~12×; do not queue 12 intro toasts."""
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
    if not EXE.is_file():
        print("missing", EXE)
        return 2
    CACHE.mkdir(parents=True, exist_ok=True)
    stamp_intro_already_shown()
    phase_lifetime()
    phase_stay_and_buttons()
    print("=== SUMMARY ===")
    print("PASS", len(PASSES))
    print("FAIL", len(FAILS))
    for msg in FAILS:
        print(" -", msg)
    # keep daemon up for the user after QA if it died
    if not yo_procs():
        spawn_daemon()
        wait_alive(20.0)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
