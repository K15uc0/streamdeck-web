# -*- coding: utf-8 -*-
"""Janelas do Windows: app em foco, lista de janelas abertas, trazer janela
para a frente e achar janela pelo nome do .exe. Fora do Windows: vazio/simulado."""
import os
import sys
import threading
import time

IS_WINDOWS = sys.platform.startswith("win")

_FG_CACHE = {"t": 0.0, "exe": None}
_FG_LOCK = threading.Lock()


_API = []


def _api():
    if not _API:
        _API.append(_make_api())
    return _API[0]


def _make_api():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetWindow.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    user32.IsWindow.argtypes = [wintypes.HWND]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    return ctypes, wintypes, user32, kernel32


def _pid_path(pid):
    ctypes, wintypes, _u, kernel32 = _api()
    h = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(h)


def _hwnd_pid(hwnd):
    ctypes, wintypes, user32, _k = _api()
    pid = wintypes.DWORD()
    tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value, tid


def foreground_exe():
    """Nome do .exe da janela em foco, minusculo (None fora do Windows ou se
    nao der para saber). Guardado por ~300 ms (o /api/state e frequente)."""
    if not IS_WINDOWS:
        return None
    with _FG_LOCK:
        now = time.time()
        if now - _FG_CACHE["t"] < 0.3:
            return _FG_CACHE["exe"]
        exe = None
        try:
            _c, _w, user32, _k = _api()
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                path = _pid_path(_hwnd_pid(hwnd)[0])
                if path:
                    exe = os.path.basename(path).lower()
        except Exception:
            exe = None
        _FG_CACHE["t"], _FG_CACHE["exe"] = now, exe
        return exe


def list_windows():
    """[{title, exe, path, hwnd}] das janelas visiveis de primeiro nivel, sem
    janelas de ferramenta nem sem titulo; uma por (exe, titulo)."""
    if not IS_WINDOWS:
        return []
    ctypes, wintypes, user32, _k = _api()
    GWL_EXSTYLE, WS_EX_TOOLWINDOW, GW_OWNER = -20, 0x80, 4
    found = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            if user32.GetWindow(hwnd, GW_OWNER):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.strip()
            if title:
                found.append((hwnd, title))
        except Exception:
            pass
        return True

    proc = WNDENUMPROC(cb)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows(proc, 0)
    out, seen = [], set()
    paths = {}
    for hwnd, title in found:
        pid = _hwnd_pid(hwnd)[0]
        if pid not in paths:
            paths[pid] = _pid_path(pid) or ""
        path = paths[pid]
        exe = os.path.basename(path).lower() if path else ""
        if exe in ("explorer.exe", "textinputhost.exe", "applicationframehost.exe") and title in (
                "Program Manager", "Windows Input Experience"):
            continue
        sig = (exe, title)
        if sig in seen:
            continue
        seen.add(sig)
        out.append({"title": title, "exe": exe, "path": path, "hwnd": int(hwnd or 0)})
    return out


def find_window(exe):
    """hwnd da primeira janela (na ordem Z, a mais recente primeiro) do exe."""
    exe = os.path.basename(str(exe).strip().strip('"')).lower()
    if not exe.endswith(".exe"):
        exe += ".exe"
    for w in list_windows():
        if w["exe"] == exe:
            return w["hwnd"]
    return None


def focus(hwnd):
    """Traz a janela para a frente (restaura se minimizada). O Windows so deixa
    o processo em foco trocar o foco: usa o truque de "anexar" a fila de
    entrada da janela em foco e, se nao bastar, um toque na tecla Alt."""
    if not IS_WINDOWS:
        print("  [simulado] focar janela", hwnd)
        return True
    ctypes, wintypes, user32, kernel32 = _api()
    hwnd = wintypes.HWND(hwnd)
    if not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)        # SW_RESTORE
    else:
        user32.ShowWindow(hwnd, 5)        # SW_SHOW
    user32.AllowSetForegroundWindow(0xFFFFFFFF)   # ASFW_ANY
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    fg_tid = _hwnd_pid(fg)[1] if fg else 0
    target_tid = _hwnd_pid(hwnd)[1]
    attached = []
    try:
        for tid in (fg_tid, target_tid):
            if tid and tid != me and user32.AttachThreadInput(me, tid, True):
                attached.append(tid)
        user32.BringWindowToTop(hwnd)
        ok = user32.SetForegroundWindow(hwnd)
    finally:
        for tid in attached:
            user32.AttachThreadInput(me, tid, False)
    if not ok or user32.GetForegroundWindow() != hwnd.value:
        # truque da tecla Alt: o Windows libera a troca de foco apos uma tecla
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        ok = user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    return bool(ok)


def foreground_hwnd():
    if not IS_WINDOWS:
        return None
    _c, _w, user32, _k = _api()
    h = user32.GetForegroundWindow()
    return int(h) if h else None


def window_title(hwnd):
    if not IS_WINDOWS:
        return ""
    ctypes, wintypes, user32, _k = _api()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(max(1, n + 1))
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value
