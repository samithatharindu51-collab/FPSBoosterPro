"""PresentMon integration, frame-time statistics, saved sessions and before/after comparison.
Only real captured/imported frame times are ever used - nothing is estimated."""
import csv, json, os, shutil, statistics, subprocess, sys, time
from collections import deque
import core

SESS = os.path.join(core.DATA, "sessions"); os.makedirs(SESS, exist_ok=True)
COLS = ("msbetweenpresents", "frametime")  # PresentMon 1.x / 2.x column names (lower-cased)

def find_presentmon(custom=""):
    cands = [custom, os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "PresentMon.exe"), os.path.join(os.getcwd(), "PresentMon.exe"),
             r"C:\Program Files\Intel\PresentMon\PresentMon.exe", r"C:\Program Files\PresentMon\PresentMon.exe", shutil.which("PresentMon") or ""]
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    try: cands += [os.path.join(base, f) for f in os.listdir(base) if f.lower().startswith("presentmon") and f.lower().endswith(".exe")]
    except OSError: pass
    return next((c for c in cands if c and os.path.isfile(c)), None)

def _col(header):
    h = [x.strip().lower() for x in header]
    for c in COLS:
        if c in h: return h.index(c)
    return None

def parse_csv(path):
    """Frame times in ms from a PresentMon (or compatible) CSV. Pauses > 5 s are ignored."""
    out = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        r = csv.reader(f); idx = _col(next(r, []))
        if idx is None: raise ValueError("CSV has no MsBetweenPresents / FrameTime column")
        for row in r:
            try: v = float(row[idx])
            except (ValueError, IndexError): continue
            if 0 < v < 5000: out.append(v)
    return out

def _low(ms, frac):
    w = sorted(ms, reverse=True); k = max(1, int(len(w) * frac))
    return 1000.0 / (sum(w[:k]) / k)

def stats(ms):
    """avg FPS = frames / total time. 1% / 0.1% low = FPS of the mean of the slowest 1% / 0.1% frames."""
    if len(ms) < 2: raise ValueError("not enough frames")
    tot = sum(ms)
    return dict(frames=len(ms), duration=tot / 1000, avg_fps=1000 * len(ms) / tot, p1_low=_low(ms, .01), p01_low=_low(ms, .001),
                mean_ms=tot / len(ms), max_ms=max(ms), stdev_ms=statistics.pstdev(ms))

class Capture:
    """Runs PresentMon for one process and tails its CSV for live FPS."""
    def __init__(s, pm, proc_name, out_csv):
        s.pm, s.name, s.csv, s.proc, s.pos, s.idx, s.buf = pm, proc_name, out_csv, None, 0, None, ""
        s.recent, s.live_fps, s.frames, s.t0, s.err = deque(maxlen=600), None, 0, time.time(), ""
    @property
    def running(s): return s.proc is not None and s.proc.poll() is None
    def variants(s):
        return [[s.pm, "--process_name", s.name, "--output_file", s.csv, "--stop_existing_session", "--session_name", "FPSBoosterPro", "--no_console_stats"],
                [s.pm, "-process_name", s.name, "-output_file", s.csv, "-stop_existing_session"]]
    def start(s):
        log = s.csv + ".log"
        for args in s.variants():
            try:
                if os.path.exists(s.csv): os.remove(s.csv)
                with open(log, "w") as lf: s.proc = subprocess.Popen(args, stdout=lf, stderr=subprocess.STDOUT, creationflags=core.NOWIN)
                time.sleep(1.5)
                if s.proc.poll() is None: s.t0 = time.time(); return True, "capturing"
            except OSError as e: s.err = str(e); continue
        try: s.err = open(log).read().strip()[-400:] or s.err
        except OSError: pass
        return False, s.err or "PresentMon exited immediately (administrator rights are required)"
    def poll(s):
        if not os.path.exists(s.csv): return s.live_fps
        with open(s.csv, "r", newline="", encoding="utf-8-sig", errors="replace") as f:
            f.seek(s.pos); chunk = f.read(); s.pos = f.tell()
        s.buf += chunk; *lines, s.buf = s.buf.split("\n")
        for line in lines:
            row = next(csv.reader([line]), [])
            if s.idx is None: s.idx = _col(row); continue
            try: v = float(row[s.idx])
            except (ValueError, IndexError, TypeError): continue
            if 0 < v < 5000: s.recent.append(v); s.frames += 1
        t, n = 0.0, 0
        for v in reversed(s.recent):
            t += v; n += 1
            if t >= 1000: break
        if n and t > 0: s.live_fps = 1000 * n / t
        return s.live_fps
    def stop(s):
        if s.proc and s.proc.poll() is None:
            s.proc.terminate()
            try: s.proc.wait(5)
            except subprocess.TimeoutExpired: s.proc.kill()
        return parse_csv(s.csv) if os.path.exists(s.csv) else []

def save_session(label, game, ms, csv_src=None, source="presentmon", note=""):
    sid = time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
    while os.path.exists(os.path.join(SESS, sid + ".json")): sid += "x"
    st = stats(ms); keep = os.path.join(SESS, sid + ".csv")
    if csv_src and os.path.exists(csv_src): shutil.copy(csv_src, keep)
    d = dict(id=sid, label=label, game=game, note=note, time=time.strftime("%Y-%m-%d %H:%M"), stats=st, source=source, csv=keep,
             tweaks=sorted(k for k in core._load()["tweaks"] if not k.startswith("gpupref:")), gaming_mode=core.gaming_active())
    json.dump(d, open(os.path.join(SESS, sid + ".json"), "w"), indent=1); return d

def list_sessions():
    out = []
    for f in os.listdir(SESS):
        if f.endswith(".json"):
            try: out.append(json.load(open(os.path.join(SESS, f))))
            except Exception: pass
    return sorted(out, key=lambda d: d["id"], reverse=True)

def delete_session(sid):
    for ext in (".json", ".csv", ".csv.log"):
        try: os.remove(os.path.join(SESS, sid + ext))
        except OSError: pass

def title(d): return f"[{d['label']}] {d['game']} · {d['time']} · {d['stats']['avg_fps']:.0f} FPS avg"

METRICS = [("Average FPS", "avg_fps", True), ("1% low FPS", "p1_low", True), ("0.1% low FPS", "p01_low", True),
           ("Mean frame time (ms)", "mean_ms", False), ("Worst frame (ms)", "max_ms", False), ("Frame-time stdev (ms)", "stdev_ms", False)]

def compare(a, b):
    """Rows: (metric, A, B, delta, delta%, improved?) plus warnings about how trustworthy the comparison is."""
    rows = []
    for name, k, hi in METRICS:
        x, y = a["stats"][k], b["stats"][k]; d = y - x
        rows.append((name, x, y, d, (d / x * 100) if x else 0.0, (d > 0) == hi if d else None))
    w = []
    if a["game"].lower() != b["game"].lower(): w.append("The two captures are from different games/processes.")
    if min(a["stats"]["duration"], b["stats"]["duration"]) < 30: w.append("A capture is shorter than 30 s; results will be noisy.")
    if min(a["stats"]["frames"], b["stats"]["frames"]) < 1000: w.append("Fewer than 1000 frames in a capture; 1% / 0.1% lows are unreliable.")
    w.append("Run-to-run variance is typically 1-3% even with no changes: repeat the same scene several times before attributing a difference to a tweak.")
    return rows, w
