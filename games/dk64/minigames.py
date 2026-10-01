"""DK Arcade and Jetpac sprites. They are pixel arrays inside the two overlays' data
segments (not in the asset tables), so they are regenerated here.

Dirty side: facts(rom, pristine) -> json-able spec (offsets, stride, 4x4 colour grid, outline).
Clean side: apply(rom bytearray, spec) rewrites both data segments in place (gzip, same ROM slot).

Arcade: RGBA16 sprites -> flat blocks of the grid colours inside the kept 1-bit alpha outline.
Jetpac: two-level 8-bit sprites -> the filled, smoothed silhouette of the outline (interior detail dropped).
"""
import re
import zlib

import numpy as np

from cleanroom.decomp import spec as cspec
from cleanroom.gfx import texfmt

from .romtables import gz

# (name, code gzip offset, data gzip offset, slot end)
ARCADE = ("arcade", 0xF41A0, 0xFB42C, 0xFD2F0)
JETPAC = ("jetpac", 0xFD2F0, 0x1010FD, 0x101A40)
VRAM = 0x80024000
END = bytes.fromhex("df00000000000000")
ARCADE_W = {576: 16, 512: 16, 4032: 48, 2944: 46, 1640: 43, 1744: 16, 800: 20, 480: 24, 384: 24,
            160: 4, 144: 8, 128: 8, 64: 8, 32: 4}


def blobs(rom, ov):
    code = zlib.decompressobj(31).decompress(rom[ov[1]:ov[1] + 0x100000])
    data = zlib.decompressobj(31).decompress(rom[ov[2]:ov[2] + 0x100000])
    return code, data


def facts(rom, pristine):
    out = {"arcade": [], "jetpac": []}
    code, data = blobs(rom, ARCADE)
    base = VRAM + len(code)
    src = open(pristine + "/src/arcade/code_0.c").read()
    syms = sorted({int(x, 16) for x in re.findall(r"D_arcade_([0-9A-F]{8})", src) if base <= int(x, 16) < base + len(data)})
    u32s = [int(m.group(1), 16) for m in re.finditer(r"^u32 D_arcade_([0-9A-F]{8})\[", src, re.M)]
    for a in u32s:
        nxt = min([b for b in syms if b > a] + [base + len(data)])
        blob = data[a - base:nxt - base]
        if blob.endswith(END):
            blob = blob[:-8]
        L = len(blob)
        if L < 16 or L not in ARCADE_W:
            continue
        w = ARCADE_W[L]
        h = L // 2 // w
        img = texfmt.decode(blob, w, h, 0, 2)
        out["arcade"].append({"off": a - base, "len": L, "w": w, "h": h,
                              "grid": cspec.grid(img.astype(np.float32), 4), "alpha2": cspec.alpha2(img[..., 3])})
    code, data = blobs(rom, JETPAC)
    base = VRAM + len(code)
    tg = set()
    recs = {}
    for o in range(0, len(data) - 12, 4):
        v = int.from_bytes(data[o:o + 4], "big")
        if base <= v < base + len(data):
            tg.add(v)
            recs.setdefault(v, int.from_bytes(data[o + 8:o + 10], "big"))
    order = sorted(tg) + [base + len(data)]
    for v, nxt in zip(order, order[1:]):
        blob = data[v - base:nxt - base]
        # the sprite is the leading run of 00/FF bytes
        n = 0
        while n < len(blob) and blob[n] in (0, 255):
            n += 1
        stride = recs[v] if recs[v] in (8, 16, 24, 32) else 16
        n = n // stride * stride
        if n < stride * 4 or blob[:n].count(255) == 0:
            continue
        a = np.frombuffer(blob[:n], np.uint8).reshape(-1, stride)
        out["jetpac"].append({"off": v - base, "len": n, "w": stride, "h": a.shape[0], "alpha2": cspec.alpha2(a)})
    return out


def silhouette(a):
    """a: (h, w) bool. Fill enclosed holes, then a 3x3 majority smooth."""
    h, w = a.shape
    out = np.pad(~a, 1, constant_values=True)
    seen = np.zeros_like(out)
    stack = [(0, 0)]
    while stack:
        y, x = stack.pop()
        if y < 0 or x < 0 or y >= h + 2 or x >= w + 2 or seen[y, x] or not out[y, x]:
            continue
        seen[y, x] = True
        stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    filled = ~seen[1:-1, 1:-1]
    p = np.pad(filled.astype(np.int32), 1)
    cnt = sum(p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3))
    return cnt >= 5


def _alpha(hexs, w, h):
    b = np.frombuffer(bytes.fromhex(hexs), np.uint8)
    a = np.empty(len(b) * 4, np.uint8)
    a[0::4], a[1::4], a[2::4], a[3::4] = b >> 6, (b >> 4) & 3, (b >> 2) & 3, b & 3
    return a[:w * h].reshape(h, w) >= 2


def _put_data(rom, ov, data):
    code_gz_end = ov[2]
    new = gz(bytes(data))
    assert code_gz_end + len(new) <= ov[3], "%s data grew: %d > %d" % (ov[0], len(new), ov[3] - code_gz_end)
    rom[code_gz_end:ov[3]] = new + bytes(ov[3] - code_gz_end - len(new))
    return len(new), ov[3] - code_gz_end


def apply(rom, spec):
    _, data = blobs(bytes(rom), ARCADE)
    data = bytearray(data)
    for r in spec["arcade"]:
        w, h = r["w"], r["h"]
        g = np.asarray(r["grid"], np.float32).reshape(4, 4, 4)
        img = g[np.arange(h) * 4 // h][:, np.arange(w) * 4 // w].copy()      # flat blocks: pixel-art look
        a = _alpha(r["alpha2"], w, h)
        # block colour should be the colour of its opaque texels
        img[..., :3] = np.clip(img[..., :3] * 255.0 / np.maximum(img[..., 3:4], 40), 0, 255)
        img[..., :3] = np.round(img[..., :3] / 36) * 36
        img[..., 3] = a * 255
        img[~a, :3] = 0
        b = texfmt.encode(np.clip(img, 0, 255).astype(np.uint8), 0, 2)
        data[r["off"]:r["off"] + len(b)] = b
    s1 = _put_data(rom, ARCADE, data)
    _, data = blobs(bytes(rom), JETPAC)
    data = bytearray(data)
    for r in spec["jetpac"]:
        s = silhouette(_alpha(r["alpha2"], r["w"], r["h"]))
        data[r["off"]:r["off"] + r["len"]] = (s * 255).astype(np.uint8).tobytes()
    s2 = _put_data(rom, JETPAC, data)
    print("minigames: arcade %d sprites (data %d/%d B), jetpac %d sprites (data %d/%d B)"
          % (len(spec["arcade"]), s1[0], s1[1], len(spec["jetpac"]), s2[0], s2[1]))


def n64_crc(rom):
    """Header checksum (CIC-6105) over 1 MB from 0x1000."""
    M = 0xFFFFFFFF
    d = np.frombuffer(bytes(rom[0x1000:0x101000]), ">u4").tolist()
    key = np.frombuffer(bytes(rom[0x750:0x850]), ">u4").tolist()
    t1 = t2 = t3 = t4 = t5 = t6 = 0xDF26F436
    for i, v in enumerate(d):
        s = (t6 + v) & M
        if s < t6:
            t4 = (t4 + 1) & M
        t6 = s
        t3 ^= v
        k = v & 31
        r = ((v << k) | (v >> (32 - k))) & M
        t5 = (t5 + r) & M
        t2 ^= r if t2 > v else (t6 ^ v)
        t1 = (t1 + (key[i & 0x3F] ^ v)) & M
    return t6 ^ t4 ^ t3, t5 ^ t2 ^ t1
