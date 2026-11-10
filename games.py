"""Game detection: known list, launcher library folders, or foreground app using DX12/Vulkan."""
import ctypes, os, sys, psutil
IS_WIN = sys.platform == "win32"
KNOWN = {n.lower() for n in """cs2.exe csgo.exe valorant-win64-shipping.exe fortniteclient-win64-shipping.exe gta5.exe gta5_enhanced.exe
eldenring.exe nightreign.exe cyberpunk2077.exe witcher3.exe rdr2.exe r5apex.exe apexlegends.exe dota2.exe league of legends.exe
robloxplayerbeta.exe rocketleague.exe destiny2.exe bf2042.exe bf1.exe cod.exe modernwarfare.exe hogwartslegacy.exe bg3.exe bg3_dx11.exe
helldivers2.exe palworld-win64-shipping.exe tslgame.exe rainbowsix.exe rainbowsix_vulkan.exe wow.exe ffxiv_dx11.exe overwatch.exe
marvel-win64-shipping.exe deadlock.exe starfield.exe baldursgate3.exe minecraft.windows.exe terraria.exe stardewvalley.exe
fallguys_client_game.exe thefinals.exe wwm.exe sekiro.exe darksouls3.exe monsterhunterwilds.exe forzahorizon5.exe rustclient.exe
dayz_x64.exe arma3_x64.exe pathofexile.exe pathofexile_x64.exe diablo iv.exe diabloiv.exe lostark.exe tarkov.exe escapefromtarkov.exe""".split("\n") for n in n.split()}
LIB_HINTS = ("\\steamapps\\common\\", "\\epic games\\", "\\gog galaxy\\games\\", "\\riot games\\", "\\ubisoft game launcher\\games\\",
             "\\ea games\\", "\\origin games\\", "\\xboxgames\\")
SKIP_WORDS = ("launcher", "crash", "helper", "setup", "unins", "anticheat", "redist", "eac", "service", "bootstrap", "webhelper", "installer")
EXCLUDE = {"steam.exe", "steamwebhelper.exe", "chrome.exe", "msedge.exe", "firefox.exe", "discord.exe", "explorer.exe", "python.exe",
           "pythonw.exe", "code.exe", "obs64.exe", "teams.exe", "fpsboosterpro.exe", "epicgameslauncher.exe", "battle.net.exe"}
GFX = {"d3d12.dll", "vulkan-1.dll"}

def classify(name, exe, fg=False, modules=()):
    """Return the reason this process looks like a game, or None. Pure function (unit-tested)."""
    n = (name or "").lower(); e = (exe or "").lower().replace("/", "\\")
    if n in EXCLUDE: return None
    if n in KNOWN: return "Known game"
    if any(h in e for h in LIB_HINTS) and not any(w in n for w in SKIP_WORDS): return "Installed in a game library folder"
    if fg and GFX & {m.lower() for m in modules} and "\\windows\\" not in e and not any(w in n for w in SKIP_WORDS):
        return "Foreground app using DirectX 12 / Vulkan"
    return None

def foreground_pid():
    if not IS_WIN: return None
    try:
        pid = ctypes.c_ulong(); ctypes.windll.user32.GetWindowThreadProcessId(ctypes.windll.user32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value
    except Exception: return None

def detect():
    fg, out = foreground_pid(), []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            i = p.info
            if not i["name"]: continue
            reason = classify(i["name"], i["exe"])
            if not reason and fg and i["pid"] == fg:
                reason = classify(i["name"], i["exe"], True, [os.path.basename(m.path) for m in p.memory_maps()])
            if reason: out.append(dict(pid=i["pid"], name=i["name"], exe=i["exe"] or "", reason=reason, fg=i["pid"] == fg))
        except (psutil.Error, OSError): continue
    out.sort(key=lambda g: (not g["fg"], g["name"].lower()))
    return out
