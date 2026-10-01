"""DIRTY ROOM. Reads the retail ROM and writes the kept facts (spec).

    python -m games.dk64.extract_spec <baserom.us.z64> <spec dir> [--no-audio]

Textures (pointer tables 7, 14, 25): format, size, 4x4 colour grid (16x16 for
128+ px images), 2-bit alpha outline, which palette file a CI texture uses.
Samples (two sound banks): length, loop points, coarse spectral outline, median pitch.
Nothing else leaves this script; code, geometry, text, music sequences and
demo inputs stay in the ROM image as kept facts (user scope).
"""
import collections
import gzip
import json
import os
import sys
import zlib

import numpy as np

from cleanroom.audio import albank, descriptor, vadpcm
from cleanroom.audio.pitch import median_f0
from cleanroom.decomp import spec as cspec
from cleanroom.gfx import texfmt

from . import lzss, texguess, texscan
from .romtables import Tables

CODE_GZ = 0x113F0
BANKS = (("A", 0x188AF20, 0x1897860, 0x1A97280), ("B", 0x1A97280, 0x1ABCBF0, 0x1FED020))
TEX_TABLES = (7, 14, 25)
RGBA, CI = 0, 2


def fact(rgba):
    h, w = rgba.shape[:2]
    n = 16 if max(w, h) >= 128 else 4
    d = {"grid": cspec.grid(rgba.astype(np.float32), n)}
    if (rgba[..., 3] < 250).any():
        d["alpha2"] = cspec.alpha2(rgba[..., 3])
    return d


def textures(rom, T):
    uses, pals = texscan.scan(T)
    code = zlib.decompressobj(31).decompress(rom[CODE_GZ:CODE_GZ + 0x200000])
    spr, _ = texscan.scan_sprites(T, code)
    files = {(t, i): d for t in TEX_TABLES for i, d, g in T.files(t)}
    out = []
    stats = collections.Counter()
    pal_used = set()
    for (t, i), d in sorted(files.items()):
        L = len(d)
        rec = {"t": t, "i": i, "len": L}
        interp = None
        if t == 25 and i in uses:
            # commonest interpretation; all palettes seen with it
            (fmt, siz, w, h, p), _ = uses[i].most_common(1)[0]
            rowb = max(1, w * (4 << siz) // 8)
            h = min(h, L // rowb)
            interp = (fmt, siz, w, h) if h >= 1 else None
            rec["src"] = "dl"
            if interp and fmt == CI:
                ps = [k[4] for k, _ in uses[i].most_common() if k[0] == CI and k[1] == siz and k[4] is not None
                      and (25, k[4]) in files and len(files[(25, k[4])]) >= 2 * (1 << (4 << siz))]
                ps = list(dict.fromkeys(ps))
                if not ps:
                    interp = None
                else:
                    rec["pals"] = ps
        if interp is None and (t, i) in spr:
            interp = spr[(t, i)]
            rec["src"] = "sprite"
            if interp[0] == CI:
                interp = (4, interp[1], interp[2], interp[3])
        if interp is None and t == 25 and i in pals:
            rec.update(kind="tlut", n=L // 2)
            rgba = texfmt.decode(d[:L // 2 * 2], L // 2, 1, RGBA, 2)
            rec["grid"] = cspec.grid(rgba.astype(np.float32).reshape(1, -1, 4).repeat(4, 0), 4)[:4]
            stats["tlut"] += 1
            out.append(rec)
            continue
        if interp is None:
            g = texguess.guess(d) if L >= 64 else None
            if g:
                interp = g[:4]
                rec["src"] = "guess"
        if interp is None:
            rec.update(kind="raw", mean=int(np.frombuffer(d, np.uint8).mean()) if L else 0)
            stats["raw"] += 1
            out.append(rec)
            continue
        fmt, siz, w, h = interp
        n0 = w * h * (4 << siz) // 8
        rec.update(kind="tex", fmt=fmt, siz=siz, w=w, h=h)
        stats[rec["src"]] += 1
        if fmt == CI:
            rec["variants"] = {}
            for p in rec["pals"]:
                pd = files[(25, p)]
                pal = texfmt.decode(pd[:len(pd) // 2 * 2], len(pd) // 2, 1, RGBA, 2).reshape(-1, 4)
                idx = texfmt.decode(d[:n0], w, h, CI, siz)[..., 0]
                rgba = pal[np.minimum(idx, len(pal) - 1)]
                rec["variants"][str(p)] = fact(rgba)
                pal_used.add(p)
        else:
            rec.update(fact(texfmt.decode(d[:n0], w, h, fmt, siz)))
        out.append(rec)
    print("textures:", len(out), dict(stats))
    return out


def samples(rom):
    out = []
    for name, ctl0, tbl0, tbl1 in BANKS:
        ctl, _ = lzss.decode(rom[ctl0:tbl0])
        bf = albank.parse_bankfile(ctl)
        b = bf["banks"][0]
        waves = {}
        for ins in [x for x in b["insts"] if x] + ([b["percussion"]] if b["percussion"] else []):
            for sd in ins["sounds"]:
                waves[sd["wave"]["_id"]] = sd["wave"]
        tbl = rom[tbl0:tbl1]
        for wid, w in sorted(waves.items(), key=lambda kv: kv[1]["base"]):
            nfr = w["len"] // 9 * 16
            pcm = vadpcm.decode(tbl[w["base"]:w["base"] + w["len"]], w["book"], nfr).astype(np.float64)
            d = {"bank": name, "wave": int(wid.split("@")[1], 16), "base": w["base"], "len": w["len"],
                 "nframes": nfr, "rate": b["rate"], "desc": descriptor.describe(pcm, b["rate"])}
            f0 = median_f0((pcm / 32768).astype(np.float32), b["rate"])
            if f0:
                d["f0"] = round(f0, 1)
            if w["loop"]:
                d["loop"] = [w["loop"]["start"], w["loop"]["end"], w["loop"]["count"]]
            out.append(d)
        print("samples bank", name, len(waves))
    return out


def main(argv):
    rom = open(argv[1], "rb").read()
    os.makedirs(argv[2], exist_ok=True)
    T = Tables(rom)
    tex = textures(rom, T)
    with gzip.open(os.path.join(argv[2], "textures.json.gz"), "wt") as f:
        json.dump(tex, f, separators=(",", ":"))
    if "--no-audio" not in argv:
        smp = samples(rom)
        with gzip.open(os.path.join(argv[2], "samples.json.gz"), "wt") as f:
            json.dump(smp, f, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv)
