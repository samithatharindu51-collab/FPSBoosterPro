import ctypes, os, platform, sys, threading, time, traceback
import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import *
import core, games, monitor, perf
from widgets import Gauge, Spark, Tile, FadeStack

def res(p): return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), p)

QSS = """* {font-family:'Segoe UI'; color:#e8e8f4; font-size:13px}
QMainWindow,QWidget#bg{background:#07070c} QFrame#side{background:#0c0c14;border-right:1px solid #1b1b2b}
QListWidget{background:transparent;border:none;outline:0} QListWidget#nav::item{padding:12px 14px;border-radius:10px;margin:2px 10px;color:#9a9ab5}
QListWidget#nav::item:hover{background:#15152a;color:#fff} QListWidget#nav::item:selected{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #25306e,stop:1 #3a2275);color:#fff}
QFrame#card{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #12121c,stop:1 #0e0e17);border:1px solid #23233a;border-radius:16px}
QPushButton{background:#181826;border:1px solid #30305a;border-radius:10px;padding:9px 16px}
QPushButton:hover{border-color:#7a6cff;background:#202036} QPushButton:pressed{background:#2a2a48} QPushButton:disabled{color:#55556b;border-color:#1f1f33}
QPushButton#boost{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2d6bff,stop:1 #8a3dff);border:none;font-size:17px;font-weight:bold;padding:15px 40px;border-radius:14px;color:#fff}
QPushButton#boost:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4a82ff,stop:1 #a15cff)}
QPushButton#danger{border-color:#7a2a3d} QPushButton#danger:hover{background:#3a1522;border-color:#ff4d6d}
QLabel#h{font-size:26px;font-weight:bold;color:#fff} QLabel#sub{color:#7d7d99;font-size:11px;font-weight:bold} QLabel#tile{font-size:19px;font-weight:bold}
QLabel#big{font-size:64px;font-weight:bold;color:#2bd67b} QLabel#muted{color:#8d8da8}
QTableWidget,QListWidget#plain{background:#0e0e17;border:1px solid #1d1d30;border-radius:10px;gridline-color:#181828;selection-background-color:#2a2a66}
QHeaderView::section{background:#12121c;border:none;padding:7px;color:#9a9ab5;font-weight:bold}
QComboBox,QLineEdit{background:#12121c;border:1px solid #2a2a48;border-radius:9px;padding:7px 10px} QComboBox QAbstractItemView{background:#12121c;selection-background-color:#2a2a66}
QCheckBox{spacing:8px} QScrollBar:vertical{background:transparent;width:10px} QScrollBar::handle:vertical{background:#2a2a48;border-radius:5px;min-height:30px}
QScrollBar::add-line,QScrollBar::sub-line{height:0} QToolTip{background:#12121c;color:#fff;border:1px solid #3a3a66}"""

def card():
    f = QFrame(); f.setObjectName("card"); l = QVBoxLayout(f); l.setContentsMargins(16, 14, 16, 14); return f, l
def header(t, sub=""):
    w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 6); l.setSpacing(0); a = QLabel(t); a.setObjectName("h"); l.addWidget(a)
    if sub: b = QLabel(sub); b.setObjectName("muted"); l.addWidget(b)
    return w
def msg(parent, t, m): QMessageBox.information(parent, t, m)
def ask_admin(parent, why):
    """Ask before elevating. Returns True if an elevated copy was started (this one then quits)."""
    if QMessageBox.question(parent, "Administrator permission", why + "\n\nRestart FPS BOOSTER PRO as administrator now? Windows will ask for your permission.\nChoose No to continue without it.") != QMessageBox.Yes: return False
    if core.relaunch_admin(): QApplication.quit(); return True
    QMessageBox.warning(parent, "Administrator permission", "Elevation was cancelled or is unavailable."); return False
def mb(v, unit="MB"): return "n/a" if v is None else (f"{v/1024:.1f} GB" if v >= 1024 else f"{v:.0f} MB")

class Ctx:
    """Shared state: hardware monitor, active PresentMon capture, detected games."""
    def __init__(s):
        s.mon = monitor.Monitor(); s.mon.start(); s.cap = None; s.games = []; s._stop = False
        threading.Thread(target=s._loop, daemon=True).start()
    def _loop(s):
        while not s._stop:
            try: s.games = games.detect()
            except Exception: pass
            time.sleep(4)

class Dashboard(QWidget):
    def __init__(s, ctx):
        super().__init__(); s.ctx = ctx; L = QVBoxLayout(s); L.addWidget(header("Dashboard", "Live hardware telemetry — real values only"))
        row = QHBoxLayout(); s.g, s.sub = {}, {}
        for k, c1, c2, mx in (("CPU", "#2d6bff", "#27d3ff", 100), ("GPU", "#8a3dff", "#ff5fd2", 100), ("RAM", "#2d6bff", "#8a3dff", 100), ("FPS", "#2bd67b", "#27d3ff", 240)):
            f, l = card(); s.g[k] = Gauge(k, "" if k == "FPS" else "%", c1, c2, mx); s.g[k].setMinimumHeight(170); s.sub[k] = QLabel("—"); s.sub[k].setObjectName("muted")
            s.sub[k].setAlignment(Qt.AlignCenter); s.sub[k].setWordWrap(True); l.addWidget(s.g[k]); l.addWidget(s.sub[k]); row.addWidget(f)
        L.addLayout(row)
        tr = QHBoxLayout(); s.t = {k: Tile(k) for k in ("CPU temp", "GPU temp", "VRAM used", "Disk R/W", "Network ↓/↑", "Processes")}
        for t in s.t.values(): tr.addWidget(t)
        L.addLayout(tr); bot = QHBoxLayout(); f, l = card(); l.addWidget(QLabel("CPU load")); s.sc = Spark("#3d7bff"); l.addWidget(s.sc)
        l.addWidget(QLabel("GPU load")); s.sg = Spark("#c15cff"); l.addWidget(s.sg); bot.addWidget(f, 3)
        f2, l2 = card(); s.info = QLabel(); s.info.setWordWrap(True); s.info.setTextFormat(Qt.RichText); l2.addWidget(s.info); l2.addStretch(); bot.addWidget(f2, 2); L.addLayout(bot, 1)
        s.timer = QTimer(s); s.timer.timeout.connect(s.tick); s.timer.start(1000); s.tick()
    def tick(s):
        m = s.ctx.mon.get(); g = m["gpu"]; cap = s.ctx.cap
        s.g["CPU"].setValue(m["cpu"]); s.sub["CPU"].setText(f"{m['threads']} threads" + (f" · {m['freq']/1000:.2f} GHz" if m["freq"] else ""))
        s.g["GPU"].setValue(g["usage"]); s.sub["GPU"].setText(f"{g['name']}" + (f" · {g['clock']:.0f} MHz" if g.get("clock") else ""))
        s.g["RAM"].setValue(m["ram"]); s.sub["RAM"].setText(f"{m['ram_used']/2**30:.1f} / {m['ram_total']/2**30:.1f} GB")
        live = cap.live_fps if cap and cap.running else None
        s.g["FPS"].setValue(live, f"{live:.0f}" if live else None); s.sub["FPS"].setText("PresentMon capture running" if live else "Start a capture in FPS Monitor")
        s.t["CPU temp"].set(f"{m['cpu_temp']:.0f} °C" if m["cpu_temp"] is not None else "n/a"); s.t["GPU temp"].set(f"{g['temp']:.0f} °C" if g["temp"] is not None else "n/a")
        s.t["VRAM used"].set(mb(g["vram_used"]) + (f" / {mb(g['vram_total'])}" if g["vram_total"] else "")); s.t["Disk R/W"].set(f"{m['disk_r']:.1f} / {m['disk_w']:.1f} MB/s")
        s.t["Network ↓/↑"].set(f"{m['net_d']:.2f} / {m['net_u']:.2f} MB/s"); s.t["Processes"].set(str(m["procs"]))
        s.sc.push(m["cpu"]); s.sg.push(g["usage"] or 0); gm = s.ctx.games
        s.info.setText(f"<b>Game detected:</b> {gm[0]['name'] + ' — ' + gm[0]['reason'] if gm else 'none'}<br><b>Gaming Mode:</b> {'ACTIVE' if core.gaming_active() else 'off'}"
            f"<br><b>Tweaks applied:</b> {len([k for k in core._load()['tweaks'] if not k.startswith('gpupref:')])}<br><b>System:</b> {platform.platform()}"
            f"<br><b>GPU data source:</b> {g.get('source') or 'unavailable'}<br><b>Administrator:</b> {'yes' if core.is_admin() else 'no (some features limited)'}")

class FPSPage(QWidget):
    def __init__(s, ctx):
        super().__init__(); L = QVBoxLayout(s); L.addWidget(header("FPS Booster", "Documented, reversible Windows settings. Registry keys are exported before any change."))
        L.addWidget(QLabel("Measure honestly:  ① capture a BEFORE run in FPS Monitor  →  ② BOOST NOW  →  ③ capture an AFTER run  →  ④ open Compare. No FPS gain is ever claimed without that data."))
        s.t = QTableWidget(len(core.TWEAKS), 3); s.t.setHorizontalHeaderLabels(["Apply", "Tweak", "Status"]); s.t.horizontalHeader().setStretchLastSection(True)
        s.t.setColumnWidth(0, 60); s.t.setColumnWidth(1, 640); s.ids = list(core.TWEAKS); L.addWidget(s.t)
        b = QPushButton("⚡  BOOST NOW"); b.setObjectName("boost"); b.clicked.connect(s.boost)
        r = QPushButton("Restore previous settings"); r.clicked.connect(s.restore); L.addWidget(b); L.addWidget(r); s.refresh()
    def refresh(s):
        for i, tid in enumerate(s.ids):
            ti, d, adm, _ = core.TWEAKS[tid]; on = core.tweak_status(tid)
            c = QTableWidgetItem(); c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled); c.setCheckState(Qt.Unchecked if on else Qt.Checked); s.t.setItem(i, 0, c)
            s.t.setItem(i, 1, QTableWidgetItem(f"{ti} — {d}" + (" [admin]" if adm else ""))); s.t.setItem(i, 2, QTableWidgetItem("already applied" if on else "not applied"))
    def boost(s):
        sel = [tid for i, tid in enumerate(s.ids) if s.t.item(i, 0).checkState() == Qt.Checked]
        if not sel: return msg(s, "Nothing to do", "All selected settings are already applied.")
        need = [t for t in sel if core.TWEAKS[t][2]]
        if need and not core.is_admin():
            if ask_admin(s, "These settings need administrator rights:\n" + "\n".join("• " + core.TWEAKS[t][0] for t in need)): return
            sel = [t for t in sel if t not in need]
            if not sel: return
        if QMessageBox.question(s, "Confirm", "These changes will be made:\n\n" + "\n".join("• " + core.TWEAKS[x][0] for x in sel) + "\n\nA registry backup is created first.") != QMessageBox.Yes: return
        res_ = core.apply_tweaks(sel); s.refresh(); msg(s, "Done", "\n".join(f"{'✔' if ok else '✘'} {core.TWEAKS[t][0]}: {m}" for t, ok, m in res_))
    def restore(s): n = core.restore_tweaks(); s.refresh(); msg(s, "Restored", f"Restored {n} setting group(s).")

class FPSMonitorPage(QWidget):
    def __init__(s, ctx):
        super().__init__(); s.ctx = ctx; L = QVBoxLayout(s); L.addWidget(header("FPS Monitor", "Real frame times captured with Intel PresentMon"))
        f, l = card(); s.pm = QLabel(); s.pm.setTextFormat(Qt.RichText); s.pm.setOpenExternalLinks(True); s.pm.setWordWrap(True); r = QHBoxLayout(); r.addWidget(s.pm, 1)
        br = QPushButton("Locate PresentMon.exe…"); br.clicked.connect(s.browse); r.addWidget(br); l.addLayout(r); L.addWidget(f)
        f, l = card(); r = QHBoxLayout(); s.target = QComboBox(); s.target.setEditable(True); s.target.setMinimumWidth(280); rf = QPushButton("Refresh"); rf.clicked.connect(s.targets)
        s.kind = QComboBox(); s.kind.addItems(["Before", "After", "Other"]); s.note = QLineEdit(); s.note.setPlaceholderText("Note (e.g. scene / settings)")
        for w in (QLabel("Game process:"), s.target, rf, QLabel("Label:"), s.kind, s.note): r.addWidget(w)
        l.addLayout(r); r = QHBoxLayout(); s.go = QPushButton("●  Start capture"); s.go.setObjectName("boost"); s.go.clicked.connect(s.start)
        s.end = QPushButton("■  Stop && save"); s.end.clicked.connect(s.stop); s.end.setEnabled(False); r.addWidget(s.go); r.addWidget(s.end); l.addLayout(r); L.addWidget(f)
        f, l = card(); s.big = QLabel("—"); s.big.setObjectName("big"); s.big.setAlignment(Qt.AlignCenter); l.addWidget(s.big); s.sp = Spark("#2bd67b", None, 120, 110); l.addWidget(s.sp)
        s.res = QLabel("No capture yet."); s.res.setObjectName("muted"); s.res.setWordWrap(True); l.addWidget(s.res); L.addWidget(f, 1)
        s.timer = QTimer(s); s.timer.timeout.connect(s.poll); s.timer.start(500); s.targets(); s.check()
    def check(s):
        p = perf.find_presentmon(core.settings()["presentmon_path"])
        s.pm.setText(f"<b>PresentMon:</b> {p}" if p else "<b>PresentMon not found.</b> Download <a href='https://github.com/GameTechDev/PresentMon/releases'>PresentMon from GitHub</a> "
                     "(free, MIT) and click Locate… or place it next to this app. Requires administrator rights. FPS is never estimated without it.")
        s.go.setEnabled(bool(p) and not (s.ctx.cap and s.ctx.cap.running)); return p
    def browse(s):
        p, _ = QFileDialog.getOpenFileName(s, "Select PresentMon executable", "", "PresentMon (*.exe)")
        if p: core.save_settings(presentmon_path=p); s.check()
    def targets(s):
        s.target.clear(); seen = set()
        for g in s.ctx.games + core.processes("ram", 40):
            if g["name"] not in seen: seen.add(g["name"]); s.target.addItem(("★ " if "reason" in g else "") + g["name"], g["name"])
    def start(s):
        pm = s.check(); name = s.target.currentText().replace("★ ", "").strip()
        if not pm or not name: return msg(s, "Cannot start", "Select a game process and locate PresentMon.exe.")
        if not core.is_admin() and ask_admin(s, "Capturing frame times with PresentMon needs administrator rights (or membership of the 'Performance Log Users' group)."): return
        cap = perf.Capture(pm, name, os.path.join(perf.SESS, "live_capture.csv")); ok, m = cap.start()
        if not ok: return QMessageBox.warning(s, "PresentMon failed", m)
        s.ctx.cap = cap; s.go.setEnabled(False); s.end.setEnabled(True); s.res.setText(f"Capturing {name}… start/continue playing; frames appear once the game presents frames.")
    def poll(s):
        c = s.ctx.cap
        if not c: return
        if c.running:
            fps = c.poll()
            if fps: s.big.setText(f"{fps:.0f} FPS"); s.sp.push(fps)
            else: s.big.setText("waiting…")
        elif s.end.isEnabled(): s.res.setText("PresentMon stopped unexpectedly. Press Stop to keep what was captured.")
    def stop(s):
        c = s.ctx.cap; ms = c.stop() if c else []; s.ctx.cap = None; s.end.setEnabled(False); s.check(); s.big.setText("—")
        if len(ms) < 30: s.res.setText("No usable frames captured (game not presenting, wrong process name, or PresentMon needs administrator)."); return
        st = perf.stats(ms)
        s.res.setText(f"{st['frames']} frames · {st['duration']:.0f} s · avg {st['avg_fps']:.1f} FPS · 1% low {st['p1_low']:.1f} · 0.1% low {st['p01_low']:.1f} · worst frame {st['max_ms']:.1f} ms")
        if QMessageBox.question(s, "Save capture", f"Save this capture as '{s.kind.currentText()}'?") == QMessageBox.Yes:
            perf.save_session(s.kind.currentText(), c.name, ms, c.csv, note=s.note.text()); msg(s, "Saved", "Capture saved. Open Compare to analyse it.")

class ComparePage(QWidget):
    def __init__(s, ctx):
        super().__init__(); L = QVBoxLayout(s); L.addWidget(header("Compare", "Before-and-after performance from real captures"))
        f, l = card(); r = QHBoxLayout(); s.a, s.b = QComboBox(), QComboBox(); s.a.setMinimumWidth(320); s.b.setMinimumWidth(320)
        for w in (QLabel("Baseline (A):"), s.a, QLabel("Compare (B):"), s.b): r.addWidget(w)
        l.addLayout(r); r = QHBoxLayout()
        for txt, fn, n in (("Compare", s.run, "boost"), ("Reload", s.load, ""), ("Import PresentMon/CapFrameX CSV…", s.imp, ""), ("Delete A", s.delete, "danger")):
            b = QPushButton(txt); b.clicked.connect(fn); b.setObjectName(n) if n else None; r.addWidget(b)
        l.addLayout(r); L.addWidget(f); s.t = QTableWidget(0, 5); s.t.setHorizontalHeaderLabels(["Metric", "A", "B", "Change", "Change %"]); s.t.horizontalHeader().setStretchLastSection(True)
        s.t.setColumnWidth(0, 230); L.addWidget(s.t, 1); s.v = QLabel(); s.v.setWordWrap(True); L.addWidget(s.v); s.sess = []; s.load()
    def load(s):
        s.sess = perf.list_sessions(); s.a.clear(); s.b.clear()
        for d in s.sess: s.a.addItem(perf.title(d)); s.b.addItem(perf.title(d))
        if len(s.sess) > 1: s.a.setCurrentIndex(1)
    def run(s):
        i, j = s.a.currentIndex(), s.b.currentIndex()
        if i < 0 or j < 0 or i == j: return msg(s, "Compare", "Pick two different captures (capture 'Before' and 'After' in FPS Monitor, or import CSVs).")
        A, B = s.sess[i], s.sess[j]; rows, warn = perf.compare(A, B); s.t.setRowCount(len(rows))
        for r, (n, x, y, d, p, good) in enumerate(rows):
            tag = "  ▲ better" if good else "  ▼ worse" if good is False else ""
            for c, v in enumerate((n, f"{x:.1f}", f"{y:.1f}", f"{d:+.1f}{tag}", f"{p:+.1f}%")): s.t.setItem(r, c, QTableWidgetItem(v))
        s.v.setText(f"A: tweaks {A['tweaks'] or 'none'}, Gaming Mode {'on' if A['gaming_mode'] else 'off'}   |   B: tweaks {B['tweaks'] or 'none'}, Gaming Mode {'on' if B['gaming_mode'] else 'off'}\n\n" + "\n".join("⚠ " + w for w in warn))
    def imp(s):
        p, _ = QFileDialog.getOpenFileName(s, "Import frame-time CSV", "", "CSV (*.csv)")
        if not p: return
        try: ms = perf.parse_csv(p); lab, ok = QInputDialog.getItem(s, "Label", "Label this capture:", ["Before", "After", "Other"], 0, False)
        except Exception as e: return QMessageBox.warning(s, "Import failed", str(e))
        if ok and len(ms) >= 30: perf.save_session(lab, os.path.splitext(os.path.basename(p))[0], ms, p, "imported"); s.load()
        elif ok: msg(s, "Import", "Too few frames in this CSV.")
    def delete(s):
        i = s.a.currentIndex()
        if i >= 0 and QMessageBox.question(s, "Delete", "Delete capture A permanently?") == QMessageBox.Yes: perf.delete_session(s.sess[i]["id"]); s.load()

class ProcPage(QWidget):
    def __init__(s, name, sort):
        super().__init__(); s.sort = sort; L = QVBoxLayout(s); L.addWidget(header(name, "Protected Windows/security processes (🔒) cannot be closed. Closing an app may lose unsaved work."))
        s.t = QTableWidget(0, 4); s.t.setHorizontalHeaderLabels(["Process", "PID", "RAM (MB)", "CPU %"]); s.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        s.t.horizontalHeader().setStretchLastSection(True); s.t.setColumnWidth(0, 320); L.addWidget(s.t)
        r = QHBoxLayout(); a = QPushButton("Refresh"); a.clicked.connect(s.load); c = QPushButton("Close selected"); c.setObjectName("danger"); c.clicked.connect(s.close_sel); r.addWidget(a); r.addWidget(c); L.addLayout(r)
        core.processes(sort); s.load()
    def load(s):
        s.rows = core.processes(s.sort); s.t.setRowCount(len(s.rows))
        for i, r in enumerate(s.rows):
            for j, v in enumerate((r["name"] + ("" if r["closable"] else " 🔒"), r["pid"], f"{r['ram']:.0f}", f"{r['cpu']:.1f}")): s.t.setItem(i, j, QTableWidgetItem(str(v)))
    def close_sel(s):
        rows = sorted({i.row() for i in s.t.selectedIndexes()}); t = [s.rows[i] for i in rows if s.rows[i]["closable"]]
        if not t or QMessageBox.question(s, "Confirm", "Close:\n" + "\n".join(r["name"] for r in t)) != QMessageBox.Yes: return
        for r in t:
            try: core.close_process(r["pid"])
            except Exception as e: QMessageBox.warning(s, "Failed", f"{r['name']}: {e}")
        s.load()

GPU_TIPS = {"NVIDIA": "NVIDIA Control Panel → Manage 3D settings → Power management mode: 'Prefer maximum performance' (per game), Low Latency Mode: On/Ultra for competitive games. Keep the Game Ready driver current.",
            "AMD": "AMD Software: Adrenalin → Gaming → per-game profile: enable Radeon Anti-Lag, disable Radeon Chill for maximum FPS. Keep the Adrenalin driver current.",
            "Intel": "Intel Graphics Software / Command Center: set the game to high performance. Integrated GPUs depend heavily on RAM: use dual-channel memory. Keep the Arc/Iris driver current.",
            "Unknown": "Keep your GPU driver current from the vendor website."}
class GPUPage(QWidget):
    def __init__(s, ctx):
        super().__init__(); s.ctx = ctx; L = QVBoxLayout(s); L.addWidget(header("GPU Optimizer", "NVIDIA · AMD · Intel"))
        f, l = card(); s.info = QLabel(); s.info.setTextFormat(Qt.RichText); l.addWidget(s.info); L.addWidget(f)
        f, l = card(); s.tips = QLabel(); s.tips.setWordWrap(True); l.addWidget(s.tips)
        l.addWidget(QLabel("Windows Settings → System → Display → Graphics: assign 'High performance' to your game (laptops with two GPUs), and enable Hardware-accelerated GPU scheduling if your driver supports it (restart needed). "
                           "These are manual recommendations; the app only changes per-game GPU preference from the Gaming Mode page, with backup."))
        l.itemAt(1).widget().setWordWrap(True); L.addWidget(f); L.addStretch(); s.timer = QTimer(s); s.timer.timeout.connect(s.tick); s.timer.start(2000); s.tick()
    def tick(s):
        m = s.ctx.mon.get(); g = m["gpu"]; f = lambda v, u="": "n/a" if v is None else f"{v:.0f}{u}"
        s.info.setText(f"<b>Adapters:</b> {', '.join(m['gpus']) or g['name']}<br><b>Active:</b> {g['name']} ({g['vendor']})<br><b>3D usage:</b> {f(g['usage'], '%')} &nbsp; <b>Temp:</b> {f(g['temp'], ' °C')}"
            f" &nbsp; <b>VRAM used:</b> {mb(g['vram_used'])}" + (f" / {mb(g['vram_total'])}" if g['vram_total'] else "") + f"<br><b>Clock:</b> {f(g['clock'], ' MHz')} &nbsp; <b>Power:</b> {f(g['power'], ' W')}<br><b>Source:</b> {g.get('source') or 'unavailable'}"
            + ("" if g["temp"] is not None else "<br><i>Temperature for this GPU needs LibreHardwareMonitor running (reads via WMI).</i>"))
        s.tips.setText(GPU_TIPS.get(g["vendor"], GPU_TIPS["Unknown"]))

class WinPage(QWidget):
    def __init__(s, ctx=None):
        super().__init__(); L = QVBoxLayout(s); L.addWidget(header("Windows Optimizer", "Startup apps, temp files, power plan, network"))
        f, l = card(); l.addWidget(QLabel("Startup apps (current user) — disabling is reversible")); s.lst = QListWidget(); s.lst.setObjectName("plain"); l.addWidget(s.lst); L.addWidget(f)
        b = QPushButton("Enable / disable selected"); b.clicked.connect(s.toggle); l.addWidget(b)
        f2, l2 = card(); s.tl = QLabel("Temp files: not scanned."); l2.addWidget(s.tl); r = QHBoxLayout()
        for txt, fn in (("Scan temp files (older than 24h)", s.scan), ("Delete scanned files", s.clean), ("High Performance power plan", s.plan), ("Flush DNS", s.dns)):
            x = QPushButton(txt); x.clicked.connect(fn); r.addWidget(x)
        l2.addLayout(r); L.addWidget(f2); s.files = []; s.load()
    def load(s):
        s.items = core.startup_items(); s.lst.clear()
        for it in s.items: s.lst.addItem(f"{'ON ' if it['enabled'] else 'OFF'}  {it['name']}  —  {it['cmd'][:80]}")
        if not s.items: s.lst.addItem("No startup entries found (or not on Windows).")
    def toggle(s):
        i = s.lst.currentRow()
        if 0 <= i < len(s.items): it = s.items[i]; core.set_startup(it["name"], not it["enabled"]); s.load()
    def scan(s): s.files, n = core.temp_scan(); s.tl.setText(f"{len(s.files)} files, {n/2**20:.1f} MB can be removed.")
    def clean(s):
        if s.files and QMessageBox.question(s, "Confirm", f"Permanently delete {len(s.files)} temp files? (cannot be restored)") == QMessageBox.Yes:
            s.tl.setText(f"Freed {core.temp_clean(s.files)/2**20:.1f} MB (files in use were skipped)."); s.files = []
    def plan(s): msg(s, "Power plan", "Switched." if core.set_plan(core.HIGH_PERF) else "Could not switch (Windows only / plan unavailable). Gaming Mode restores the original plan automatically.")
    def dns(s): msg(s, "DNS", "Flushed." if core.IS_WIN and core.run(["ipconfig", "/flushdns"]).returncode == 0 else "Failed / Windows only.")

class GamingPage(QWidget):
    def __init__(s, ctx):
        super().__init__(); s.ctx = ctx; L = QVBoxLayout(s); L.addWidget(header("Gaming Mode", "Game detection · power plan · priority · optional app closing"))
        f, l = card(); l.addWidget(QLabel("Detected games")); s.dt = QTableWidget(0, 3); s.dt.setHorizontalHeaderLabels(["Game", "PID", "Why detected"]); s.dt.horizontalHeader().setStretchLastSection(True)
        s.dt.setColumnWidth(0, 260); s.dt.setMaximumHeight(150); l.addWidget(s.dt); s.auto = QCheckBox("Auto Gaming Mode: enable when a game is detected, restore when it closes (never closes apps)")
        s.auto.setChecked(core.settings()["auto_gaming"]); s.auto.stateChanged.connect(lambda *_: core.save_settings(auto_gaming=s.auto.isChecked())); l.addWidget(s.auto); L.addWidget(f)
        f, l = card(); s.game = QComboBox(); l.addWidget(QLabel("Target game (gets raised CPU priority):")); l.addWidget(s.game)
        l.addWidget(QLabel("Optionally close these background apps (not reopened afterwards):")); s.bg = QListWidget(); s.bg.setObjectName("plain"); l.addWidget(s.bg); L.addWidget(f, 1)
        r = QHBoxLayout(); s.btn = QPushButton(); s.btn.setObjectName("boost"); s.btn.clicked.connect(s.toggle); gp = QPushButton("Use high-performance GPU for target"); gp.clicked.connect(s.gpu)
        rf = QPushButton("Refresh lists"); rf.clicked.connect(s.load); r.addWidget(s.btn, 2); r.addWidget(gp, 1); r.addWidget(rf); L.addLayout(r)
        s.rows = []; s.load(); s.timer = QTimer(s); s.timer.timeout.connect(s.tick); s.timer.start(3000)
    def tick(s):
        g = s.ctx.games; s.dt.setRowCount(len(g))
        for i, x in enumerate(g):
            for j, v in enumerate((("▶ " if x["fg"] else "") + x["name"], x["pid"], x["reason"])): s.dt.setItem(i, j, QTableWidgetItem(str(v)))
        s.upd()
    def load(s):
        s.rows = core.processes("ram", 60); s.game.clear(); s.bg.clear(); det = {g["pid"] for g in s.ctx.games}
        for g in s.ctx.games: s.game.addItem(f"★ {g['name']} ({g['pid']})", g["pid"])
        for r in s.rows:
            if r["pid"] not in det: s.game.addItem(f"{r['name']} ({r['pid']})", r["pid"])
            if r["closable"]: it = QListWidgetItem(f"{r['name']} ({r['ram']:.0f} MB)"); it.setFlags(it.flags() | Qt.ItemIsUserCheckable); it.setCheckState(Qt.Unchecked); it.setData(Qt.UserRole, r["pid"]); s.bg.addItem(it)
        s.tick()
    def upd(s): s.btn.setText("DISABLE GAMING MODE" if core.gaming_active() else "ENABLE GAMING MODE")
    def toggle(s):
        if core.gaming_active(): core.gaming_off()
        else:
            pids = [s.bg.item(i).data(Qt.UserRole) for i in range(s.bg.count()) if s.bg.item(i).checkState() == Qt.Checked]
            if pids and QMessageBox.question(s, "Confirm", f"Close {len(pids)} selected app(s)? Unsaved work in them may be lost.") != QMessageBox.Yes: return
            core.gaming_on(s.game.currentData(), pids)
        s.upd()
    def gpu(s):
        pid = s.game.currentData()
        try: exe = psutil.Process(pid).exe(); core.set_gpu_pref(exe); msg(s, "GPU preference", f"High-performance GPU set for:\n{exe}\n\nUndo with Settings → Restore all defaults.")
        except Exception as e: QMessageBox.warning(s, "Failed", str(e))

class SettingsPage(QWidget):
    def __init__(s, ctx=None):
        super().__init__(); L = QVBoxLayout(s); L.addWidget(header("Settings", "Backups, restore, data locations"))
        f, l = card(); a = QPushButton("Restore ALL defaults (tweaks, GPU preferences, Gaming Mode)"); a.setObjectName("danger"); a.clicked.connect(s.rd)
        b = QPushButton("Open backup folder"); b.clicked.connect(lambda: os.startfile(core.BACKUPS) if core.IS_WIN else None); l.addWidget(a); l.addWidget(b)
        ra = QPushButton("Restart as administrator"); ra.setEnabled(not core.is_admin()); ra.clicked.connect(lambda: core.relaunch_admin() and QApplication.quit()); l.addWidget(ra)
        l.addWidget(QLabel(f"Data folder: {core.DATA}\nAdministrator: {core.is_admin()} (needed for PresentMon and HKLM tweaks)")); L.addWidget(f); L.addStretch()
    def rd(s): core.gaming_off(); n = core.restore_tweaks(); msg(s, "Restored", f"Restored {n} setting group(s) and Gaming Mode.")

class Main(QMainWindow):
    def __init__(s):
        super().__init__(); s.setWindowTitle("FPS BOOSTER PRO"); s.resize(1280, 800); s.setWindowIcon(QIcon(res("assets/icon.ico"))); s.ctx = Ctx()
        w = QWidget(); w.setObjectName("bg"); s.setCentralWidget(w); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        side = QFrame(); side.setObjectName("side"); side.setFixedWidth(240); sl = QVBoxLayout(side); sl.setContentsMargins(0, 18, 0, 12)
        lg = QHBoxLayout(); lg.setContentsMargins(18, 0, 0, 10); ic = QLabel(); ic.setPixmap(QPixmap(res("assets/icon.png")).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        tl = QLabel("FPS BOOSTER\nPRO"); tl.setStyleSheet("font-weight:bold;font-size:14px;letter-spacing:2px"); lg.addWidget(ic); lg.addWidget(tl); lg.addStretch(); sl.addLayout(lg)
        P = [("◈  Dashboard", Dashboard), ("⚡  FPS Booster", FPSPage), ("📈  FPS Monitor", FPSMonitorPage), ("⇄  Compare", ComparePage), ("▤  RAM Optimizer", lambda c: ProcPage("RAM Optimizer", "ram")),
             ("◉  CPU Optimizer", lambda c: ProcPage("CPU Optimizer", "cpu")), ("▣  GPU Optimizer", GPUPage), ("⊞  Windows Optimizer", WinPage), ("🎮  Gaming Mode", GamingPage), ("⚙  Settings", SettingsPage)]
        s.stack = FadeStack(); nav = QListWidget(); nav.setObjectName("nav")
        s.pages, s.nav = [], nav
        for n, cls in P: nav.addItem(n); w_ = cls(s.ctx); s.pages.append(w_); s.stack.addWidget(w_)
        nav.currentRowChanged.connect(s.stack.fade_to); nav.setCurrentRow(0); sl.addWidget(nav, 1)
        s.stat = QLabel(); s.stat.setObjectName("muted"); s.stat.setContentsMargins(18, 0, 0, 0); sl.addWidget(s.stat)
        h.addWidget(side); body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(26, 22, 26, 18); bl.addWidget(s.stack); h.addWidget(body, 1)
        s.timer = QTimer(s); s.timer.timeout.connect(s.auto_tick); s.timer.start(3000); s.auto_tick()
    def auto_tick(s):
        try:
            st = core.gaming_state()
            if core.settings()["auto_gaming"]:
                if not st and s.ctx.games: core.gaming_on(s.ctx.games[0]["pid"], (), auto=True)
                elif st and st.get("auto") and st.get("pid") and not psutil.pid_exists(st["pid"]): core.gaming_off()
            s.stat.setText(("● Gaming Mode ACTIVE" if core.gaming_active() else "○ Gaming Mode off") + ("\n● Admin" if core.is_admin() else "\n○ Not elevated"))
        except Exception: pass
    def closeEvent(s, e):
        if s.ctx.cap: s.ctx.cap.stop()
        s.ctx._stop = True; s.ctx.mon.stop(); e.accept()

_in_hook = False
def _log(txt):
    try: open(os.path.join(core.DATA, "crash.log"), "a", encoding="utf-8").write(time.strftime("[%Y-%m-%d %H:%M:%S]\n") + txt + "\n")
    except Exception: pass
def _native_box(text):
    try: ctypes.windll.user32.MessageBoxW(0, text, "FPS BOOSTER PRO", 0x10)
    except Exception: pass
def _crash(et, ev, tb):
    global _in_hook
    _log("".join(traceback.format_exception(et, ev, tb)))
    if _in_hook: return
    _in_hook = True
    try: QMessageBox.critical(None, "FPS BOOSTER PRO", f"An unexpected error occurred. The app keeps running.\n\n{ev}\n\nDetails were saved to:\n{os.path.join(core.DATA, 'crash.log')}")
    except Exception: pass
    _in_hook = False

def selftest(out=None):
    """Starts the real UI, visits every page, saves screenshots and checks bundled resources. Used by CI against the frozen EXE."""
    out = out or os.path.join(core.DATA, "selftest"); os.makedirs(out, exist_ok=True); rf = os.path.join(out, "result.txt")
    def pump(sec, a):
        t0 = time.time()
        while time.time() - t0 < sec: a.processEvents(); time.sleep(0.05)
    try:
        import PySide6
        a = QApplication.instance() or QApplication(sys.argv); a.setStyleSheet(QSS); m = Main(); m.show(); pump(2.5, a)
        for i in range(len(m.pages)): m.nav.setCurrentRow(i); pump(0.5, a); m.grab().save(os.path.join(out, f"{i:02d}.png"))
        d = m.ctx.mon.get()
        checks = {"icon files bundled": os.path.exists(res("assets/icon.png")) and os.path.exists(res("assets/icon.ico")), "monitor delivers data": d["ram_total"] > 0 and d["procs"] > 0, "10 pages": len(m.pages) == 10}
        bad = [k for k, v in checks.items() if not v]
        if bad: raise RuntimeError("failed checks: " + ", ".join(bad))
        open(rf, "w").write(f"OK\nPySide6 {getattr(PySide6, '__version__', '?')}\nplatform {a.platformName()}\nfrozen {getattr(sys, 'frozen', False)}\n"); m.close(); return True
    except Exception:
        open(rf, "w").write("FAIL\n" + traceback.format_exc()); return False

if __name__ == "__main__":
    sys.excepthook = _crash; threading.excepthook = lambda a: _log("".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest"); sys.exit(0 if selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else None) else 1)
    try:
        a = QApplication(sys.argv); a.setApplicationName("FPS BOOSTER PRO"); a.setStyleSheet(QSS); m = Main(); m.show(); sys.exit(a.exec())
    except Exception:
        _log(traceback.format_exc()); _native_box("FPS BOOSTER PRO could not start.\n\n" + traceback.format_exc()[-600:] + f"\nLog: {os.path.join(core.DATA, 'crash.log')}"); sys.exit(1)
