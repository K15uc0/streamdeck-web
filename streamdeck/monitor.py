# -*- coding: utf-8 -*-
"""Monitor do PC (2.9): CPU, memoria, discos, rede, GPU, temperaturas e processos.

No Windows usa so ctypes (GetSystemTimes, GlobalMemoryStatusEx, GetDiskFreeSpaceExW,
GetIfTable2, PDH "GPU Engine", Toolhelp32 + GetProcessTimes + GetProcessMemoryInfo).
Fora do Windows devolve valores simulados e deterministicos (para os testes).
Temperaturas vem do LibreHardwareMonitor (http://127.0.0.1:8085/data.json), se
estiver rodando. So coleta se alguem chamou touch() no ultimo minuto."""
import copy
import json
import os
import re
import threading
import time
import urllib.request

from . import windows

IS_WINDOWS = windows.IS_WINDOWS
INTERVAL = 2.0
ACTIVE_FOR = 60.0     # segundos depois do ultimo touch()
LHM_URL = "http://127.0.0.1:8085/data.json"
LHM_TTL = 5.0

PROTECTED_NAMES = ("csrss.exe", "wininit.exe", "winlogon.exe", "lsass.exe",
                   "services.exe", "smss.exe", "explorer.exe")


# ------------------------------------------------------------ funcoes puras ---
def cpu_pct(prev, cur):
    """prev/cur = (idle, kernel, user) do GetSystemTimes (kernel inclui idle)."""
    di = cur[0] - prev[0]
    total = (cur[1] - prev[1]) + (cur[2] - prev[2])
    if total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (total - di) * 100.0 / total)), 1)


def rate(prev_bytes, cur_bytes, dt):
    """Bytes por segundo entre duas leituras de contador (0 se reiniciou)."""
    if dt <= 0 or cur_bytes < prev_bytes:
        return 0.0
    return float(cur_bytes - prev_bytes) / dt


def _pct(used, total):
    return round(used * 100.0 / total, 1) if total else 0.0


# ------------------------------------------------------- LibreHardwareMonitor ---
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
CPU_TEMP_NAMES = ("cpu package", "core (tctl/tdie)")
GPU_TEMP_NAMES = ("gpu core",)


def _parse_value(text):
    """"54,0 °C" ou "54.0 °C" -> 54.0 (None se nao der)."""
    m = _NUM.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_lhm(raw):
    """JSON do /data.json do LibreHardwareMonitor -> {"cpu": float|None, "gpu": float|None}."""
    out = {"cpu": None, "gpu": None}
    try:
        tree = json.loads(raw)
    except (ValueError, TypeError):
        return out
    cpu_pri = {}

    def walk(node, hw, in_temp):
        if not isinstance(node, dict):
            return
        text = str(node.get("Text") or "")
        kids = node.get("Children") or []
        low = text.lower()
        if in_temp and not kids:
            v = _parse_value(node.get("Value"))
            if v is not None:
                if low in CPU_TEMP_NAMES:
                    # CPU Package ganha de Tctl/Tdie
                    pri = 0 if low == "cpu package" else 1
                    if out["cpu"] is None or pri < cpu_pri.get("p", 9):
                        out["cpu"] = v
                        cpu_pri["p"] = pri
                elif low in GPU_TEMP_NAMES and out["gpu"] is None:
                    out["gpu"] = v
            return
        for k in kids if isinstance(kids, list) else []:
            walk(k, hw, in_temp or low == "temperatures")

    walk(tree, None, False)
    return out


_LHM_CACHE = {}
_LHM_LOCK = threading.Lock()


def lhm_cached(url=None):
    """Ultimo valor conhecido das temperaturas, sem rede (nunca bloqueia)."""
    with _LHM_LOCK:
        c = _LHM_CACHE.get(url or LHM_URL)
        return dict(c[1]) if c else {"cpu": None, "gpu": None}


_OPENER = []


def lhm_temps(url=None, timeout=0.4):
    """Temperaturas do LibreHardwareMonitor; None se nao estiver rodando. Cache de 5 s."""
    url = url or LHM_URL
    now = time.time()
    with _LHM_LOCK:
        c = _LHM_CACHE.get(url)
        if c and now - c[0] < LHM_TTL:
            return dict(c[1])
    try:
        if not _OPENER:    # sem proxy do sistema: e sempre local
            _OPENER.append(urllib.request.build_opener(urllib.request.ProxyHandler({})))
        with _OPENER[0].open(url, timeout=timeout) as r:
            res = parse_lhm(r.read(2_000_000).decode("utf-8", "replace"))
    except Exception:
        res = {"cpu": None, "gpu": None}
    with _LHM_LOCK:
        _LHM_CACHE[url] = (time.time(), res)
    return dict(res)


# ------------------------------------------------------------------ Windows ---
_W = []


def _win():
    """Declara as APIs uma vez (como em windows.py)."""
    if _W:
        return _W[0]
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    iph = ctypes.WinDLL("iphlpapi", use_last_error=True)
    pdh = ctypes.WinDLL("pdh", use_last_error=True)

    class FILETIME(ctypes.Structure):
        _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

    class MEMSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64)]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD),
                    ("d4", ctypes.c_ubyte * 8)]

    class IFROW2(ctypes.Structure):   # MIB_IF_ROW2
        _fields_ = [("InterfaceLuid", ctypes.c_uint64), ("InterfaceIndex", wintypes.ULONG),
                    ("InterfaceGuid", GUID), ("Alias", ctypes.c_wchar * 257),
                    ("Description", ctypes.c_wchar * 257), ("PhysicalAddressLength", wintypes.ULONG),
                    ("PhysicalAddress", ctypes.c_ubyte * 32), ("PermanentPhysicalAddress", ctypes.c_ubyte * 32),
                    ("Mtu", wintypes.ULONG), ("Type", wintypes.ULONG), ("TunnelType", wintypes.ULONG),
                    ("MediaType", wintypes.ULONG), ("PhysicalMediumType", wintypes.ULONG),
                    ("AccessType", wintypes.ULONG), ("DirectionType", wintypes.ULONG),
                    ("InterfaceAndOperStatusFlags", ctypes.c_ubyte), ("OperStatus", wintypes.ULONG),
                    ("AdminStatus", wintypes.ULONG), ("MediaConnectState", wintypes.ULONG),
                    ("NetworkGuid", GUID), ("ConnectionType", wintypes.ULONG),
                    ("TransmitLinkSpeed", ctypes.c_uint64), ("ReceiveLinkSpeed", ctypes.c_uint64),
                    ("InOctets", ctypes.c_uint64), ("InUcastPkts", ctypes.c_uint64),
                    ("InNUcastPkts", ctypes.c_uint64), ("InDiscards", ctypes.c_uint64),
                    ("InErrors", ctypes.c_uint64), ("InUnknownProtos", ctypes.c_uint64),
                    ("InUcastOctets", ctypes.c_uint64), ("InMulticastOctets", ctypes.c_uint64),
                    ("InBroadcastOctets", ctypes.c_uint64), ("OutOctets", ctypes.c_uint64),
                    ("OutUcastPkts", ctypes.c_uint64), ("OutNUcastPkts", ctypes.c_uint64),
                    ("OutDiscards", ctypes.c_uint64), ("OutErrors", ctypes.c_uint64),
                    ("OutUcastOctets", ctypes.c_uint64), ("OutMulticastOctets", ctypes.c_uint64),
                    ("OutBroadcastOctets", ctypes.c_uint64), ("OutQLen", ctypes.c_uint64)]

    class PDH_ITEM(ctypes.Structure):   # PDH_FMT_COUNTERVALUE_ITEM_W (double)
        _fields_ = [("szName", wintypes.LPWSTR), ("CStatus", wintypes.DWORD), ("value", ctypes.c_double)]

    k32.GetSystemTimes.argtypes = [ctypes.POINTER(FILETIME)] * 3
    k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMSTATUSEX)]
    k32.GetDiskFreeSpaceExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_uint64),
                                        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64)]
    k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FILETIME)] * 4
    k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    iph.GetIfTable2.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    iph.GetIfTable2.restype = wintypes.ULONG
    iph.FreeMibTable.argtypes = [ctypes.c_void_p]
    pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
    pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_size_t,
                                          ctypes.POINTER(ctypes.c_void_p)]
    pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
    pdh.PdhGetFormattedCounterArrayW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                 ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _W.append(dict(ctypes=ctypes, wintypes=wintypes, k32=k32, iph=iph, pdh=pdh, FILETIME=FILETIME,
                   MEMSTATUSEX=MEMSTATUSEX, PROCESSENTRY32W=PROCESSENTRY32W, PMC=PMC, IFROW2=IFROW2,
                   PDH_ITEM=PDH_ITEM))
    return _W[0]


def _ft(f):
    return (f.hi << 32) | f.lo


def _win_cpu_times():
    w = _win()
    i, k, u = w["FILETIME"](), w["FILETIME"](), w["FILETIME"]()
    w["k32"].GetSystemTimes(w["ctypes"].byref(i), w["ctypes"].byref(k), w["ctypes"].byref(u))
    return (_ft(i), _ft(k), _ft(u))


def _win_mem():
    w = _win()
    m = w["MEMSTATUSEX"]()
    m.dwLength = w["ctypes"].sizeof(m)
    w["k32"].GlobalMemoryStatusEx(w["ctypes"].byref(m))
    total = int(m.ullTotalPhys)
    used = total - int(m.ullAvailPhys)
    return {"used": used, "total": total, "pct": _pct(used, total)}


def _win_disks():
    w = _win()
    ct = w["ctypes"]
    out = []
    mask = w["k32"].GetLogicalDrives()
    for i in range(26):
        if not mask & (1 << i):
            continue
        root = "%s:\\" % chr(65 + i)
        if w["k32"].GetDriveTypeW(root) != 3:    # so discos fixos
            continue
        free, total, _f = ct.c_uint64(), ct.c_uint64(), ct.c_uint64()
        if w["k32"].GetDiskFreeSpaceExW(root, ct.byref(free), ct.byref(total), ct.byref(_f)) and total.value:
            used = total.value - free.value
            out.append({"drive": "%s:" % chr(65 + i), "used": int(used), "total": int(total.value),
                        "pct": _pct(used, total.value)})
    return out


def _win_net_bytes():
    """(bytes recebidos, bytes enviados) somando interfaces ativas (sem loopback/tunel)."""
    w = _win()
    ct = w["ctypes"]
    ptr = ct.c_void_p()
    if w["iph"].GetIfTable2(ct.byref(ptr)) != 0 or not ptr.value:
        return (0, 0)
    try:
        n = ct.c_ulong.from_address(ptr.value).value
        size = ct.sizeof(w["IFROW2"])
        base = ptr.value + 8       # NumEntries + alinhamento; linhas tem ULONG64
        hw = [0, 0, 0]       # interfaces fisicas (flag HardwareInterface)
        anyif = [0, 0, 0]    # reserva: qualquer ativa que nao seja loopback/tunel
        for i in range(n):
            row = w["IFROW2"].from_address(base + i * size)
            if row.OperStatus != 1 or row.Type in (24, 131):   # up; nao loopback/tunel
                continue
            anyif[0] += row.InOctets
            anyif[1] += row.OutOctets
            anyif[2] += 1
            if row.InterfaceAndOperStatusFlags & 1:
                hw[0] += row.InOctets
                hw[1] += row.OutOctets
                hw[2] += 1
        best = hw if hw[2] else anyif
        return (best[0], best[1])
    finally:
        w["iph"].FreeMibTable(ptr)


_GPU = {"q": None, "c": None, "failed": False}


def _win_gpu():
    """Soma "GPU Engine(*)\\Utilization Percentage" (limitado a 100); None se indisponivel."""
    if _GPU["failed"]:
        return None
    w = _win()
    ct, pdh = w["ctypes"], w["pdh"]
    try:
        if _GPU["q"] is None:
            q, c = ct.c_void_p(), ct.c_void_p()
            if pdh.PdhOpenQueryW(None, 0, ct.byref(q)) != 0 or pdh.PdhAddEnglishCounterW(
                    q, "\\GPU Engine(*)\\Utilization Percentage", 0, ct.byref(c)) != 0:
                _GPU["failed"] = True
                return None
            _GPU["q"], _GPU["c"] = q, c
            pdh.PdhCollectQueryData(q)
            return None            # precisa de duas coletas
        if pdh.PdhCollectQueryData(_GPU["q"]) != 0:
            return None
        size, count = w["wintypes"].DWORD(0), w["wintypes"].DWORD(0)
        pdh.PdhGetFormattedCounterArrayW(_GPU["c"], 0x200, ct.byref(size), ct.byref(count), None)
        if not size.value:
            return None
        buf = ct.create_string_buffer(size.value)
        if pdh.PdhGetFormattedCounterArrayW(_GPU["c"], 0x200, ct.byref(size), ct.byref(count), buf) != 0:
            return None
        items = (w["PDH_ITEM"] * count.value).from_buffer(buf)
        tot = sum(it.value for it in items
                  if it.CStatus in (0, 1) and "engtype_3d" in (it.szName or "").lower())
        return round(max(0.0, min(100.0, tot)), 1)
    except Exception:
        _GPU["failed"] = True
        return None


# ----------------------------------------------------------------- processos ---
_PROC_PREV = {}     # pid -> (cpu_100ns, wall)
_PROC_T = [0.0]     # quando a baseline foi gravada
_PROC_LOCK = threading.Lock()
PROC_MIN_GAP = 1.0


def _win_processes(update_baseline=True):
    with _PROC_LOCK:
        return _win_processes_locked(update_baseline)


def _win_processes_locked(update_baseline):
    w = _win()
    ct = w["ctypes"]
    k32 = w["k32"]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    if not snap or snap == ct.c_void_p(-1).value:
        return []
    out = []
    now = time.time()
    ncpu = os.cpu_count() or 1
    seen = {}
    try:
        e = w["PROCESSENTRY32W"]()
        e.dwSize = ct.sizeof(e)
        ok = k32.Process32FirstW(snap, ct.byref(e))
        while ok:
            pid, name = int(e.th32ProcessID), e.szExeFile
            cpu, mem = 0.0, 0
            h = k32.OpenProcess(0x1000, False, pid) if pid else None   # QUERY_LIMITED_INFORMATION
            if h:
                try:
                    c, x, kt, ut = (w["FILETIME"]() for _ in range(4))
                    if k32.GetProcessTimes(h, ct.byref(c), ct.byref(x), ct.byref(kt), ct.byref(ut)):
                        t = _ft(kt) + _ft(ut)
                        seen[pid] = (t, now)
                        p = _PROC_PREV.get(pid)
                        if p and now > p[1]:
                            cpu = max(0.0, (t - p[0]) / 1e7 / (now - p[1]) / ncpu * 100.0)
                    pm = w["PMC"]()
                    pm.cb = ct.sizeof(pm)
                    if k32.K32GetProcessMemoryInfo(h, ct.byref(pm), pm.cb):
                        mem = int(pm.WorkingSetSize)
                finally:
                    k32.CloseHandle(h)
            out.append({"pid": pid, "name": name, "cpu": round(min(cpu, 100.0), 1), "mem": mem})
            ok = k32.Process32NextW(snap, ct.byref(e))
    finally:
        k32.CloseHandle(snap)
    # baseline so troca depois de 1 s (chamadas rapidas nao zeram o CPU%)
    if update_baseline and (not _PROC_PREV or now - _PROC_T[0] >= PROC_MIN_GAP):
        _PROC_PREV.clear()
        _PROC_PREV.update(seen)
        _PROC_T[0] = now
    return out


def _prime():
    """Grava a baseline de CPU dos processos se estiver velha."""
    if IS_WINDOWS and time.time() - _PROC_T[0] > 10.0:
        try:
            _win_processes()
        except Exception:
            pass


# --------------------------------------------------------------- simulado ---
SIM_PROCS = [
    {"pid": 4, "name": "System", "cpu": 0.5, "mem": 40_000_000},
    {"pid": 612, "name": "lsass.exe", "cpu": 0.1, "mem": 30_000_000},
    {"pid": 1200, "name": "chrome.exe", "cpu": 12.5, "mem": 900_000_000},
    {"pid": 2400, "name": "Spotify.exe", "cpu": 3.0, "mem": 350_000_000},
    {"pid": 3100, "name": "obs64.exe", "cpu": 8.0, "mem": 500_000_000},
    {"pid": 4200, "name": "Code.exe", "cpu": 5.5, "mem": 700_000_000},
]
GB = 1024 ** 3


def _sim_snapshot():
    return {"cpu": 25.0,
            "mem": {"used": 8 * GB, "total": 16 * GB, "pct": 50.0},
            "disk": [{"drive": "C:", "used": 200 * GB, "total": 500 * GB, "pct": 40.0}],
            "net": {"down_bps": 125000.0, "up_bps": 25000.0},
            "gpu": 10.0,
            "temps": {"cpu": 50.0, "gpu": 55.0}}


# ------------------------------------------------------------------- coleta ---
_LOCK = threading.Lock()
_STATE = {"polled": 0.0, "snap": None, "cpu": None, "net": None, "last": 0.0}
_COLLECT_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD = [None]


def touch():
    """Chamado pelo servidor: algum aparelho esta olhando o monitor."""
    _STATE["polled"] = time.time()
    _prime()


def _active():
    return time.time() - _STATE["polled"] < ACTIVE_FOR


def _collect(with_lhm=False):
    now = time.time()
    if not IS_WINDOWS:
        s = _sim_snapshot()
        s["ts"] = float(now)
        return s
    if now - _STATE["last"] > 5.0:     # amostra velha: recomeca as taxas
        _STATE["cpu"] = _STATE["net"] = None
    _STATE["last"] = now
    t = _win_cpu_times()
    prev = _STATE["cpu"]
    cpu = cpu_pct(prev, t) if prev else 0.0
    _STATE["cpu"] = t
    rx, tx = _win_net_bytes()
    pn = _STATE["net"]
    if pn and now > pn[0]:
        dt = now - pn[0]
        down, up = rate(pn[1], rx, dt), rate(pn[2], tx, dt)
    else:
        down = up = 0.0
    _STATE["net"] = (now, rx, tx)
    temps = lhm_temps() if with_lhm else lhm_cached()
    gpu = _win_gpu()
    return {"cpu": float(cpu), "mem": _win_mem(), "disk": _win_disks(),
            "net": {"down_bps": float(down), "up_bps": float(up)},
            "gpu": float(gpu) if gpu is not None else None,
            "temps": temps, "ts": float(now)}


_EMPTY = {"cpu": 0.0, "mem": {"used": 0, "total": 0, "pct": 0.0}, "disk": [],
          "net": {"down_bps": 0.0, "up_bps": 0.0}, "gpu": None,
          "temps": {"cpu": None, "gpu": None}, "ts": 0.0}


def _refresh(with_lhm):
    """Coleta e guarda; serializada, e o LHM (rede) so entra pela thread."""
    with _COLLECT_LOCK:
        try:
            s = _collect(with_lhm)
        except Exception:
            with _LOCK:
                s = _STATE["snap"] or dict(copy.deepcopy(_EMPTY), ts=time.time())
        with _LOCK:
            _STATE["snap"] = s
        return s


def snapshot():
    """Metricas do PC agora. Devolve copia do cache quando a thread esta
    mantendo-o fresco (nunca espera o LibreHardwareMonitor)."""
    with _LOCK:
        s = _STATE["snap"]
    if s:
        age = time.time() - s["ts"]
        th = _THREAD[0]
        if age < 1.0 or not _active() or (th and th.is_alive() and age < 2 * INTERVAL):
            return copy.deepcopy(s)
    return copy.deepcopy(_refresh(False))


def processes(limit=15, sort="cpu"):
    key = "mem" if sort == "mem" else "cpu"
    try:
        lst = _win_processes() if IS_WINDOWS else [dict(p) for p in SIM_PROCS]
    except Exception:
        lst = []
    lst = [p for p in lst if p["pid"] != 0]       # "System Idle Process" nao interessa
    lst.sort(key=lambda p: (p[key], p["name"]), reverse=True)
    return lst[:max(0, int(limit))]


def kill(pid):
    """Encerra um processo. ValueError (pt-BR) para protegidos ou inexistentes."""
    if isinstance(pid, bool) or not isinstance(pid, int):
        raise ValueError("PID inválido.")
    if pid in (0, 4) or pid == os.getpid():
        raise ValueError("Este processo é protegido e não pode ser encerrado.")
    lst = _win_processes(update_baseline=False) if IS_WINDOWS else SIM_PROCS
    name = next((p["name"] for p in lst if p["pid"] == pid), None)
    if name is None:
        raise ValueError("Processo não encontrado.")
    if name.lower() in PROTECTED_NAMES:
        raise ValueError("Este processo é protegido e não pode ser encerrado.")
    if not IS_WINDOWS:
        return
    w = _win()
    h = w["k32"].OpenProcess(0x0001, False, pid)        # PROCESS_TERMINATE
    if not h:
        raise ValueError("Sem permissão para encerrar este processo.")
    try:
        if not w["k32"].TerminateProcess(h, 1):
            raise ValueError("Não foi possível encerrar o processo.")
    finally:
        w["k32"].CloseHandle(h)


# ------------------------------------------------------------------ thread ---
def _loop():
    while not _STOP.is_set():
        if _active():
            try:
                _refresh(True)
            except Exception:
                pass
        _STOP.wait(INTERVAL)


def start():
    if not IS_WINDOWS or (_THREAD[0] and _THREAD[0].is_alive()):
        return
    _STOP.clear()
    _prime()
    _THREAD[0] = threading.Thread(target=_loop, name="monitor", daemon=True)
    _THREAD[0].start()


def stop():
    _STOP.set()
    if _THREAD[0]:
        _THREAD[0].join(2.0)
    _THREAD[0] = None
