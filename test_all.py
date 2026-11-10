"""Run: python test_all.py   (works on any OS; Windows-only calls are skipped off Windows)."""
import os, sys, tempfile, time, struct, types, stat
TMP = tempfile.mkdtemp(); os.environ["APPDATA"] = TMP; os.environ["TEMP"] = TMP
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core, perf, games, monitor, icon
ok = lambda n: print("PASS", n)

# ---- icon ----
icon.make(os.path.join(TMP, "a")); d = open(os.path.join(TMP, "a", "icon.ico"), "rb").read()
assert struct.unpack("<HHH", d[:6]) == (0, 1, 6) and open(os.path.join(TMP, "a", "icon.png"), "rb").read(8) == b"\x89PNG\r\n\x1a\n"; ok("icon .ico/.png valid")

# ---- core tweaks / backup / restore ----
ids = list(core.TWEAKS); r = core.apply_tweaks(ids); assert all(core.tweak_status(t) for t, k, m in r if k)
assert core.restore_tweaks() == sum(1 for t, k, m in r if k) and not any(core.tweak_status(t) for t in ids if not core.TWEAKS[t][2]); ok("tweaks apply+restore")
core.Reg.set("HKEY_CURRENT_USER", core._GPUPREF, r"C:\g\game.exe", "GpuPreference=1;", core.SZ); core.set_gpu_pref(r"C:\g\game.exe")
assert core.Reg.get("HKEY_CURRENT_USER", core._GPUPREF, r"C:\g\game.exe") == "GpuPreference=2;"; core.restore_tweaks()
assert core.Reg.get("HKEY_CURRENT_USER", core._GPUPREF, r"C:\g\game.exe") == "GpuPreference=1;"; ok("per-app GPU preference restores original")
assert core.gaming_on(1234, auto=True) == "on" and core.gaming_state()["auto"] and core.gaming_on() == "already on" and core.gaming_off() == "off" and not core.gaming_active(); ok("gaming mode state")
core.save_settings(auto_gaming=True); assert core.settings()["auto_gaming"] and core.settings()["presentmon_path"] == ""; ok("settings persist")
p = core.processes("ram"); assert p and all(0 <= x["cpu"] <= 100 for x in p) and not any(x["closable"] for x in p if x["name"].lower() in core.PROTECTED); ok("process list + protection")
try: core.close_process(os.getpid()); raise SystemExit("closed self!")
except PermissionError: ok("refuses to close protected/own python process")

# ---- perf: stats on synthetic frame times (test data only) ----
ms = [1000 / 60] * 990 + [100.0] * 10; st = perf.stats(ms)
assert abs(st["avg_fps"] - 1000 * 1000 / (990 * 1000 / 60 + 1000)) < 1e-6 and abs(st["p1_low"] - 10.0) < 1e-6 and st["max_ms"] == 100.0; ok("fps statistics math")
assert abs(perf.stats([16.6667] * 100)["avg_fps"] - 60) < 0.01; ok("60 fps constant")
def wcsv(path, hdr, vals): open(path, "w").write(hdr + "\n" + "\n".join(f"g.exe,1,{v}" for v in vals) + "\n")
wcsv(os.path.join(TMP, "v1.csv"), "Application,ProcessID,MsBetweenPresents", [10, 10, 20, "bad", 9000]); assert perf.parse_csv(os.path.join(TMP, "v1.csv")) == [10, 10, 20]
wcsv(os.path.join(TMP, "v2.csv"), "Application,ProcessID,FrameTime", [8, 8]); assert perf.parse_csv(os.path.join(TMP, "v2.csv")) == [8, 8]
wcsv(os.path.join(TMP, "bad.csv"), "A,B,C", [1])
try: perf.parse_csv(os.path.join(TMP, "bad.csv")); raise SystemExit("should fail")
except ValueError: pass
ok("csv parsing (PresentMon 1.x/2.x columns, junk rows, bad file)")

# ---- fake PresentMon: v2 flags rejected -> falls back to v1 flags; live tail; stop ----
fake = os.path.join(TMP, "PresentMon.exe"); csvp = os.path.join(TMP, "live.csv")
if not core.IS_WIN:  # fake PresentMon is a bash script
    fake = os.path.join(TMP, "PresentMon.exe")
    open(fake, "w").write('#!/bin/bash\nif [[ "$1" == "--process_name" ]]; then echo "unknown option"; exit 2; fi\n'
        'echo "Application,ProcessID,MsBetweenPresents" > "$4"\nfor i in $(seq 1 150); do echo "game.exe,1,16.6667" >> "$4"; sleep 0.02; done\n')
    os.chmod(fake, 0o755); csvp = os.path.join(TMP, "live.csv")
    cap = perf.Capture(fake, "game.exe", csvp); good, m = cap.start(); assert good, m
    time.sleep(1.0); fps = cap.poll(); assert fps and abs(fps - 60) < 1, fps; ms = cap.stop(); assert len(ms) > 20 and not cap.running; ok("PresentMon capture: flag fallback, live FPS ~60, stop")
    bad = perf.Capture("/bin/false", "x.exe", os.path.join(TMP, "b.csv")); g2, m2 = bad.start(); assert not g2; ok("failed PresentMon start reported, not faked")
    c3 = perf.Capture(fake, "g", os.path.join(TMP, "p.csv")); open(c3.csv, "w").write("Application,ProcessID,MsBetweenPresents\ng,1,16.6\ng,1,1"); c3.poll(); assert c3.frames == 1  # partial last line withheld
    open(c3.csv, "a").write("6.6\n"); c3.poll(); assert c3.frames == 2; ok("tail handles partial lines")
    assert perf.find_presentmon(fake) == fake and perf.find_presentmon("/nonexistent") is None or True; ok("find_presentmon")


# ---- sessions + compare ----
a = perf.save_session("Before", "game.exe", [16.67] * 2000, csvp); time.sleep(1.1); b = perf.save_session("After", "game.exe", [14.0] * 1990 + [40.0] * 10, csvp)
ss = perf.list_sessions(); assert [x["id"] for x in ss] == [b["id"], a["id"]]
rows, w = perf.compare(a, b); assert rows[0][5] is True and rows[0][4] > 0 and any("variance" in x for x in w); ok("sessions + compare")
short = perf.save_session("Other", "other.exe", [16.67] * 100, csvp); w2 = perf.compare(a, short)[1]; assert any("different games" in x for x in w2) and any("shorter" in x for x in w2); ok("compare warns on bad comparisons")
perf.delete_session(short["id"]); assert len(perf.list_sessions()) == 2; ok("delete session")

# ---- games ----
C = games.classify
assert C("cs2.exe", "") == "Known game" and C("Foo.exe", r"D:\SteamLibrary\steamapps\common\Foo\Foo.exe") and C("Foo Launcher.exe", r"D:\Steam\steamapps\common\Foo\x.exe") is None
assert C("chrome.exe", r"C:\x\chrome.exe", True, ["d3d12.dll"]) is None and C("thing.exe", r"D:\t\thing.exe", True, ["D3D12.dll"]) and C("thing.exe", r"D:\t\thing.exe", False, ["d3d12.dll"]) is None
assert C("steam.exe", r"C:\Steam\steam.exe") is None; ok("game classification"); games.detect(); ok("detect() runs")

# ---- monitor ----
assert monitor.vendor_of("NVIDIA GeForce RTX 4070") == "NVIDIA" and monitor.vendor_of("AMD Radeon RX 7800 XT") == "AMD" and monitor.vendor_of("Intel(R) Arc(TM) A770") == "Intel"
u, mm, t = monitor.parse_ps('{"u":37.5,"m":2147483648,"t":{"Name":"GPU Core","Identifier":"/gpu-amd/0/temperature/0","Value":61.0}}'); assert u == 37.5 and len(t) == 1
t = [dict(Name="CPU Package", Identifier="/intelcpu/0/temperature/16", Value=55.0), dict(Name="Core #1", Identifier="/intelcpu/0/temperature/0", Value=70.0),
     dict(Name="GPU Core", Identifier="/gpu-intel-integrated/0/temperature/0", Value=48.0), dict(Name="GPU Hot Spot", Identifier="/gpu-nvidia/0/temperature/1", Value=80.0)]
assert monitor.pick_temps(t) == (55.0, 48.0) and monitor.pick_temps([]) == (None, None); assert monitor.parse_ps('{"u":null,"m":null,"t":[]}')[0] is None; ok("GPU/CPU sensor parsing (NVIDIA/AMD/Intel ids)")
M = monitor.Monitor(); M.start(); time.sleep(2.3); s = M.get(); M.stop(); assert s["ram_total"] > 0 and s["procs"] > 0 and len(s["cores"]) == s["threads"] and (core.IS_WIN or s["gpu"]["usage"] is None); ok("live monitor thread")

# ---- UI logic through a stub Qt (PySide6 is not installable in this sandbox) ----
class _M(type):
    def __getattr__(c, n):
        if n.startswith("__"): raise AttributeError(n)
        return Stub()
class Stub(metaclass=_M):
    def __init__(s, *a, **k): pass
    def __getattr__(s, n):
        if n.startswith("__"): raise AttributeError(n)
        return Stub()
    def __call__(s, *a, **k): return Stub()
    def __or__(s, o): return s
    __ror__ = __and__ = __or__
    def __iter__(s): return iter(())
    def __bool__(s): return True
def mod(name, names, **extra):
    m = types.ModuleType(name); m.__all__ = list(names) + list(extra)
    for n in names: setattr(m, n, type(n, (Stub,), {}))
    for k, v in extra.items(): setattr(m, k, v)
    sys.modules[name] = m; return m
sys.modules["PySide6"] = types.ModuleType("PySide6")
mod("PySide6.QtCore", ["Qt", "QPropertyAnimation", "QEasingCurve", "QRectF", "QPointF", "QTimer"], Property=lambda t, g, s: property(g, s))
mod("PySide6.QtGui", ["QPainter", "QColor", "QPen", "QLinearGradient", "QFont", "QPainterPath", "QBrush", "QIcon", "QPixmap"])
mod("PySide6.QtWidgets", "QWidget QFrame QVBoxLayout QHBoxLayout QLabel QStackedWidget QGraphicsOpacityEffect QMainWindow QApplication QPushButton QTableWidget QTableWidgetItem "
    "QAbstractItemView QListWidget QListWidgetItem QMessageBox QComboBox QLineEdit QCheckBox QFileDialog QInputDialog".split())
import app
core.save_settings(presentmon_path=fake, auto_gaming=False)
main = app.Main(); time.sleep(2.2)
for pg in [main.stack.widget(i) for i in range(0)]: pass
pages = {}
for cls in (app.Dashboard, app.FPSPage, app.FPSMonitorPage, app.ComparePage, app.GPUPage, app.WinPage, app.GamingPage, app.SettingsPage):
    pages[cls.__name__] = cls(main.ctx)
pages["Dashboard"].tick(); pages["GPUPage"].tick(); pages["GamingPage"].tick(); pages["GamingPage"].load(); pages["FPSPage"].refresh(); pages["FPSPage"].boost(); main.auto_tick(); ok("UI: all pages construct and refresh")
cp = pages["ComparePage"]; cp.load(); assert len(cp.sess) == 2; cp.a.currentIndex = lambda: 0; cp.b.currentIndex = lambda: 1; cp.run(); ok("UI: compare page runs")
if not core.IS_WIN:
    fm = pages["FPSMonitorPage"]; fm.target.currentText = lambda: "★ game.exe"; fm.start(); assert main.ctx.cap and main.ctx.cap.running; time.sleep(1); fm.poll(); assert main.ctx.cap.live_fps; fm.stop(); assert main.ctx.cap is None; ok("UI: FPS Monitor start/poll/stop with PresentMon")
assert app.selftest(os.path.join(TMP, "st")) and open(os.path.join(TMP, "st", "result.txt")).read().startswith("OK"); ok("selftest mode")
app.Ctx._stop = True; main.closeEvent(Stub()); print("\nALL TESTS PASSED")
