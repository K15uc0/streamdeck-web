# -*- coding: utf-8 -*-
"""Monitor do PC: CPU (total e por nucleo), memoria, GPU, disco, rede, tempo ligado
e bateria. Sem dependencias: no Windows usa ctypes (NtQuerySystemInformation,
GlobalMemoryStatusEx, PDH, GetSystemPowerStatus); no Linux le /proc (para rodar
pelo codigo e nos testes). Cada fonte falha sozinha: o que nao der para ler vem None.

Uma thread amostra a cada INTERVAL s, mas so enquanto alguem olha (touch() pelo
/api/sys ou /api/state?sys=1 no ultimo ACTIVE_FOR s). Historico curto para os graficos.
Temperatura nao e lida: o Windows so a entrega com driver/administrador."""
import os
import shutil
import sys
import threading
import time
from collections import deque

IS_WINDOWS = sys.platform.startswith("win")
INTERVAL = 1.0
ACTIVE_FOR = 30.0
HIST = 90            # amostras guardadas (~1,5 min)
DISK_EVERY = 30.0    # espaco em disco muda devagar
HIST_KEYS = ("cpu", "ram", "gpu", "rx", "tx", "dr", "dw")


# ----------------------------------------------------------- funcoes puras ---
def cpu_percent(prev, cur):
    """prev/cur: [(ocupado, total)] por nucleo (contadores acumulados).
    Devolve (total %, [% por nucleo]) ou (None, []) sem amostra anterior."""
    if not prev or not cur or len(prev) != len(cur):
        return None, []
    cores, sb, st = [], 0, 0
    for (b0, t0), (b1, t1) in zip(prev, cur):
        db, dt = b1 - b0, t1 - t0
        sb += max(0, db)
        st += max(0, dt)
        cores.append(_pct(db, dt))
    return _pct(sb, st), cores


def _pct(part, whole):
    if whole <= 0:
        return 0.0
    return round(min(100.0, max(0.0, 100.0 * part / whole)), 1)


def rate(prev, cur, dt):
    """Bytes/s entre dois contadores acumulados (None se faltar algo ou o contador voltou)."""
    if prev is None or cur is None or dt <= 0 or cur < prev:
        return None
    return (cur - prev) / dt


def gpu_from_engines(items):
    """items: [(instancia, %)] de "\\GPU Engine(*)\\Utilization Percentage".
    Como o Gerenciador de Tarefas: soma os processos de cada motor
    (luid_..._phys_N_eng_M) e fica com o motor mais ocupado."""
    per = {}
    for name, v in items:
        if v is None:
            continue
        key = name
        i = name.find("luid_")
        if i >= 0:
            key = name[i:]
            j = key.find("_engtype_")
            if j >= 0:
                key = key[:j]
        per[key] = per.get(key, 0.0) + float(v)
    if not per:
        return None
    return round(min(100.0, max(per.values())), 1)


def human_bytes(n):
    """Texto curto: 512 B, 1,2 KB, 34 MB, 1,5 GB (virgula decimal)."""
    if n is None:
        return "--"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return "%d B" % int(n)
            s = ("%.1f" % n) if abs(n) < 10 else ("%d" % round(n))
            return "%s %s" % (s.replace(".", ","), unit)
        n /= 1024.0
    return "--"


# ------------------------------------------------------------------ Linux ---
class _Linux(object):
    def __init__(self):
        self.cpu_name = None
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        self.cpu_name = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass

    def cpu_times(self):
        out = []
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu") and line[3:4].isdigit():
                    v = [int(x) for x in line.split()[1:]]
                    idle = v[3] + (v[4] if len(v) > 4 else 0)
                    total = sum(v[:8])
                    out.append((total - idle, total))
        return out

    def memory(self):
        info = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                k, _, rest = line.partition(":")
                info[k] = int(rest.split()[0]) * 1024
        total = info.get("MemTotal")
        avail = info.get("MemAvailable", info.get("MemFree"))
        if not total or avail is None:
            return None
        return total, total - avail

    def counters(self):
        """{rx, tx, dr, dw} acumulados (bytes)."""
        out = {"rx": None, "tx": None, "dr": None, "dw": None}
        try:
            rx = tx = 0
            with open("/proc/net/dev", "r") as f:
                for line in f.readlines()[2:]:
                    name, _, rest = line.partition(":")
                    if name.strip() == "lo":
                        continue
                    v = rest.split()
                    rx += int(v[0])
                    tx += int(v[8])
            out["rx"], out["tx"] = rx, tx
        except (OSError, ValueError, IndexError):
            pass
        try:
            disks = set(d for d in os.listdir("/sys/block") if not d.startswith(("loop", "ram", "zram", "dm-")))
            dr = dw = 0
            with open("/proc/diskstats", "r") as f:
                for line in f:
                    v = line.split()
                    if len(v) > 9 and v[2] in disks:
                        dr += int(v[5]) * 512
                        dw += int(v[9]) * 512
            out["dr"], out["dw"] = dr, dw
        except (OSError, ValueError):
            pass
        return out

    def rates(self):
        return {}

    def gpu(self):
        return None

    def disks(self):
        try:
            u = shutil.disk_usage("/")
            return [{"name": "/", "total": u.total, "used": u.total - u.free}]
        except OSError:
            return []

    def uptime(self):
        with open("/proc/uptime", "r") as f:
            return int(float(f.read().split()[0]))

    def battery(self):
        base = "/sys/class/power_supply"
        try:
            for d in sorted(os.listdir(base)):
                if d.startswith("BAT"):
                    with open(os.path.join(base, d, "capacity")) as f:
                        pct = int(f.read().strip())
                    with open(os.path.join(base, d, "status")) as f:
                        st = f.read().strip()
                    return {"pct": pct, "charging": st in ("Charging", "Full")}
        except (OSError, ValueError):
            pass
        return None


# ---------------------------------------------------------------- Windows ---
class _Windows(object):
    PDH_FMT_DOUBLE = 0x00000200
    PDH_FMT_NOCAP100 = 0x00008000
    PDH_MORE_DATA = 0x800007D2

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.k32 = ctypes.WinDLL("kernel32")
        self.k32.GetTickCount64.restype = ctypes.c_ulonglong
        self.nt = ctypes.WinDLL("ntdll")
        self.ncpu = os.cpu_count() or 1

        class SPPI(ctypes.Structure):   # SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION
            _fields_ = [("Idle", ctypes.c_longlong), ("Kernel", ctypes.c_longlong),
                        ("User", ctypes.c_longlong), ("Dpc", ctypes.c_longlong),
                        ("Interrupt", ctypes.c_longlong), ("Count", ctypes.c_ulong)]
        self.SPPI = SPPI

        class MEM(ctypes.Structure):    # MEMORYSTATUSEX
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        self.MEM = MEM

        class PWR(ctypes.Structure):    # SYSTEM_POWER_STATUS
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]
        self.PWR = PWR

        self.cpu_name = self._reg_str(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
        self.gpu_name, self.gpu_total = self._gpu_info()
        self._pdh_init()

    # registro ---------------------------------------------------------------
    @staticmethod
    def _reg_str(path, name):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
                return str(winreg.QueryValueEx(k, name)[0]).strip() or None
        except OSError:
            return None

    @staticmethod
    def _gpu_info():
        """Nome e memoria dedicada da placa de video principal (a de mais memoria)."""
        best = (None, None)
        try:
            import winreg
            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
                for i in range(32):
                    try:
                        sub = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    if not sub.isdigit():
                        continue
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            name = winreg.QueryValueEx(k, "DriverDesc")[0]
                            try:
                                mem = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")[0]
                            except OSError:
                                mem = None
                            if isinstance(mem, bytes):
                                mem = int.from_bytes(mem[:8], "little")
                            if not isinstance(mem, int):
                                mem = None
                            if best[0] is None or (mem or 0) > (best[1] or 0):
                                best = (str(name), mem)
                    except OSError:
                        continue
        except OSError:
            pass
        return best

    # PDH (contadores de desempenho, nomes em ingles funcionam em qualquer idioma)
    def _pdh_init(self):
        ct, wt = self.ct, self.wt
        self.pdh = None
        self.counters_h = {}
        try:
            pdh = ct.WinDLL("pdh")
            pdh.PdhOpenQueryW.argtypes = [wt.LPCWSTR, ct.c_void_p, ct.POINTER(ct.c_void_p)]
            pdh.PdhAddEnglishCounterW.argtypes = [ct.c_void_p, wt.LPCWSTR, ct.c_void_p, ct.POINTER(ct.c_void_p)]
            pdh.PdhCollectQueryData.argtypes = [ct.c_void_p]
            pdh.PdhGetFormattedCounterArrayW.argtypes = [ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD),
                                                         ct.POINTER(wt.DWORD), ct.c_void_p]
            for f in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
                      "PdhGetFormattedCounterArrayW"):
                getattr(pdh, f).restype = wt.DWORD
            q = ct.c_void_p()
            if pdh.PdhOpenQueryW(None, None, ct.byref(q)) != 0:
                return
            paths = {
                "rx": r"\Network Interface(*)\Bytes Received/sec",
                "tx": r"\Network Interface(*)\Bytes Sent/sec",
                "dr": r"\PhysicalDisk(_Total)\Disk Read Bytes/sec",
                "dw": r"\PhysicalDisk(_Total)\Disk Write Bytes/sec",
                "didle": r"\PhysicalDisk(_Total)\% Idle Time",
                "gpu": r"\GPU Engine(*)\Utilization Percentage",
                "vram": r"\GPU Adapter Memory(*)\Dedicated Usage",
            }
            for key, p in paths.items():
                h = ct.c_void_p()
                if pdh.PdhAddEnglishCounterW(q, p, None, ct.byref(h)) == 0:
                    self.counters_h[key] = h
            self.pdh, self.query = pdh, q
            pdh.PdhCollectQueryData(q)

            class VAL(ct.Structure):
                _fields_ = [("CStatus", wt.DWORD), ("doubleValue", ct.c_double)]

            class ITEM(ct.Structure):
                _fields_ = [("szName", ct.c_wchar_p), ("FmtValue", VAL)]
            self.ITEM = ITEM
        except Exception:  # noqa: BLE001 - sem PDH: rede/GPU/disco ficam None
            self.pdh = None

    def _array(self, key):
        """[(instancia, valor)] de um contador (vazio se indisponivel)."""
        h = self.counters_h.get(key)
        if self.pdh is None or h is None:
            return []
        ct, wt = self.ct, self.wt
        size, count = wt.DWORD(0), wt.DWORD(0)
        fmt = self.PDH_FMT_DOUBLE | self.PDH_FMT_NOCAP100
        r = self.pdh.PdhGetFormattedCounterArrayW(h, fmt, ct.byref(size), ct.byref(count), None)
        if r != self.PDH_MORE_DATA or size.value == 0:
            return []
        buf = ct.create_string_buffer(size.value)
        r = self.pdh.PdhGetFormattedCounterArrayW(h, fmt, ct.byref(size), ct.byref(count), buf)
        if r != 0:
            return []
        items = ct.cast(buf, ct.POINTER(self.ITEM))
        out = []
        for i in range(count.value):
            it = items[i]
            if it.FmtValue.CStatus in (0, 1):   # PDH_CSTATUS_VALID_DATA / NEW_DATA
                out.append((it.szName or "", it.FmtValue.doubleValue))
        return out

    def rates(self):
        """Taxas ja calculadas pelo PDH (bytes/s e %), lidas uma vez por amostra."""
        if self.pdh is None:
            return {}
        try:
            self.pdh.PdhCollectQueryData(self.query)
        except Exception:  # noqa: BLE001
            return {}
        out = {}
        for key in ("rx", "tx", "dr", "dw", "didle", "vram"):
            arr = self._array(key)
            if arr:
                vals = [v for n, v in arr if key not in ("rx", "tx") or "isatap" not in n.lower()]
                out[key] = sum(vals)
        g = self._array("gpu")
        if g:
            out["gpu"] = gpu_from_engines(g)
        return out

    # leituras diretas --------------------------------------------------------
    def cpu_times(self):
        ct = self.ct
        n = self.ncpu
        arr = (self.SPPI * n)()
        ret = ct.c_ulong(0)
        st = self.nt.NtQuerySystemInformation(8, ct.byref(arr), ct.sizeof(arr), ct.byref(ret))
        if st != 0:
            return []
        got = ret.value // ct.sizeof(self.SPPI) or n
        out = []
        for i in range(min(n, got)):
            p = arr[i]
            total = p.Kernel + p.User   # Kernel inclui o tempo ocioso
            out.append((total - p.Idle, total))
        return out

    def memory(self):
        m = self.MEM()
        m.dwLength = self.ct.sizeof(self.MEM)
        if not self.k32.GlobalMemoryStatusEx(self.ct.byref(m)):
            return None
        return m.ullTotalPhys, m.ullTotalPhys - m.ullAvailPhys

    def counters(self):
        return {}

    def gpu(self):
        return None   # vem em rates()

    def disks(self):
        out = []
        try:
            mask = self.k32.GetLogicalDrives()
        except Exception:  # noqa: BLE001
            return out
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = "%s:\\" % chr(65 + i)
            try:
                if self.k32.GetDriveTypeW(self.ct.c_wchar_p(root)) != 3:   # DRIVE_FIXED
                    continue
                u = shutil.disk_usage(root)
            except OSError:
                continue
            out.append({"name": root[:2], "total": u.total, "used": u.total - u.free})
        return out

    def uptime(self):
        return int(self.k32.GetTickCount64() // 1000)

    def battery(self):
        p = self.PWR()
        if not self.k32.GetSystemPowerStatus(self.ct.byref(p)):
            return None
        if p.BatteryFlag & 128 or p.BatteryLifePercent == 255:   # sem bateria / desconhecido
            return None
        return {"pct": int(p.BatteryLifePercent), "charging": p.ACLineStatus == 1}


# --------------------------------------------------------------- amostrador ---
class Monitor(object):
    def __init__(self, backend=None):
        self._backend = backend
        self._lock = threading.Lock()
        self._prev_cpu = None
        self._prev_cnt = None
        self._prev_t = None
        self._disks = ([], 0.0)
        self.snap = None
        self.hist = dict((k, deque(maxlen=HIST)) for k in HIST_KEYS)
        self.polled = 0.0
        self._stop = threading.Event()
        self._thread = None

    def backend(self):
        if self._backend is None:
            try:
                self._backend = _Windows() if IS_WINDOWS else _Linux()
            except Exception as e:  # noqa: BLE001
                print("  monitor do PC indisponivel: %s" % e)
                self._backend = _Linux() if not IS_WINDOWS else False
        return self._backend

    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - uma fonte com problema nao derruba as outras
            return default

    def sample(self):
        """Le tudo agora, calcula as taxas e guarda no historico. Devolve o retrato."""
        be = self.backend()
        now = time.time()
        if not be:
            return None
        cpu_t = self._safe(be.cpu_times, [])
        mem = self._safe(be.memory)
        cnt = self._safe(be.counters, {}) or {}
        rates = self._safe(be.rates, {}) or {}
        if now - self._disks[1] > DISK_EVERY:
            self._disks = (self._safe(be.disks, []) or [], now)
        with self._lock:
            total, cores = cpu_percent(self._prev_cpu, cpu_t)
            dt = now - self._prev_t if self._prev_t else 0
            prev = self._prev_cnt or {}
            r = {}
            for k in ("rx", "tx", "dr", "dw"):
                if k in rates:
                    r[k] = rates[k]
                else:
                    r[k] = rate(prev.get(k), cnt.get(k), dt)
            self._prev_cpu, self._prev_cnt, self._prev_t = cpu_t, cnt, now
            ram = None
            if mem:
                ram = {"total": mem[0], "used": mem[1], "pct": _pct(mem[1], mem[0])}
            gpu = None
            if rates.get("gpu") is not None or rates.get("vram") is not None:
                gpu = {"pct": rates.get("gpu"), "mem": rates.get("vram"),
                       "mem_total": getattr(be, "gpu_total", None), "name": getattr(be, "gpu_name", None)}
            disk_busy = None
            if rates.get("didle") is not None:
                disk_busy = round(max(0.0, min(100.0, 100.0 - rates["didle"])), 1)
            disks = []
            for d in self._disks[0]:
                disks.append(dict(d, pct=_pct(d["used"], d["total"])))
            snap = {
                "t": int(now),
                "cpu": {"pct": total, "cores": cores, "name": getattr(be, "cpu_name", None),
                        "count": len(cpu_t)},
                "ram": ram,
                "gpu": gpu,
                "net": {"rx": _round(r["rx"]), "tx": _round(r["tx"])},
                "disk": {"read": _round(r["dr"]), "write": _round(r["dw"]), "busy": disk_busy, "drives": disks},
                "uptime": self._safe(be.uptime),
                "battery": self._safe(be.battery),
            }
            if total is not None:   # a primeira leitura so serve de base
                vals = {"cpu": total, "ram": ram and ram["pct"], "gpu": gpu and gpu["pct"],
                        "rx": snap["net"]["rx"], "tx": snap["net"]["tx"],
                        "dr": snap["disk"]["read"], "dw": snap["disk"]["write"]}
                for k in HIST_KEYS:
                    self.hist[k].append(vals[k])
                self.snap = snap
            return snap

    def touch(self):
        """Alguem esta olhando: garante a thread rodando."""
        self.polled = time.time()
        if not (self._thread and self._thread.is_alive()):
            self.start()

    def full(self):
        """Retrato completo com historico (para a tela Monitor)."""
        with self._lock:
            snap = self.snap
            hist = dict((k, list(v)) for k, v in self.hist.items())
        if snap is None:   # acabou de ligar: duas leituras rapidas para ter as porcentagens
            self.sample()
            time.sleep(0.25)
            snap = self.sample()
            with self._lock:
                hist = dict((k, list(v)) for k, v in self.hist.items())
        out = dict(snap or {})
        out["ok"] = snap is not None
        out["interval"] = INTERVAL
        out["hist"] = hist
        return out

    def compact(self):
        """So os numeros que os botoes com texto ao vivo usam."""
        with self._lock:
            s = self.snap
        if not s:
            return None
        return {"cpu": s["cpu"]["pct"], "ram": s["ram"] and s["ram"]["pct"],
                "gpu": s["gpu"] and s["gpu"]["pct"], "rx": s["net"]["rx"], "tx": s["net"]["tx"],
                "disk": s["disk"]["busy"], "uptime": s["uptime"]}

    def _loop(self):
        while not self._stop.is_set():
            if time.time() - self.polled > ACTIVE_FOR:
                break   # ninguem olhando: para (touch() liga de novo)
            self._safe(self.sample)
            self._stop.wait(INTERVAL)
        self._prev_cpu = None   # proxima vez recomeca a base (evita media de minutos)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(2.0)
        self._thread = None


def _round(v):
    return None if v is None else int(round(v))


MONITOR = Monitor()
