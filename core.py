"""FPS Booster PRO core: real system data and reversible, documented tweaks."""
import ctypes, json, os, subprocess, sys, time
import psutil
IS_WIN = sys.platform == "win32"
if IS_WIN:
    import winreg
def _datadir():
    for base in (os.environ.get("APPDATA"), os.path.expanduser("~"), os.environ.get("TEMP")):
        try:
            d = os.path.join(base, "FPSBoosterPro"); os.makedirs(os.path.join(d, "backups"), exist_ok=True); return d
        except Exception: continue
    raise RuntimeError("No writable data folder available")
DATA = _datadir(); BACKUPS = os.path.join(DATA, "backups")
STATE = os.path.join(DATA, "state.json")
DWORD, SZ = 4, 1
NOWIN = 0x08000000 if IS_WIN else 0

def relaunch_admin(args=""):
    """Restart this app elevated (Windows shows the UAC prompt). True if the user accepted."""
    if not IS_WIN: return False
    params = args if getattr(sys, "frozen", False) else f'"{os.path.abspath(sys.argv[0])}" {args}'
    try: return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1) > 32
    except Exception: return False

def is_admin():
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False

class Reg:  # winreg wrapper; in-memory fake off Windows so logic is unit-testable
    fake = {}
    @staticmethod
    def get(h, p, n):
        if IS_WIN:
            try:
                with winreg.OpenKey(getattr(winreg, h), p) as k: return winreg.QueryValueEx(k, n)[0]
            except OSError: return None
        return Reg.fake.get((h, p, n))
    @staticmethod
    def set(h, p, n, v, t):
        if IS_WIN:
            with winreg.CreateKeyEx(getattr(winreg, h), p, 0, winreg.KEY_SET_VALUE) as k: winreg.SetValueEx(k, n, 0, t, v)
        else: Reg.fake[(h, p, n)] = v
    @staticmethod
    def delete(h, p, n):
        if IS_WIN:
            try:
                with winreg.OpenKey(getattr(winreg, h), p, 0, winreg.KEY_SET_VALUE) as k: winreg.DeleteValue(k, n)
            except OSError: pass
        else: Reg.fake.pop((h, p, n), None)

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, creationflags=NOWIN, timeout=20)

# id: (title, description, needs_admin, [(hive, path, name, value, type)])
TWEAKS = {
 "gamemode": ("Enable Windows Game Mode", "Lets Windows prioritise the foreground game.", False,
    [("HKEY_CURRENT_USER", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1, DWORD)]),
 "gamedvr": ("Disable background game capture (Game DVR)", "Stops background recording overhead. Xbox Game Bar clips stop working.", False,
    [("HKEY_CURRENT_USER", r"System\GameConfigStore", "GameDVR_Enabled", 0, DWORD),
     ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0, DWORD)]),
 "transparency": ("Disable window transparency", "Small GPU/CPU saving from the Windows UI.", False,
    [("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0, DWORD)]),
 "animations": ("Disable window minimise/maximise animation", "Cosmetic change; effect on FPS is minor.", False,
    [("HKEY_CURRENT_USER", r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0", SZ)]),
 "mmcss": ("Favour foreground apps in multimedia scheduler", "SystemResponsiveness 20 -> 10. Documented key; gain is usually marginal.", True,
    [("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "SystemResponsiveness", 10, DWORD)]),
}
def _load():
    try: return json.load(open(STATE))
    except Exception: return {"tweaks": {}, "gaming": None}
def _save(s): json.dump(s, open(STATE, "w"), indent=1)

def tweak_status(tid):
    return all(Reg.get(h, p, n) == v for h, p, n, v, t in TWEAKS[tid][3])

def apply_tweaks(ids):
    """Backup keys (.reg export) + original values, then apply. Returns list of (id, ok, msg)."""
    st, out, ts = _load(), [], time.strftime("%Y%m%d-%H%M%S")
    for tid in ids:
        title, _, adm, items = TWEAKS[tid]
        if adm and not is_admin(): out.append((tid, False, "needs administrator")); continue
        try:
            orig = [[h, p, n, Reg.get(h, p, n)] for h, p, n, v, t in items]
            if IS_WIN:
                for i, (h, p, *_ ) in enumerate(items):
                    run(["reg", "export", ("HKCU\\" if h.endswith("USER") else "HKLM\\") + p,
                         os.path.join(BACKUPS, f"{ts}_{tid}_{i}.reg"), "/y"])
            st["tweaks"].setdefault(tid, orig)  # keep the oldest original
            _save(st)
            for h, p, n, v, t in items: Reg.set(h, p, n, v, t)
            out.append((tid, True, "applied"))
        except Exception as e: out.append((tid, False, str(e)))
    return out

def restore_tweaks():
    st = _load(); n = 0
    for tid, orig in list(st["tweaks"].items()):
        for h, p, name, old in orig:
            try:
                Reg.delete(h, p, name) if old is None else Reg.set(h, p, name, old, SZ if isinstance(old, str) else DWORD)
            except Exception: continue
        st["tweaks"].pop(tid); n += 1
    _save(st); return n

HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
def active_plan():
    if not IS_WIN: return None
    o = run(["powercfg", "/getactivescheme"]).stdout
    return o.split(":")[1].split()[0] if ":" in o else None
def set_plan(guid): return IS_WIN and run(["powercfg", "/setactive", guid]).returncode == 0

# ---- processes ----
PROTECTED = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "winlogon.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe", "msmpeng.exe",
    "securityhealthservice.exe", "memcompression", "python.exe", "pythonw.exe", "fpsboosterpro.exe"}
def processes(sort="ram", n=40):
    me, rows = None, []
    try: me = psutil.Process().username()
    except Exception: pass
    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "username"]):
        i = p.info
        if not i["name"] or not i["memory_info"]: continue
        rows.append(dict(pid=i["pid"], name=i["name"], ram=i["memory_info"].rss / 2**20, cpu=(i["cpu_percent"] or 0.0) / (psutil.cpu_count() or 1),
                         closable=i["name"].lower() not in PROTECTED and i["username"] == me))
    rows.sort(key=lambda r: -r[sort]); return rows[:n]
def close_process(pid):
    if pid in (os.getpid(), os.getppid()): raise PermissionError("protected process")
    p = psutil.Process(pid)
    if p.name().lower() in PROTECTED or p.username() != psutil.Process().username(): raise PermissionError("protected process")
    p.terminate()
    try: p.wait(5)
    except psutil.TimeoutExpired: pass

# ---- startup apps (reversible via StartupApproved, same mechanism as Task Manager) ----
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
def startup_items():
    if not IS_WIN: return []
    out = []
    for h in ("HKEY_CURRENT_USER",):
        with winreg.OpenKey(getattr(winreg, h), _RUN) as k:
            i = 0
            while True:
                try: n, v, _ = winreg.EnumValue(k, i); i += 1
                except OSError: break
                try:
                    with winreg.OpenKey(getattr(winreg, h), _APP) as a: flag = winreg.QueryValueEx(a, n)[0][0]
                except OSError: flag = 2
                out.append(dict(name=n, cmd=v, enabled=flag % 2 == 0))
    return out
def set_startup(name, enabled):
    Reg.set("HKEY_CURRENT_USER", _APP, name, bytes([2 if enabled else 3]) + bytes(11), 3)

# ---- temp files ----
def temp_scan(max_age_h=24):
    files, total = [], 0
    for d in {os.environ.get("TEMP", ""), r"C:\Windows\Temp" if IS_WIN else ""}:
        if not d or not os.path.isdir(d): continue
        for r, _, fs in os.walk(d):
            for f in fs:
                p = os.path.join(r, f)
                try:
                    s = os.stat(p)
                    if time.time() - s.st_mtime > max_age_h * 3600: files.append(p); total += s.st_size
                except OSError: pass
    return files, total
def temp_clean(files):
    freed = 0
    for p in files:
        try: s = os.path.getsize(p); os.remove(p); freed += s
        except OSError: pass  # in use / no permission: skipped
    return freed

# ---- hardware ----
def gpu_info():
    try:
        o = run(["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"]).stdout.strip().splitlines()[0].split(", ")
        return dict(name=o[0], usage=float(o[1]), temp=float(o[2]), vram=f"{o[3]}/{o[4]} MiB")
    except Exception: pass
    name = "Unknown"
    if IS_WIN:
        try: name = run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name -join ', '"]).stdout.strip() or name
        except Exception: pass
    return dict(name=name, usage=None, temp=None, vram=None)
def cpu_temp():
    try:
        for ts in psutil.sensors_temperatures().values():
            if ts: return ts[0].current
    except Exception: pass
    return None

# ---- settings ----
SETTINGS = os.path.join(DATA, "settings.json")
DEFAULTS = {"auto_gaming": False, "presentmon_path": ""}
def settings():
    try: d = json.load(open(SETTINGS))
    except Exception: d = {}
    return {**DEFAULTS, **d}
def save_settings(**kw):
    s = settings(); s.update(kw); json.dump(s, open(SETTINGS, "w"), indent=1)

# ---- per-app GPU preference (Windows Graphics settings; reversible, documented) ----
_GPUPREF = r"Software\Microsoft\DirectX\UserGpuPreferences"
def set_gpu_pref(exe_path, mode=2):
    """mode 2 = High performance GPU. Original value is saved and restored by restore_tweaks()."""
    if not exe_path: raise ValueError("no executable path")
    if IS_WIN: run(["reg", "export", "HKCU\\" + _GPUPREF, os.path.join(BACKUPS, time.strftime("%Y%m%d-%H%M%S") + "_gpupref.reg"), "/y"])
    st = _load(); old = Reg.get("HKEY_CURRENT_USER", _GPUPREF, exe_path)
    st["tweaks"].setdefault("gpupref:" + exe_path, [["HKEY_CURRENT_USER", _GPUPREF, exe_path, old]]); _save(st)
    Reg.set("HKEY_CURRENT_USER", _GPUPREF, exe_path, f"GpuPreference={mode};", SZ)

# ---- gaming mode ----
def gaming_state(): return _load()["gaming"]
def gaming_active(): return bool(_load()["gaming"])
def gaming_on(game_pid=None, close_pids=(), auto=False):
    st = _load()
    if st["gaming"]: return "already on"
    st["gaming"] = {"plan": active_plan(), "pid": game_pid, "t": time.time(), "auto": auto}; _save(st)
    set_plan(HIGH_PERF)
    if game_pid and IS_WIN:
        try: psutil.Process(game_pid).nice(psutil.HIGH_PRIORITY_CLASS)
        except Exception: pass
    for pid in close_pids:
        try: close_process(pid)
        except Exception: pass
    return "on"
def gaming_off():
    st = _load(); g = st["gaming"]
    if not g: return "not active"
    if g["plan"]: set_plan(g["plan"])
    if g["pid"] and IS_WIN:
        try: psutil.Process(g["pid"]).nice(psutil.NORMAL_PRIORITY_CLASS)
        except Exception: pass
    st["gaming"] = None; _save(st); return "off"
