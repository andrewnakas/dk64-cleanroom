"""Dirty room: find each texture's format/size from the display lists that use it.

DK64 display lists (map/prop/actor geometry) name a texture by its index in
pointer table 25 in G_SETTIMG; the following SETTILE / LOADBLOCK / LOADTLUT /
SETTILESIZE give format, texel size, dimensions and (for CI) the palette file.
"""
import collections
import struct

import numpy as np

GEO_TABLES = (1, 4, 5)


def scan_file(d, uses, pals, maxidx=8192):
    n = len(d) // 8
    w = np.frombuffer(d[:n * 8], ">u4").reshape(-1, 2)
    op = w[:, 0] >> 24
    cand = np.nonzero((op == 0xFD) & ((w[:, 0] & 0x0007FFFF) == 0) & (w[:, 1] < maxidx))[0]
    tile0 = None      # (fmt, siz, line)
    cur_pal = None
    for ci, j in enumerate(cand):
        idx = int(w[j, 1])
        end = cand[ci + 1] if ci + 1 < len(cand) else n
        end = min(end, j + 14)
        texels = None; size = None; is_tlut = False; t0 = None; lt = None
        for k in range(j + 1, end):
            a = int(w[k, 0]); b = int(w[k, 1]); o = a >> 24
            if o == 0xF5:
                tile = (b >> 24) & 7
                st = ((a >> 21) & 7, (a >> 19) & 3, (a >> 9) & 0x1FF, (b >> 20) & 0xF)
                if tile == 0:
                    t0 = st
                elif tile == 7:
                    lt = st
            elif o == 0xF3:
                texels = ((b >> 12) & 0xFFF) + 1
            elif o == 0xF0:
                is_tlut = True
                texels = ((b >> 14) & 0x3FF) + 1
            elif o == 0xF2:
                if ((b >> 24) & 7) == 0 and size is None:
                    size = (((b >> 12) & 0xFFF) >> 2) + 1, ((b & 0xFFF) >> 2) + 1
            elif o in (0xE6, 0xE7, 0xE8, 0xFC, 0xE3, 0xE2, 0xD7, 0xD9, 0xFA, 0xFB, 0xDA, 0x01):
                continue
            else:
                break
        if is_tlut:
            pals[idx][texels] += 1
            cur_pal = idx
            continue
        if texels is None:
            continue
        if t0 is not None:
            tile0 = t0
        t = t0 or tile0
        if t is None:
            # fall back to the SETTIMG's own fmt/siz
            t = ((int(w[j, 0]) >> 21) & 7, (int(w[j, 0]) >> 19) & 3, 0, 0)
        fmt, siz, line, _ = t
        bpp = 4 << siz
        if lt is not None and lt[1] != siz:
            # loaded as 16-bit words but rendered as siz: texel count is in load units
            texels = texels * (4 << lt[1]) // bpp
        if size is None:
            if not line:
                continue
            wd = line * 64 // bpp
            size = (wd, max(1, texels // wd))
        uses[idx][(fmt, siz, size[0], size[1], cur_pal if fmt == 2 else None)] += 1


def scan(T):
    uses = collections.defaultdict(collections.Counter)
    pals = collections.defaultdict(collections.Counter)
    for t in GEO_TABLES:
        for i, d, g in T.files(t):
            scan_file(d, uses, pals)
    return uses, pals


if __name__ == "__main__":
    import sys
    from .romtables import Tables
    T = Tables(open(sys.argv[1], "rb").read())
    uses, pals = scan(T)
    files = {i: len(d) for i, d, g in T.files(25)}
    ok = bad = 0; badl = []
    fm = collections.Counter()
    for i, c in uses.items():
        if i not in files:
            continue
        (fmt, siz, w, h, p), _ = c.most_common(1)[0]
        need = w * h * (4 << siz) // 8
        fm[(fmt, siz)] += 1
        if need <= files[i]:
            ok += 1
        else:
            bad += 1; badl.append((i, files[i], fmt, siz, w, h))
    npal = sum(1 for i in pals if i in files)
    rest = [i for i in files if i not in uses and i not in pals]
    print("table25 files", len(files), "with DL use", ok, "size mismatch", bad, "palettes", npal, "unreferenced", len(rest))
    print("formats", sorted(fm.items()))
    print("mismatch sample", badl[:8])
    print("unreferenced sizes", collections.Counter(files[i] for i in rest).most_common(12))
    print("unreferenced idx ranges", rest[:10], rest[-10:])
    multi = sum(1 for i, c in uses.items() if len(c) > 1)
    print("textures with >1 interpretation", multi)
