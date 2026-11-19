# -*- coding: utf-8 -*-
"""Icone na bandeja do Windows (area de notificacao), so com ctypes.

Roda numa thread propria (janela escondida + GetMessageW). Qualquer falha
so gera um aviso no log: o servidor continua rodando sem o icone.
Fora do Windows start() nao faz nada e devolve False."""
import os
import sys
import threading
import time

IS_WINDOWS = sys.platform.startswith("win")

# ids dos itens do menu
ID_CONECTAR = 1001
ID_EDITAR = 1002
ID_PASTA = 1003
ID_LOG = 1004
ID_AUTOSTART = 1005
ID_UPDATE = 1006
ID_CONSOLE = 1007
ID_SAIR = 1099
SEP = None   # id de separador

UPDATE_POLL = 60.0   # segundos entre conferencias de atualizacao

_STATE = {"running": False, "thread": None, "hwnd": None, "post_quit": None}


def tooltip(port, version=None):
    """Texto que aparece ao passar o mouse no icone (max 127 caracteres)."""
    txt = "Stream Deck"
    if version:
        txt += " %s" % version
    txt += " — porta %d" % port
    return txt[:127]


def build_menu(st):
    """Modelo do menu (testavel sem Win32).

    st: dict com has_console, console_visible, autostart, autostart_ok,
    update_latest (str ou None).
    Devolve lista de (id, rotulo, marcado, habilitado); separador = (None, "-", False, False)."""
    items = [
        (ID_CONECTAR, "Conectar um aparelho", False, True),
        (ID_EDITAR, "Editar botões", False, True),
        (ID_PASTA, "Abrir pasta de dados", False, True),
        (ID_LOG, "Abrir log", False, True),
    ]
    if st.get("has_console"):
        items.append((ID_CONSOLE, "Mostrar janela do log", bool(st.get("console_visible")), True))
    items.append((SEP, "-", False, False))
    items.append((ID_AUTOSTART, "Iniciar com o Windows", bool(st.get("autostart")),
                  bool(st.get("autostart_ok", True))))
    if st.get("update_latest"):
        items.append((ID_UPDATE, "Atualização disponível: %s" % st["update_latest"], False, True))
    items.append((SEP, "-", False, False))
    items.append((ID_SAIR, "Sair", False, True))
    return items


def update_balloon(update, shown):
    """Texto do aviso de atualizacao ou None. shown: set de versoes ja avisadas."""
    if not (update and update.get("available") and update.get("latest")):
        return None
    v = update["latest"]
    if v in shown:
        return None
    shown.add(v)
    return ("Atualização disponível",
            "Stream Deck %s está disponível. Clique em Conectar para atualizar." % v)


# ---------------------------------------------------------------- console

def console_hwnd():
    if not IS_WINDOWS:
        return 0
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleWindow() or 0
    except Exception:
        return 0


def show_console(show):
    h = console_hwnd()
    if not h:
        return False
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(h, 9 if show else 0)   # SW_RESTORE / SW_HIDE
        if show:
            ctypes.windll.user32.SetForegroundWindow(h)
        return True
    except Exception:
        return False


def console_visible():
    h = console_hwnd()
    if not h:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsWindowVisible(h))
    except Exception:
        return False


# ---------------------------------------------------------------- inicio

def start(port, srv, version=None):
    """Sobe o icone numa thread. True se a thread foi iniciada."""
    if not IS_WINDOWS or _STATE["running"]:
        return False
    ready = threading.Event()
    ok = [False]

    def run():
        try:
            _Tray(port, srv, version).loop(ready, ok)
        except Exception as e:  # noqa: BLE001
            print("  aviso: icone na bandeja indisponivel (%s)" % e)
        finally:
            _STATE["running"] = False
            ready.set()

    t = threading.Thread(target=run, name="bandeja", daemon=True)
    _STATE.update(running=True, thread=t)
    t.start()
    ready.wait(5.0)
    return ok[0]


def stop():
    """Tira o icone (ex.: antes de os._exit)."""
    fn = _STATE.get("post_quit")
    if fn:
        try:
            fn()
        except Exception:
            pass


# ---------------------------------------------------------------- Win32

class _Tray:
    WM_USER = 0x0400
    WM_TRAY = WM_USER + 20
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_COMMAND = 0x0111
    WM_NULL = 0x0000
    WM_TIMER = 0x0113
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_CONTEXTMENU = 0x007B
    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10
    NIIF_INFO = 1
    MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_GRAYED = 0, 0x800, 0x8, 0x1
    TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80

    def __init__(self, port, srv, version):
        import ctypes
        from ctypes import wintypes as w
        self.ct, self.w = ctypes, w
        self.port, self.srv, self.version = port, srv, version
        self.shown_updates = set()
        self.last_click = 0.0
        self.u32 = ctypes.WinDLL("user32", use_last_error=True)
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.sh32 = ctypes.WinDLL("shell32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        self.WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", w.UINT), ("lpfnWndProc", self.WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON),
                        ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE), ("lpszMenuName", w.LPCWSTR),
                        ("lpszClassName", w.LPCWSTR)]

        class GUID(ctypes.Structure):
            _fields_ = [("a", w.DWORD), ("b", w.WORD), ("c", w.WORD), ("d", ctypes.c_ubyte * 8)]

        class NOTIFYICONDATAW(ctypes.Structure):
            # layout completo (Vista+), cbSize = sizeof -> vale para Win 7+
            _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                        ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                        ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                        ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                        ("guidItem", GUID), ("hBalloonIcon", w.HICON)]

        class POINT(ctypes.Structure):
            _fields_ = [("x", w.LONG), ("y", w.LONG)]

        self.WNDCLASSW, self.NID, self.POINT = WNDCLASSW, NOTIFYICONDATAW, POINT
        u = self.u32
        u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        u.DefWindowProcW.restype = LRESULT
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.RegisterClassW.restype = w.ATOM
        u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
        u.CreateWindowExW.restype = w.HWND
        u.RegisterWindowMessageW.argtypes = [w.LPCWSTR]
        u.RegisterWindowMessageW.restype = w.UINT
        u.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        u.GetMessageW.restype = w.BOOL
        u.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
        u.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
        u.DispatchMessageW.restype = LRESULT
        u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        u.CreatePopupMenu.restype = w.HMENU
        u.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
        u.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID]
        u.TrackPopupMenu.restype = w.BOOL
        u.DestroyMenu.argtypes = [w.HMENU]
        u.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        u.SetForegroundWindow.argtypes = [w.HWND]
        u.DestroyWindow.argtypes = [w.HWND]
        u.KillTimer.argtypes = [w.HWND, ctypes.c_size_t]
        u.IsWindowVisible.argtypes = [w.HWND]
        u.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID]
        u.SetTimer.restype = ctypes.c_size_t
        u.LoadIconW.argtypes = [w.HINSTANCE, w.LPVOID]
        u.LoadIconW.restype = w.HICON
        u.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
        u.LoadImageW.restype = w.HANDLE
        u.GetDoubleClickTime.restype = w.UINT
        self.sh32.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        self.sh32.Shell_NotifyIconW.restype = w.BOOL
        self.sh32.ExtractIconW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT]
        self.sh32.ExtractIconW.restype = w.HICON
        self.k32.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self.k32.GetModuleHandleW.restype = w.HMODULE

    # ---- icone
    def _load_icon(self):
        from . import paths
        if paths.FROZEN:
            try:
                h = self.sh32.ExtractIconW(None, sys.executable, 0)
                if h and h != 1:
                    return h
            except Exception:
                pass
        ico = os.path.join(paths.APP_DIR, "icon.ico")
        if os.path.exists(ico):
            h = self.u32.LoadImageW(None, ico, 1, 0, 0, 0x10 | 0x40)   # IMAGE_ICON, LR_LOADFROMFILE|LR_DEFAULTSIZE
            if h:
                return h
        return self.u32.LoadIconW(None, self.ct.c_void_p(32512))       # IDI_APPLICATION

    def _nid(self, flags):
        n = self.NID()
        n.cbSize = self.ct.sizeof(self.NID)
        n.hWnd = self.hwnd
        n.uID = 1
        n.uFlags = flags
        n.uCallbackMessage = self.WM_TRAY
        n.hIcon = self.hicon
        n.szTip = tooltip(self.port, self.version)
        return n

    def add_icon(self):
        n = self._nid(self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP)
        return bool(self.sh32.Shell_NotifyIconW(self.NIM_ADD, self.ct.byref(n)))

    def remove_icon(self):
        try:
            n = self._nid(0)
            self.sh32.Shell_NotifyIconW(self.NIM_DELETE, self.ct.byref(n))
        except Exception:
            pass

    def balloon(self, title, text):
        try:
            n = self._nid(self.NIF_INFO)
            n.szInfoTitle = title[:63]
            n.szInfo = text[:255]
            n.dwInfoFlags = self.NIIF_INFO
            self.sh32.Shell_NotifyIconW(self.NIM_MODIFY, self.ct.byref(n))
        except Exception:
            pass

    # ---- menu
    def _menu_state(self):
        from . import updates, winapi
        try:
            auto, auto_ok = winapi.autostart_enabled(), True
        except Exception:
            auto, auto_ok = False, False
        up = updates.UPDATE
        return {"has_console": bool(console_hwnd()), "console_visible": console_visible(),
                "autostart": auto, "autostart_ok": auto_ok,
                "update_latest": up.get("latest") if up.get("available") else None}

    def show_menu(self):
        u = self.u32
        menu = u.CreatePopupMenu()
        try:
            for mid, label, checked, enabled in build_menu(self._menu_state()):
                if mid is SEP:
                    u.AppendMenuW(menu, self.MF_SEPARATOR, 0, None)
                    continue
                flags = self.MF_STRING | (self.MF_CHECKED if checked else 0) | (0 if enabled else self.MF_GRAYED)
                u.AppendMenuW(menu, flags, mid, label)
            pt = self.POINT()
            u.GetCursorPos(self.ct.byref(pt))
            u.SetForegroundWindow(self.hwnd)
            cmd = u.TrackPopupMenu(menu, self.TPM_RIGHTBUTTON | self.TPM_RETURNCMD | self.TPM_NONOTIFY,
                                   pt.x, pt.y, 0, self.hwnd, None)
            u.PostMessageW(self.hwnd, self.WM_NULL, 0, 0)
        finally:
            u.DestroyMenu(menu)
        if cmd:
            self.command(cmd)

    def _open(self, path):
        import webbrowser
        webbrowser.open("http://127.0.0.1:%d%s" % (self.port, path))

    def command(self, cmd):
        from . import paths, winapi
        try:
            if cmd in (ID_CONECTAR, ID_UPDATE):
                self._open("/conectar")
            elif cmd == ID_EDITAR:
                self._open("/editar")
            elif cmd == ID_PASTA:
                winapi.open_folder(paths.BASE)
            elif cmd == ID_LOG:
                os.startfile(paths.LOG_PATH)
            elif cmd == ID_CONSOLE:
                show_console(not console_visible())
            elif cmd == ID_AUTOSTART:
                winapi.set_autostart(not winapi.autostart_enabled())
            elif cmd == ID_SAIR:
                self.quit()
        except Exception as e:  # noqa: BLE001
            print("  aviso: menu da bandeja: %s" % e)

    def quit(self):
        print("Encerrando (pelo icone da bandeja)...")
        self.remove_icon()
        threading.Thread(target=self._shutdown_srv, daemon=True).start()
        threading.Timer(1.5, os._exit, [0]).start()

    def _shutdown_srv(self):
        try:
            self.srv.shutdown()
        except Exception:
            pass

    # ---- janela
    def wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == self.WM_TRAY:
                ev = lparam & 0xFFFF
                if ev == self.WM_LBUTTONDBLCLK:
                    self.dbl = True
                    self._open("/conectar")
                elif ev in (self.WM_RBUTTONUP, self.WM_CONTEXTMENU):
                    self.show_menu()
                elif ev == self.WM_LBUTTONUP:
                    # espera o tempo do duplo clique para nao abrir menu + pagina
                    self.dbl = False
                    self.u32.SetTimer(hwnd, 2, self.u32.GetDoubleClickTime(), None)
                return 0
            if msg == self.WM_TIMER:
                if wparam == 2:
                    self.u32.KillTimer(hwnd, 2)
                    if not self.dbl:
                        self.show_menu()
                elif wparam == 1:
                    self.check_update()
                return 0
            if msg == self.taskbar_created and self.taskbar_created:
                self.add_icon()
                return 0
            if msg == self.WM_CLOSE:
                self.remove_icon()
                self.u32.DestroyWindow(hwnd)
                return 0
            if msg == self.WM_DESTROY:
                self.u32.PostQuitMessage(0)
                return 0
        except Exception as e:  # noqa: BLE001
            print("  aviso: bandeja: %s" % e)
        return self.u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def check_update(self):
        from . import updates
        msg = update_balloon(updates.UPDATE, self.shown_updates)
        if msg:
            self.balloon(*msg)

    def loop(self, ready, ok):
        ct, w, u = self.ct, self.w, self.u32
        self.dbl = False
        self._proc = self.WNDPROC(self.wndproc)   # manter referencia viva
        hinst = self.k32.GetModuleHandleW(None)
        wc = self.WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = "StreamDeckTray"
        if not u.RegisterClassW(ct.byref(wc)):
            raise OSError("RegisterClassW falhou (%d)" % ct.get_last_error())
        # janela de nivel superior escondida (nao HWND_MESSAGE): so assim recebe TaskbarCreated
        self.hwnd = u.CreateWindowExW(0, "StreamDeckTray", "Stream Deck", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise OSError("CreateWindowExW falhou (%d)" % ct.get_last_error())
        self.taskbar_created = u.RegisterWindowMessageW("TaskbarCreated")
        self.hicon = self._load_icon()
        if not self.add_icon():
            # Explorer pode ainda nao estar pronto (logon): tenta mais um pouco
            for _ in range(10):
                time.sleep(1.0)
                if self.add_icon():
                    break
            else:
                u.DestroyWindow(self.hwnd)
                raise OSError("Shell_NotifyIconW falhou")
        hwnd = self.hwnd
        _STATE.update(hwnd=hwnd, post_quit=lambda: (self.remove_icon(), u.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)))
        u.SetTimer(hwnd, 1, int(UPDATE_POLL * 1000), None)
        ok[0] = True
        ready.set()
        msg = w.MSG()
        while u.GetMessageW(ct.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ct.byref(msg))
            u.DispatchMessageW(ct.byref(msg))
        self.remove_icon()
