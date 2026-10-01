"""Dirty room: guess format/size of textures no display list or sprite record names.

Candidates are every (fmt, siz, w, h) whose byte size fits the file; the score
is neighbour smoothness of the decoded image relative to its contrast (a wrong
width or texel size shreds rows, which raises it).
"""
import numpy as np

from cleanroom.gfx import texfmt

RGBA, CI, IA, I = 0, 2, 3, 4
WIDTHS = [8, 16, 24, 32, 40, 44, 48, 56, 60, 63, 64, 72, 76, 80, 96, 104, 108, 112, 120, 128, 160, 192, 256, 320]
FORMATS = [(RGBA, 2), (RGBA, 3), (IA, 2), (IA, 1), (I, 1), (IA, 0), (I, 0)]


def mip_len(w, h, siz, levels, align):
    """Byte size of a mip chain; rows padded to `align` bytes."""
    tot = 0
    out = []
    for k in range(levels):
        wk, hk = max(1, w >> k), max(1, h >> k)
        row = (wk * (4 << siz) + 7) // 8
        row = (row + align - 1) // align * align
        out.append((wk, hk, row))
        tot += row * hk
    return tot, out


def layouts(L, w, h, siz):
    """Mip layouts (list of (w, h, rowbytes)) whose total is exactly L."""
    base = w * h * (4 << siz) // 8
    if base == L:
        return [(w, h, (w * (4 << siz) + 7) // 8)]
    if base > L:
        return None
    for align in (8, 4, 2, 1):
        for levels in range(2, 8):
            tot, lv = mip_len(w, h, siz, levels, align)
            if tot == L:
                return lv
            for pad in (8, 16):
                if (tot + pad - 1) // pad * pad == L:
                    return lv
    return None


def score(img):
    """Lower = more image-like. img: (h, w, 4) uint8."""
    x = img.astype(np.float32)
    if x.shape[0] < 2 or x.shape[1] < 2:
        return 9.0
    a = x[..., 3:4] / 255.0
    c = x[..., :3] * (a > 0.1)          # ignore colour under transparent texels
    v = np.concatenate([c, x[..., 3:4]], -1)
    sd = v.reshape(-1, 4).std(0).sum() + 1e-3
    if sd < 2.0:
        return 5.0                       # flat: no evidence
    dy = np.abs(v[1:] - v[:-1]).mean(0).mean(0).sum()
    dx = np.abs(v[:, 1:] - v[:, :-1]).mean(0).mean(0).sum()
    return float((dx + dy) / (2 * sd))


def candidates(L):
    out = []
    for fmt, siz in FORMATS:
        bpp = 4 << siz
        for w in WIDTHS:
            rb = w * bpp // 8
            if rb == 0 or rb > L:
                continue
            if L % rb == 0:
                h = L // rb
                if 4 <= h <= 320 and h * 6 >= w and w * 8 >= h:
                    out.append((fmt, siz, w, h))
            elif w in (16, 32, 64) and fmt == RGBA:
                for h in (w, w // 2, w * 2):
                    lv = layouts(L, w, h, siz)
                    if lv and len(lv) > 1 and isinstance(lv[0], tuple):
                        out.append((fmt, siz, w, h))
    return out


def guess(data):
    """-> (fmt, siz, w, h, score) or None."""
    best = None
    for fmt, siz, w, h in candidates(len(data)):
        n = w * h * (4 << siz) // 8
        try:
            img = texfmt.decode(data[:n], w, h, fmt, siz)
        except Exception:
            continue
        s = score(img)
        # mild priors: RGBA16 is by far the commonest; square-ish pow2 sizes
        if (fmt, siz) != (RGBA, 2):
            s *= 1.08
        if w & (w - 1) or h & (h - 1):
            s *= 1.05
        if best is None or s < best[4]:
            best = (fmt, siz, w, h, s)
    return best


if __name__ == "__main__":
    import sys, zlib, collections
    from .romtables import Tables
    from . import texscan
    rom = open(sys.argv[1], "rb").read()
    T = Tables(rom)
    uses, pals = texscan.scan(T)
    code = zlib.decompressobj(31).decompress(rom[0x113F0:0x113F0 + 0x200000])
    spr, _ = texscan.scan_sprites(T, code)
    known = {}
    for i, c in uses.items():
        known[(25, i)] = c.most_common(1)[0][0][:4]
    known.update(spr)
    files = {(t, i): d for t in (7, 25) for i, d, g in T.files(t)}
    res = collections.Counter(); wrong = collections.Counter()
    n = 0
    for k, (fmt, siz, w, h) in sorted(known.items()):
        if k not in files or fmt == CI:
            continue
        n += 1
        if n % 3:
            continue
        g = guess(files[k])
        if g is None:
            res["none"] += 1; continue
        if g[:2] == (fmt, siz) and g[2] == w:
            res["exact"] += 1
        elif g[:2] == (fmt, siz):
            res["fmt ok, size wrong"] += 1
        else:
            res["wrong"] += 1; wrong[((fmt, siz), g[:2])] += 1
    print(dict(res)); print(wrong.most_common(10))
