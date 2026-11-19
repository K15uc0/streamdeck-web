# -*- coding: utf-8 -*-
"""Efeitos sonoros (SoundPlayer), volume do Windows (Core Audio) e niveis dos
faders: master (saida), effects (sons do Stream Deck, ate 200%) e mic.

Efeitos ate 100% tocam pelo MCI (como sempre). Acima de 100% o som e
decodificado para PCM (WAV pelo modulo wave; MP3/WMA/M4A pelo Media
Foundation do Windows) e tocado pelo waveOut com ganho e corte (clipping)
feitos em Python. Se a decodificacao falhar, toca pelo MCI a 100%."""
import os
import queue
import threading
import time
from array import array

from . import paths

IS_WINDOWS = paths.IS_WINDOWS
TARGETS = ("master", "effects", "mic")
MAX_LEVEL = {"master": 100, "effects": 200, "mic": 100}
MAX_EFFECT = 200          # volume maximo de um efeito (botao x fader)


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


FADE_STEPS = 20           # degraus de volume nas transicoes suaves pelo MCI
SIM_DEFAULT_DUR = 3.0     # duracao simulada (fora do Windows) quando nao da para saber


def quick_duration(path):
    """Duracao (s) sem decodificar: WAV pelo modulo wave; senao None."""
    if not path.lower().endswith(".wav"):
        return None
    try:
        import wave
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            return w.getnframes() / float(rate) if rate else None
    except Exception:
        return None


def _sim_duration(path):
    d = quick_duration(path)
    if d:
        return d
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    # ~128 kbps (MP3 comum) = 16000 bytes/s; minimo de 3 s para dar tempo de ver
    return min(600.0, max(SIM_DEFAULT_DUR, size / 16000.0))


def _ms(v):
    try:
        return max(0, min(5000, int(v or 0)))
    except (TypeError, ValueError):
        return 0


class SoundPlayer:
    """Toca varios sons ao mesmo tempo. Comandos do MCI rodam numa unica
    thread (como o MCI prefere); cada som amplificado (>100%) toca na sua
    propria thread pelo waveOut, que o Windows mistura com os outros.
    Cada som tocado vira uma "faixa" (botao de origem, arquivo, inicio,
    duracao) para o /api/state mostrar o progresso."""

    def __init__(self):
        self.q = queue.Queue()
        self.playing = []          # [[alias, volume do botao, faixa, fator de fade, saindo]] pelo MCI
        self.pcm = []              # [PcmSound] pelo waveOut
        self.pcm_lock = threading.Lock()
        self.tracks = []           # faixas tocando (dicts)
        self.tracks_lock = threading.Lock()
        self.n = 0
        self.level = 100           # fader EFEITOS (0..200)
        self.muted = False
        threading.Thread(target=self._loop, daemon=True).start()

    def effective(self, volume):
        """Volume final 0..200 (volume do botao x fader EFEITOS)."""
        if self.muted:
            return 0
        try:
            v = max(0, min(MAX_EFFECT, int(volume)))
        except (TypeError, ValueError):
            v = 100
        return int(min(MAX_EFFECT, v * self.level / 100))

    def set_level(self, level=None, muted=None):
        if level is not None:
            self.level = max(0, min(MAX_EFFECT, int(level)))
        if muted is not None:
            self.muted = bool(muted)
        self.q.put(("vol",))

    # ------------------------------------------------------- faixas ---
    def play(self, path, volume=100, exclusive=False, key=None, fade_in=0):
        now = time.time()
        track = {"key": key, "file": os.path.basename(path), "start": now, "dur": None,
                 "end": None, "done": False}
        if not IS_WINDOWS:
            track["dur"] = _sim_duration(path)
        else:
            track["dur"] = quick_duration(path)
        with self.tracks_lock:
            if exclusive:
                for t in self.tracks:
                    t["done"] = True
            # poda as faixas encerradas (lista limitada mesmo sem /api/state)
            self.tracks = [t for t in self.tracks if _track_alive(t, now)]
            self.tracks.append(track)
        self.q.put(("play", path, volume, exclusive, track, _ms(fade_in)))

    def stop_all(self, fade=0):
        fade = _ms(fade)
        if not IS_WINDOWS:
            fade = 0               # simulado: so a contabilidade, sem esperar
        end = time.time() + fade / 1000.0
        with self.tracks_lock:
            for t in self.tracks:
                if fade:
                    t["end"] = min(t["end"] or end, end)
                else:
                    t["done"] = True
        self.q.put(("stop", fade))

    def sounds(self):
        """[{key, file, pos, dur}] dos sons tocando agora (segundos)."""
        now = time.time()
        out = []
        with self.tracks_lock:
            keep = []
            for t in self.tracks:
                pos = now - t["start"]
                dur = t["dur"]
                if not _track_alive(t, now):
                    continue
                keep.append(t)
                out.append({"key": t["key"], "file": t["file"], "pos": round(min(pos, dur or pos), 2),
                            "dur": None if dur is None else round(dur, 2)})
            self.tracks = keep
        return out

    def _finish(self, track):
        if track is not None:
            track["done"] = True

    # ---------------------------------------------------------- MCI ---
    def _stop_pcm(self, fade=0):
        with self.pcm_lock:
            for snd in list(self.pcm):
                if fade:
                    snd.fade_out(fade)
                else:
                    snd.stop()
            if not fade:
                self.pcm = []

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

    def _mci_vol(self, alias, volume, factor=1.0):
        try:
            self._mci("setaudio %s volume to %d" % (alias, int(min(100, self.effective(volume)) * 10 * factor)))
        except Exception:
            pass

    def _ramp(self, steps_ms, make):
        """Thread que enfileira FADE_STEPS comandos make(i) espacados."""
        def run():
            for i in range(1, FADE_STEPS + 1):
                time.sleep(steps_ms / 1000.0 / FADE_STEPS)
                self.q.put(make(i))
        threading.Thread(target=run, daemon=True).start()

    def _mci_play(self, path, volume, track=None, fade_in=0):
        self.n += 1
        alias = "sd%d" % self.n
        try:
            self._mci('open "%s" type mpegvideo alias %s' % (path, alias))
            try:
                self._mci("set %s time format milliseconds" % alias)
                ms = int(self._mci("status %s length" % alias) or 0)
                if ms > 0 and track is not None:
                    track["dur"] = ms / 1000.0
            except Exception:
                pass
            self._mci_vol(alias, volume, 0.0 if fade_in else 1.0)
            self._mci("play " + alias)
            if track is not None:
                track["start"] = time.time()
            self.playing.append([alias, volume, track, 0.0 if fade_in else 1.0, False])
            if fade_in:
                self._ramp(fade_in, lambda i: ("setvol", alias, volume, i / float(FADE_STEPS)))
        except Exception as e:
            print("  erro ao tocar %s: %s" % (path, e))
            self._close(alias)
            self._finish(track)

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
                            self._finish(entry[2])
                    except Exception:
                        self.playing.remove(entry)
                        self._finish(entry[2])
            with self.pcm_lock:
                for x in self.pcm:
                    if not x.alive():
                        self._finish(x.track)
                self.pcm = [x for x in self.pcm if x.alive()]
            if item is None:
                continue
            try:
                self._handle(item)
            except Exception as e:
                print("  erro no som:", e)

    def _handle(self, item):
        if item[0] == "vol":           # fader mexeu: ajusta o que ja esta tocando
            if IS_WINDOWS:             # mantem o fator de fade de cada som
                for e in self.playing:
                    self._mci_vol(e[0], e[1], e[3])
            return                     # os sons PCM leem o ganho a cada bloco
        if item[0] == "setvol":        # degrau de entrada suave
            for e in self.playing:
                if e[0] == item[1] and not e[4]:   # saindo: a saida manda
                    e[3] = item[3]
                    if IS_WINDOWS:
                        self._mci_vol(e[0], e[1], e[3])
            return
        if item[0] == "scale":         # degrau de saida suave (so os do retrato)
            for e in self.playing:
                if e[0] in item[1]:
                    e[3] = min(e[3], item[2])
                    if IS_WINDOWS:
                        self._mci_vol(e[0], e[1], e[3])
            return
        if item[0] == "stopset":       # fim da saida suave: para so os do retrato
            keep = []
            for e in self.playing:
                if e[0] in item[1]:
                    if IS_WINDOWS:
                        self._close(e[0])
                    self._finish(e[2])
                else:
                    keep.append(e)
            self.playing = keep
            return
        if item[0] == "mci":           # PCM falhou: toca pelo MCI a ate 100%
            self._mci_play(item[1], item[2], item[3], item[4])
            return
        if item[0] == "stop" and item[1] and IS_WINDOWS:
            # saida suave: PCM abaixa sozinho; MCI em degraus e depois para
            # retrato dos sons atuais: os que comecarem durante a saida seguem
            self._stop_pcm(item[1])
            snap = frozenset(e[0] for e in self.playing)
            for e in self.playing:
                e[4] = True
            if snap:
                self._ramp(item[1], lambda i: ("scale", snap, 1.0 - i / float(FADE_STEPS))
                           if i < FADE_STEPS else ("stopset", snap))
            return
        if item[0] == "stop" or (item[0] == "play" and item[3]):
            for e in self.playing:
                alias, t = e[0], e[2]
                if IS_WINDOWS:
                    self._close(alias)
                self._finish(t)
            self.playing = []
            self._stop_pcm()
            if item[0] == "stop":
                print("  sons parados")
                return
        _, path, volume, _excl, track, fade_in = item
        eff = self.effective(volume)
        if not IS_WINDOWS:
            print("  [simulado] tocar:", path, "vol", eff, "(amplificado)" if eff > 100 else "")
            return
        if eff > 100 or fade_in:
            snd = PcmSound(self, path, volume, track, fade_in)
            with self.pcm_lock:
                self.pcm.append(snd)
            snd.start()
        else:
            self._mci_play(path, volume, track)


def _track_alive(t, now):
    """Faixa ainda tocando (nao encerrada, nem expirada pelo fim ou duracao)."""
    dur = t["dur"]
    if t["done"] or (t["end"] and now >= t["end"]):
        return False
    return dur is None or now - t["start"] <= dur + 0.3


# --------------------------------------------- PCM: decodificar e tocar ---
MAX_PCM_BYTES = 60 * 1024 * 1024     # ~6 min de estereo 44,1 kHz; mais que isso vai pelo MCI
_PCM_CACHE = {}                       # caminho -> (mtime, tamanho, (canais, taxa, bytes))
_PCM_CACHE_LOCK = threading.Lock()
_PCM_CACHE_MAX = 80 * 1024 * 1024


def apply_gain(data, gain):
    """Ganho em PCM 16 bits little-endian, com corte em +-32767 (sem audioop)."""
    a = array("h")
    a.frombytes(data[:len(data) - (len(data) % 2)])
    if abs(gain - 1.0) > 0.001:
        g = int(gain * 4096)
        a = array("h", [-32768 if v < -32768 else (32767 if v > 32767 else v)
                        for v in [(x * g) >> 12 for x in a]])
    return a.tobytes()


def _decode_wav(path):
    import wave
    with wave.open(path, "rb") as w:
        ch, rate, width, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        if width not in (1, 2):
            raise ValueError("WAV de %d bits" % (width * 8))
        if n * ch * 2 > MAX_PCM_BYTES:
            raise ValueError("som longo demais para amplificar")
        data = w.readframes(n)
    if width == 1:   # 8 bits sem sinal -> 16 bits
        data = array("h", [(b - 128) << 8 for b in bytearray(data)]).tobytes()
    return ch, rate, data


def _decode_mf(path):
    """MP3/WMA/M4A (e WAV) -> PCM 16 bits pelo Media Foundation (COM via ctypes)."""
    import ctypes
    import uuid
    from ctypes import POINTER, byref, c_void_p, c_ulong, c_ulonglong, c_longlong, HRESULT, WINFUNCTYPE

    class GUID(ctypes.Structure):
        _fields_ = [("b", ctypes.c_ubyte * 16)]

    def guid(text):
        g = GUID()
        ctypes.memmove(byref(g), uuid.UUID(text).bytes_le, 16)
        return g

    def call(obj, index, argtypes, *args):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        fn = WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[index])
        return fn(obj, *args)

    def release(obj):
        if obj and obj.value:
            call(obj, 2, ())

    MT_MAJOR = guid("48eba18e-f8c9-4687-bf11-0a74c9f96a8f")
    MT_SUBTYPE = guid("f7e34c9a-42e8-4714-b74b-cb29d72c35e5")
    AUDIO = guid("73647561-0000-0010-8000-00aa00389b71")
    PCM = guid("00000001-0000-0010-8000-00aa00389b71")
    BITS = guid("f2deb57f-40fa-4764-aa33-ed4f2d1ff669")
    CHANNELS = guid("37e48bf5-645e-4c5b-89de-ada9e29b696a")
    RATE = guid("5faeeae7-0290-4c31-9e8a-c534f68d9dba")
    FIRST_AUDIO, ALL_STREAMS = 0xFFFFFFFD, 0xFFFFFFFE
    PG = POINTER(GUID)

    ctypes.windll.ole32.CoInitializeEx(None, 0)
    mf = ctypes.windll.mfplat
    mfr = ctypes.windll.mfreadwrite
    mf.MFStartup.argtypes = [c_ulong, c_ulong]
    hr = mf.MFStartup(0x00020070, 0)
    if hr != 0:
        raise OSError("MFStartup falhou (%x)" % (hr & 0xFFFFFFFF))
    reader, mt, cur = c_void_p(), c_void_p(), c_void_p()
    try:
        mfr.MFCreateSourceReaderFromURL.argtypes = [ctypes.c_wchar_p, c_void_p, POINTER(c_void_p)]
        hr = mfr.MFCreateSourceReaderFromURL(path, None, byref(reader))
        if hr != 0 or not reader.value:
            raise OSError("nao abriu o arquivo (%x)" % (hr & 0xFFFFFFFF))
        mf.MFCreateMediaType.argtypes = [POINTER(c_void_p)]
        if mf.MFCreateMediaType(byref(mt)) != 0:
            raise OSError("MFCreateMediaType falhou")
        call(mt, 24, (PG, PG), byref(MT_MAJOR), byref(AUDIO))          # SetGUID
        call(mt, 24, (PG, PG), byref(MT_SUBTYPE), byref(PCM))
        call(mt, 21, (PG, ctypes.c_uint32), byref(BITS), 16)            # SetUINT32
        call(reader, 4, (c_ulong, ctypes.c_int), ALL_STREAMS, 0)        # SetStreamSelection
        call(reader, 4, (c_ulong, ctypes.c_int), FIRST_AUDIO, 1)
        hr = call(reader, 7, (c_ulong, c_void_p, c_void_p), FIRST_AUDIO, None, mt)  # SetCurrentMediaType
        if hr != 0:
            raise OSError("formato PCM recusado (%x)" % (hr & 0xFFFFFFFF))
        call(reader, 6, (c_ulong, POINTER(c_void_p)), FIRST_AUDIO, byref(cur))     # GetCurrentMediaType
        ch, rate = ctypes.c_uint32(), ctypes.c_uint32()
        call(cur, 7, (PG, POINTER(ctypes.c_uint32)), byref(CHANNELS), byref(ch))     # GetUINT32
        call(cur, 7, (PG, POINTER(ctypes.c_uint32)), byref(RATE), byref(rate))
        if not ch.value or not rate.value:
            raise OSError("formato de audio desconhecido")
        chunks, total = [], 0
        while True:
            idx, flags, ts, sample = c_ulong(), c_ulong(), c_longlong(), c_void_p()
            hr = call(reader, 9, (c_ulong, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                                  POINTER(c_longlong), POINTER(c_void_p)),
                      FIRST_AUDIO, 0, byref(idx), byref(flags), byref(ts), byref(sample))
            if hr != 0:
                raise OSError("ReadSample falhou (%x)" % (hr & 0xFFFFFFFF))
            if sample.value:
                buf = c_void_p()
                try:
                    call(sample, 41, (POINTER(c_void_p),), byref(buf))      # ConvertToContiguousBuffer
                    ptr, maxlen, curlen = c_void_p(), c_ulong(), c_ulong()
                    if call(buf, 3, (POINTER(c_void_p), POINTER(c_ulong), POINTER(c_ulong)),
                            byref(ptr), byref(maxlen), byref(curlen)) == 0:         # Lock
                        try:
                            chunks.append(ctypes.string_at(ptr.value, curlen.value))
                            total += curlen.value
                        finally:
                            call(buf, 4, ())                                     # Unlock
                finally:
                    release(buf)
                    release(sample)
                if total > MAX_PCM_BYTES:
                    raise ValueError("som longo demais para amplificar")
            if flags.value & 0x2:      # MF_SOURCE_READERF_ENDOFSTREAM
                break
        return ch.value, rate.value, b"".join(chunks)
    finally:
        release(cur)
        release(mt)
        release(reader)
        mf.MFShutdown()


def decode_pcm(path):
    """(canais, taxa, bytes PCM 16 bits). Guarda os ultimos em memoria."""
    try:
        st = os.stat(path)
    except OSError:
        raise ValueError("arquivo nao encontrado")
    with _PCM_CACHE_LOCK:
        hit = _PCM_CACHE.get(path)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
    out = None
    if path.lower().endswith(".wav"):
        try:
            out = _decode_wav(path)
        except Exception:
            out = None
    if out is None:
        out = _decode_mf(path)
    with _PCM_CACHE_LOCK:
        _PCM_CACHE[path] = (st.st_mtime_ns, st.st_size, out)
        while sum(len(v[2][2]) for v in _PCM_CACHE.values()) > _PCM_CACHE_MAX and len(_PCM_CACHE) > 1:
            _PCM_CACHE.pop(next(iter(_PCM_CACHE)))
    return out


class PcmSound(object):
    """Um som tocando pelo waveOut, em blocos de ~100 ms com o ganho atual."""
    BLOCKS = 4

    def __init__(self, player, path, volume, track=None, fade_in=0):
        self.player, self.path, self.volume = player, path, volume
        self.track, self.fade_in = track, fade_in
        self.fade_at, self.fade_ms = None, 0      # saida suave em andamento
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def fade_out(self, ms):
        if self.fade_at is None:
            self.fade_at, self.fade_ms = time.time(), max(1, ms)

    def gain(self, pos_s):
        """Ganho atual (0..2) com entrada e saida suaves."""
        g = self.player.effective(self.volume) / 100.0
        if self.fade_in:
            g *= min(1.0, pos_s * 1000.0 / self.fade_in)
        if self.fade_at is not None:
            left = 1.0 - (time.time() - self.fade_at) * 1000.0 / self.fade_ms
            if left <= 0:
                self._stop.set()
                return 0.0
            g *= left
        return g

    def alive(self):
        return self._thread.is_alive() or not self._thread.ident

    def _run(self):
        try:
            ch, rate, data = decode_pcm(self.path)
        except Exception as e:
            print("  aviso: sem amplificar %s (%s); tocando a 100%%" % (os.path.basename(self.path), e))
            if not self._stop.is_set():
                self.player.q.put(("mci", self.path, min(100, self.volume), self.track, self.fade_in))
            return
        if self.track is not None:
            self.track["dur"] = len(data) / float(max(1, ch * 2 * rate))
            self.track["start"] = time.time()
        try:
            self._play(ch, rate, data)
        except Exception as e:
            print("  erro ao tocar %s: %s" % (self.path, e))

    def _play(self, ch, rate, data):
        import ctypes
        from ctypes import wintypes, POINTER, byref

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                        ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                        ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                        ("cbSize", wintypes.WORD)]

        class WAVEHDR(ctypes.Structure):
            pass
        WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                            ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                            ("dwFlags", wintypes.DWORD), ("dwLoops", wintypes.DWORD),
                            ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]

        winmm = ctypes.WinDLL("winmm")
        winmm.waveOutOpen.argtypes = [POINTER(ctypes.c_void_p), ctypes.c_uint, POINTER(WAVEFORMATEX),
                                      ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
        for name in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
            getattr(winmm, name).argtypes = [ctypes.c_void_p, POINTER(WAVEHDR), ctypes.c_uint]
        winmm.waveOutReset.argtypes = [ctypes.c_void_p]
        winmm.waveOutClose.argtypes = [ctypes.c_void_p]

        align = ch * 2
        fmt = WAVEFORMATEX(1, ch, rate, rate * align, align, 16, 0)
        h = ctypes.c_void_p()
        err = winmm.waveOutOpen(byref(h), 0xFFFFFFFF, byref(fmt), 0, 0, 0)   # WAVE_MAPPER, CALLBACK_NULL
        if err:
            raise OSError("waveOutOpen falhou (%d)" % err)
        WHDR_DONE, size = 0x1, ctypes.sizeof(WAVEHDR)
        block = max(align, (rate // 10) * align)
        hdrs = [WAVEHDR() for _ in range(self.BLOCKS)]
        bufs = [None] * self.BLOCKS
        busy = [False] * self.BLOCKS
        pos = 0
        try:
            while not self._stop.is_set():
                for i in range(self.BLOCKS):
                    if busy[i] and hdrs[i].dwFlags & WHDR_DONE:
                        winmm.waveOutUnprepareHeader(h, byref(hdrs[i]), size)
                        busy[i] = False
                    if not busy[i] and pos < len(data):
                        gain = self.gain(pos / float(align * rate))
                        chunk = apply_gain(data[pos:pos + block], gain)
                        pos += block
                        bufs[i] = ctypes.create_string_buffer(chunk, len(chunk))
                        hdrs[i] = WAVEHDR()
                        hdrs[i].lpData = ctypes.cast(bufs[i], ctypes.c_void_p)
                        hdrs[i].dwBufferLength = len(chunk)
                        if winmm.waveOutPrepareHeader(h, byref(hdrs[i]), size) == 0:
                            winmm.waveOutWrite(h, byref(hdrs[i]), size)
                            busy[i] = True
                if pos >= len(data) and not any(busy):
                    break
                time.sleep(0.01)
        finally:
            winmm.waveOutReset(h)   # marca tudo como pronto (para na hora no stop)
            for i in range(self.BLOCKS):
                if busy[i]:
                    for _ in range(50):
                        if hdrs[i].dwFlags & WHDR_DONE:
                            break
                        time.sleep(0.01)
                    winmm.waveOutUnprepareHeader(h, byref(hdrs[i]), size)
            winmm.waveOutClose(h)


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
    out = {"effects": {"v": PLAYER.level, "muted": PLAYER.muted, "max": MAX_LEVEL["effects"]}}
    for name, flow in VOL_TARGETS.items():
        try:
            v, m = win_volume(flow)
        except Exception:
            v, m = None, False
        out[name] = {"v": v, "muted": m, "max": MAX_LEVEL[name]}
    return out


def set_level(target, value=None, toggle_mute=False):
    if value is not None and target in MAX_LEVEL:
        value = max(0, min(MAX_LEVEL[target], int(value)))
    if target == "effects":
        PLAYER.set_level(value, (not PLAYER.muted) if toggle_mute else None)
    elif target in VOL_TARGETS:
        win_volume(VOL_TARGETS[target], value, toggle_mute)
    else:
        raise ValueError("controle desconhecido: %s" % target)
