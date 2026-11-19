# -*- coding: utf-8 -*-
"""Efeitos sonoros (SoundPlayer pelo MCI), volume do Windows (Core Audio) e
niveis dos faders: master (saida), effects (sons do Stream Deck) e mic."""
import os
import queue
import threading

from . import paths

IS_WINDOWS = paths.IS_WINDOWS
TARGETS = ("master", "effects", "mic")


# ------------------------------------------------------------ efeitos sonoros ---
def sound_path(name):
    name = str(name).strip().strip('"')
    if os.path.isabs(name):
        return name
    return os.path.join(paths.SOUNDS_DIR, name)


def list_sounds():
    if not os.path.isdir(paths.SOUNDS_DIR):
        return []
    out = []
    for root, _dirs, files in os.walk(paths.SOUNDS_DIR):
        for f in files:
            if f.lower().endswith(paths.SOUND_EXT):
                out.append(os.path.relpath(os.path.join(root, f), paths.SOUNDS_DIR).replace("\\", "/"))
    return sorted(out, key=str.lower)


class SoundPlayer:
    """Toca varios sons ao mesmo tempo pelo MCI do Windows (sem dependencias).
    Todos os comandos rodam numa unica thread, como o MCI prefere."""

    def __init__(self):
        self.q = queue.Queue()
        self.playing = []          # [(alias, volume do botao)]
        self.n = 0
        self.level = 100           # fader EFEITOS
        self.muted = False
        threading.Thread(target=self._loop, daemon=True).start()

    def effective(self, volume):
        if self.muted:
            return 0
        return int(max(0, min(100, int(volume))) * self.level / 100)

    def set_level(self, level=None, muted=None):
        if level is not None:
            self.level = max(0, min(100, int(level)))
        if muted is not None:
            self.muted = bool(muted)
        self.q.put(("vol",))

    def play(self, path, volume=100, exclusive=False):
        self.q.put(("play", path, volume, exclusive))

    def stop_all(self):
        self.q.put(("stop",))

    def _mci(self, cmd):
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0)
        if err:
            ebuf = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(err, ebuf, 255)
            raise RuntimeError(ebuf.value or "erro MCI %d" % err)
        return buf.value

    def _close(self, alias):
        try:
            self._mci("close " + alias)
        except Exception:
            pass

    def _loop(self):
        while True:
            try:
                item = self.q.get(timeout=1)
            except queue.Empty:
                item = None
            if IS_WINDOWS:
                for entry in list(self.playing):  # libera sons que terminaram
                    try:
                        if self._mci("status %s mode" % entry[0]) != "playing":
                            self._close(entry[0])
                            self.playing.remove(entry)
                    except Exception:
                        self.playing.remove(entry)
            if item is None:
                continue
            if item[0] == "vol":           # fader mexeu: ajusta o que ja esta tocando
                for alias, vol in self.playing:
                    if IS_WINDOWS:
                        try:
                            self._mci("setaudio %s volume to %d" % (alias, self.effective(vol) * 10))
                        except Exception:
                            pass
                continue
            if item[0] == "stop" or (item[0] == "play" and item[3]):
                for alias, _vol in self.playing:
                    if IS_WINDOWS:
                        self._close(alias)
                self.playing = []
                if item[0] == "stop":
                    print("  sons parados")
                    continue
            _, path, volume, _ = item
            if not IS_WINDOWS:
                print("  [simulado] tocar:", path, "vol", self.effective(volume))
                continue
            self.n += 1
            alias = "sd%d" % self.n
            try:
                self._mci('open "%s" type mpegvideo alias %s' % (path, alias))
                try:
                    self._mci("setaudio %s volume to %d" % (alias, self.effective(volume) * 10))
                except Exception:
                    pass
                self._mci("play " + alias)
                self.playing.append((alias, volume))
            except Exception as e:
                print("  erro ao tocar %s: %s" % (path, e))
                self._close(alias)


PLAYER = SoundPlayer()


# ------------------------------------------------- volume do Windows (Core Audio) ---
def _endpoint(flow):
    """IAudioEndpointVolume do dispositivo padrao: flow 0 = saida (alto-falante),
    1 = entrada (microfone)."""
    import ctypes
    from ctypes import POINTER, byref, c_void_p, HRESULT, WINFUNCTYPE

    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 0)   # cada thread do servidor inicializa o COM

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort),
                    ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def guid(text):
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(g))
        return g

    def method(obj, index, *argtypes):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        return WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[index])

    clsid = guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    iid_enum = guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    iid_vol = guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")
    enum, dev, vol = c_void_p(), c_void_p(), c_void_p()
    hr = ole32.CoCreateInstance(byref(clsid), None, 0x17, byref(iid_enum), byref(enum))
    if hr != 0 or not enum.value:
        raise OSError("audio indisponivel (%x)" % (hr & 0xFFFFFFFF))
    try:
        method(enum, 4, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(enum, flow, 0, byref(dev))
        method(dev, 3, POINTER(GUID), ctypes.c_ulong, c_void_p, POINTER(c_void_p))(
            dev, byref(iid_vol), 0x17, None, byref(vol))
    finally:
        if dev.value:
            method(dev, 2)(dev)
        method(enum, 2)(enum)
    return vol, method


SIM_VOL = {}   # volume simulado fora do Windows


def win_volume(flow, level=None, toggle_mute=False):
    """Le (e opcionalmente muda) volume 0-100 e mudo. Devolve (nivel, mudo)."""
    if not IS_WINDOWS:
        st = SIM_VOL.setdefault(flow, [60, False])
        if level is not None:
            st[0] = max(0, min(100, int(level)))
        if toggle_mute:
            st[1] = not st[1]
        return st[0], st[1]
    import ctypes
    from ctypes import POINTER, byref
    vol, method = _endpoint(flow)
    try:
        if level is not None:
            method(vol, 7, ctypes.c_float, ctypes.c_void_p)(vol, max(0.0, min(1.0, level / 100.0)), None)
        mute = ctypes.c_int()
        method(vol, 15, POINTER(ctypes.c_int))(vol, byref(mute))
        if toggle_mute:
            method(vol, 14, ctypes.c_int, ctypes.c_void_p)(vol, 0 if mute.value else 1, None)
            mute.value = 0 if mute.value else 1
        cur = ctypes.c_float()
        method(vol, 9, POINTER(ctypes.c_float))(vol, byref(cur))
        return int(round(cur.value * 100)), bool(mute.value)
    finally:
        method(vol, 2)(vol)


VOL_TARGETS = {"master": 0, "mic": 1}   # fluxo do Core Audio


def levels():
    """{master: {v, muted}, effects: {...}, mic: {...}}; v = None se indisponivel."""
    out = {"effects": {"v": PLAYER.level, "muted": PLAYER.muted}}
    for name, flow in VOL_TARGETS.items():
        try:
            v, m = win_volume(flow)
        except Exception:
            v, m = None, False
        out[name] = {"v": v, "muted": m}
    return out


def set_level(target, value=None, toggle_mute=False):
    if target == "effects":
        PLAYER.set_level(value, (not PLAYER.muted) if toggle_mute else None)
    elif target in VOL_TARGETS:
        win_volume(VOL_TARGETS[target], value, toggle_mute)
    else:
        raise ValueError("controle desconhecido: %s" % target)
