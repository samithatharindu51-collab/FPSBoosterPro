"""Generates the application icon (lightning bolt in a neon rounded tile) with no dependencies beyond the stdlib."""
import os, struct, zlib
BOLT = [(.58, .17), (.32, .54), (.48, .54), (.42, .85), (.69, .45), (.53, .45)]
def _in_poly(x, y):
    c = False
    for i in range(len(BOLT)):
        (x1, y1), (x2, y2) = BOLT[i], BOLT[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c
def _rr(x, y, half, rad):
    qx, qy = abs(x - .5) - (half - rad), abs(y - .5) - (half - rad)
    return (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** .5 + min(max(qx, qy), 0) - rad
def _lerp(a, b, t): return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
def _shade(u, v):
    if _rr(u, v, .48, .22) > 0: return (0, 0, 0, 0)
    t = (u + v) / 2
    if _in_poly(u, v): return (*_lerp((120, 215, 255), (190, 120, 255), t), 255)
    if _rr(u, v, .40, .17) < 0: return (*_lerp((16, 16, 28), (10, 10, 18), t), 255)
    return (*_lerp((45, 107, 255), (138, 61, 255), t), 255)
def render(size):
    ss = 3 if size <= 64 else 2; px = bytearray()
    for y in range(size):
        px.append(0)
        for x in range(size):
            r = g = b = a = 0
            for j in range(ss):
                for i in range(ss):
                    c = _shade((x + (i + .5) / ss) / size, (y + (j + .5) / ss) / size); r += c[0] * c[3]; g += c[1] * c[3]; b += c[2] * c[3]; a += c[3]
            n = ss * ss
            px += bytes((int(r / a), int(g / a), int(b / a), a // n)) if a else bytes(4)
    def ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + ch(b"IDAT", zlib.compress(bytes(px), 9)) + ch(b"IEND", b"")
def make(folder):
    os.makedirs(folder, exist_ok=True); sizes = (256, 128, 64, 48, 32, 16); pngs = [render(s) for s in sizes]
    open(os.path.join(folder, "icon.png"), "wb").write(pngs[0])
    ico = struct.pack("<HHH", 0, 1, len(sizes)); off = 6 + 16 * len(sizes); body = b""
    for s, p in zip(sizes, pngs):
        ico += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(p), off + len(body)); body += p
    open(os.path.join(folder, "icon.ico"), "wb").write(ico + body)
if __name__ == "__main__": make(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
