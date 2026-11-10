"""Real-time hardware monitor. NVIDIA: nvidia-smi. AMD/Intel: Windows GPU performance counters (usage, VRAM).
Temperatures for AMD/Intel GPUs and most CPUs need LibreHardwareMonitor running (WMI); otherwise reported as unavailable."""
import copy, json, os, shutil, threading, time
import psutil
import core

def vendor_of(name):
    n = (name or "").lower()
    return "NVIDIA" if "nvidia" in n or "geforce" in n else "AMD" if "amd" in n or "radeon" in n else "Intel" if "intel" in n else "Unknown"

PS = r"""$ErrorActionPreference='SilentlyContinue'
$u=$null;$m=$null
if(%COUNTERS%){$u=[math]::Min(100,((Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage').CounterSamples|Measure-Object CookedValue -Sum).Sum)
$m=((Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples|Measure-Object CookedValue -Sum).Sum}
$t=@(Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor|?{$_.SensorType -eq 'Temperature'}|select Name,Identifier,Value)
@{u=$u;m=$m;t=$t}|ConvertTo-Json -Compress -Depth 3"""

def parse_ps(text):
    d = json.loads(text); t = d.get("t") or []
    if isinstance(t, dict): t = [t]
    return d.get("u"), d.get("m"), t

def pick_temps(sensors):
    cpu, gpu = [], []
    for x in sensors:
        ident = (x.get("Identifier") or "").lower().split("/"); nm = (x.get("Name") or "").lower(); v = x.get("Value")
        if v is None or len(ident) < 2: continue
        if "cpu" in ident[1]: cpu.append((any(k in nm for k in ("package", "tctl", "tdie")), v))
        elif ident[1].startswith("gpu"): gpu.append((("core" in nm), v))
    def best(l): return max(l, key=lambda a: (a[0], a[1]))[1] if l else None
    return best(cpu), best(gpu)

def num(x):
    try: return float(x)
    except Exception: return None

def nvidia_path():
    for p in (shutil.which("nvidia-smi"), r"C:\Windows\System32\nvidia-smi.exe", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if p and os.path.exists(p): return p

def query_nvidia(path):
    try:
        o = core.run([path, "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,clocks.gr,power.draw",
                      "--format=csv,noheader,nounits"]).stdout.strip().splitlines()[0].split(", ")
        return dict(name=o[0], vendor="NVIDIA", usage=num(o[1]), temp=num(o[2]), vram_used=num(o[3]), vram_total=num(o[4]),
                    clock=num(o[5]), power=num(o[6]), source="nvidia-smi")
    except Exception: return None

def list_gpus():
    if not core.IS_WIN: return []
    try: return [l.strip() for l in core.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"]).stdout.splitlines() if l.strip()]
    except Exception: return []

class Monitor:
    def __init__(s):
        s._lock, s._stop = threading.Lock(), threading.Event()
        s._snap = dict(cpu=0.0, cores=[], threads=psutil.cpu_count() or 0, freq=None, ram=0.0, ram_used=0, ram_total=0, disk_r=0.0, disk_w=0.0,
                       net_d=0.0, net_u=0.0, procs=0, cpu_temp=None, gpu_temp_lhm=None, gpus=[],
                       gpu=dict(name="Detecting…", vendor="Unknown", usage=None, temp=None, vram_used=None, vram_total=None, clock=None, power=None, source=None))
    def get(s):
        with s._lock: return copy.deepcopy(s._snap)
    def _upd(s, **kw):
        with s._lock: s._snap.update(kw)
    def start(s):
        for f in (s._fast, s._slow): threading.Thread(target=f, daemon=True).start()
    def stop(s): s._stop.set()
    def _fast(s):
        psutil.cpu_percent(None); d0, n0, t0 = psutil.disk_io_counters(), psutil.net_io_counters(), time.time()
        while not s._stop.is_set():
            time.sleep(1)
            try:
                now = time.time(); dt = max(now - t0, 0.001); d1, n1 = psutil.disk_io_counters(), psutil.net_io_counters(); vm = psutil.virtual_memory()
                f = psutil.cpu_freq(); ct = None
                try:
                    for ts in psutil.sensors_temperatures().values():
                        if ts: ct = ts[0].current; break
                except Exception: pass
                s._upd(cpu=psutil.cpu_percent(None), cores=psutil.cpu_percent(None, percpu=True), freq=f.current if f else None, ram=vm.percent,
                       ram_used=vm.used, ram_total=vm.total, procs=len(psutil.pids()),
                       disk_r=((d1.read_bytes - d0.read_bytes) / dt / 2**20) if d0 and d1 else 0.0, disk_w=((d1.write_bytes - d0.write_bytes) / dt / 2**20) if d0 and d1 else 0.0,
                       net_d=((n1.bytes_recv - n0.bytes_recv) / dt / 2**20) if n0 and n1 else 0.0, net_u=((n1.bytes_sent - n0.bytes_sent) / dt / 2**20) if n0 and n1 else 0.0,
                       **({"cpu_temp": ct} if ct is not None else {}))
                d0, n0, t0 = d1, n1, now
            except Exception: pass
    def _slow(s):
        names, nv, first, lhm_ok = list_gpus(), nvidia_path(), True, False
        s._upd(gpus=names)
        primary = next((n for n in names if vendor_of(n) in ("NVIDIA", "AMD")), names[0] if names else "No GPU detected")
        while not s._stop.is_set():
            try:
                g = query_nvidia(nv) if nv else None
                need_ps = core.IS_WIN and (g is None or first or lhm_ok)
                u = m = None; sensors = []
                if need_ps:
                    r = core.run(["powershell", "-NoProfile", "-Command", PS.replace("%COUNTERS%", "$true" if g is None else "$false")])
                    u, m, sensors = parse_ps(r.stdout.strip()); first = False; lhm_ok = bool(sensors)
                cpu_t, gpu_t = pick_temps(sensors)
                if g is None:
                    g = dict(name=primary, vendor=vendor_of(primary), usage=num(u), temp=gpu_t, vram_used=(m / 2**20) if m else None, vram_total=None,
                             clock=None, power=None, source="Windows GPU counters (3D engine)" if u is not None else None)
                elif g["temp"] is None: g["temp"] = gpu_t
                s._upd(gpu=g, **({"cpu_temp": cpu_t} if cpu_t is not None else {}))
            except Exception: pass
            time.sleep(3)
