"""Build the clean ROM: kept facts (code, geometry, text, sequences) + regenerated
textures and samples.

    python -m games.dk64.generate <baserom.us.z64> <spec dir> <out.z64> [--no-audio] [--audio-cache dir]

The base ROM supplies only the kept parts. Every file of texture tables 7/14/25
and every byte of both sample tables (and their codebooks/loop states) is
written from the spec; the script asserts that coverage.
"""
import gzip
import hashlib
import json
import os
import struct
import sys

import numpy as np

from cleanroom.audio import albank, descriptor, vadpcm
from cleanroom.decomp import gen
from cleanroom.gfx import texfmt

from . import lzss, texguess
from .romtables import Tables, repack

BANKS = (("A", 0x188AF20, 0x1897860, 0x1A97280), ("B", 0x1A97280, 0x1ABCBF0, 0x1FED020))
TEX_TABLES = (7, 14, 25)
RGBA, CI, IA, I = 0, 2, 3, 4
RETAIL_SHA1 = "cf806ff2603640a748fca5026ded28802f1f4a50"


# ------------------------------------------------------------------ textures

def key(rec, extra=""):
    return "t%d/%d%s" % (rec["t"], rec["i"], extra)


def base_image(rec, d, k):
    """RGBA from the kept grid + outline, with our own noise detail."""
    dd = {"w": rec["w"], "h": rec["h"], "grid": d["grid"]}
    if "alpha2" in d:
        dd["alpha2"] = d["alpha2"]
    img = gen.from_digest(k, dd)
    if rec["fmt"] == I and "alpha2" in d:
        # intensity textures are their own alpha: the outline carries the shape
        a = img[..., 3]
        img = np.stack([a, a, a, a], -1)
    return img


def box(img, w, h):
    H, W = img.shape[:2]
    ys = (np.arange(h + 1) * H // h)
    xs = (np.arange(w + 1) * W // w)
    out = np.zeros((h, w, 4), np.float32)
    f = img.astype(np.float32)
    for y in range(h):
        for x in range(w):
            out[y, x] = f[ys[y]:max(ys[y] + 1, ys[y + 1]), xs[x]:max(xs[x] + 1, xs[x + 1])].reshape(-1, 4).mean(0)
    return out.astype(np.uint8)


def rows(data, w, h, siz, rowb):
    nat = (w * (4 << siz) + 7) // 8
    if nat == rowb:
        return data
    out = bytearray()
    for y in range(h):
        out += data[y * nat:(y + 1) * nat] + bytes(rowb - nat)
    return bytes(out)


def pack(rec, img, enc):
    """Level 0 + mip chain in the file's layout, exactly rec['len'] bytes."""
    L, w, h, siz = rec["len"], rec["w"], rec["h"], rec["siz"]
    lv = texguess.layouts(L, w, h, siz) or [(w, h, (w * (4 << siz) + 7) // 8)]
    out = bytearray()
    for k, (wk, hk, rowb) in enumerate(lv):
        im = img if k == 0 else box(img, wk, hk)
        out += rows(enc(im), wk, hk, siz, rowb)
    out = out[:L] + bytes(max(0, L - len(out)))
    return bytes(out)


def rgba16(colors):
    return texfmt.encode(np.asarray(colors, np.uint8).reshape(1, -1, 4), RGBA, 2)


def quantize(images, weights, K, seed):
    """images: list (per texture) of (npix, M, 4) float; weights: (M,) bool per texture.
    Joint palette over M palette variants. -> centres (K, M, 4), list of index arrays."""
    rng = np.random.default_rng(seed)
    X = np.concatenate(images, 0)
    W = np.concatenate([np.broadcast_to(w, (len(x), len(w))) for x, w in zip(images, weights)], 0).astype(np.float32)
    n = len(X)
    sub = rng.choice(n, min(n, 6000), replace=False)
    Xs, Ws = X[sub], W[sub]
    C = Xs[rng.choice(len(Xs), K, replace=len(Xs) < K)].copy()

    def assign(Xa, Wa):
        out = np.empty(len(Xa), np.int32)
        for s in range(0, len(Xa), 4096):
            x = Xa[s:s + 4096]; w = Wa[s:s + 4096]
            d = (((x[:, None] - C[None]) ** 2).sum(-1) * w[:, None, :]).sum(-1)
            out[s:s + 4096] = d.argmin(1)
        return out

    for _ in range(10):
        lab = assign(Xs, Ws)
        for k in range(K):
            m = lab == k
            if m.any():
                ww = Ws[m][..., None]
                C[k] = (Xs[m] * ww).sum(0) / np.maximum(ww.sum(0), 1e-6)
    # fully transparent texels need a transparent entry
    lab = assign(X, W)
    idx = []
    o = 0
    for x in images:
        idx.append(lab[o:o + len(x)]); o += len(x)
    return C, idx


def gen_textures(spec, hooks=None):
    out = {}
    stats = {"tex": 0, "ci": 0, "tlut": 0, "raw": 0, "hook": 0}
    by = {(r["t"], r["i"]): r for r in spec}
    # standalone palettes, raw
    for r in spec:
        k = (r["t"], r["i"])
        if r["kind"] == "raw":
            out[k] = bytes([r["mean"]]) * r["len"]; stats["raw"] += 1
        elif r["kind"] == "tlut":
            g = np.asarray(r["grid"], np.float32)
            n = max(1, r["n"])
            xs = (np.arange(n) + 0.5) / n * 4 - 0.5
            x0 = np.clip(np.floor(xs).astype(int), 0, 3); x1 = np.clip(x0 + 1, 0, 3)
            f = np.clip(xs - np.floor(xs), 0, 1)[:, None]
            cols = g[x0] * (1 - f) + g[x1] * f
            cols[:, 3] = np.where(cols[:, 3] > 127, 255, 0)
            b = rgba16(np.clip(cols, 0, 255))
            out[k] = (b + bytes(r["len"]))[:r["len"]]; stats["tlut"] += 1
    # plain textures
    for r in spec:
        if r["kind"] != "tex" or r["fmt"] == CI:
            continue
        k = (r["t"], r["i"])
        img = None
        if hooks:
            img = hooks(r)
            if img is not None:
                stats["hook"] += 1
        if img is None:
            img = base_image(r, r, key(r))
        out[k] = pack(r, img, lambda im, r=r: texfmt.encode(im, r["fmt"], r["siz"]))
        stats["tex"] += 1
    # CI textures: union-find over texture <-> palette
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    ci = [r for r in spec if r["kind"] == "tex" and r["fmt"] == CI]
    for r in ci:
        for p in r["pals"]:
            parent[find(("p", p))] = find(("t", r["i"]))
    comps = {}
    for r in ci:
        comps.setdefault(find(("t", r["i"])), []).append(r)
    for root, texs in sorted(comps.items(), key=lambda kv: kv[1][0]["i"]):
        pals = sorted({p for r in texs for p in r["pals"]})
        K = min(1 << (4 << r["siz"]) for r in texs)
        K = min([K] + [by[(25, p)]["len"] // 2 for p in pals])
        images, weights = [], []
        for r in texs:
            x = np.zeros((r["w"] * r["h"], len(pals), 4), np.float32)
            w = np.zeros(len(pals), np.float32)
            for q, p in enumerate(pals):
                if str(p) in r["variants"]:
                    hk = hooks(r, p) if hooks else None
                    img = hk if hk is not None else base_image(r, r["variants"][str(p)], key(r, "/p%d" % p))
                    img = img.astype(np.float32)
                    img[..., 3] = np.where(img[..., 3] > 127, 255, 0)
                    x[:, q] = img.reshape(-1, 4); w[q] = 1
            images.append(x); weights.append(w)
        C, idx = quantize(images, weights, K, gen.h32("ci", texs[0]["i"]))
        for q, p in enumerate(pals):
            pr = by[(25, p)]
            b = rgba16(np.clip(C[:, q], 0, 255))
            out[(25, p)] = (b + bytes(pr["len"]))[:pr["len"]]
        for r, ix in zip(texs, idx):
            im = np.zeros((r["h"], r["w"], 4), np.uint8)
            im[..., 0] = ix.reshape(r["h"], r["w"])
            # mips of an index image: nearest sample
            L, w, h, siz = r["len"], r["w"], r["h"], r["siz"]
            lv = texguess.layouts(L, w, h, siz) or [(w, h, (w * (4 << siz) + 7) // 8)]
            data = bytearray()
            for kx, (wk, hk, rowb) in enumerate(lv):
                sm = im[::max(1, h // hk), ::max(1, w // wk)][:hk, :wk]
                data += rows(texfmt.encode(sm, CI, siz), wk, hk, siz, rowb)
            out[(25, r["i"])] = bytes(data[:L] + bytes(max(0, L - len(data))))
            stats["ci"] += 1
    print("textures generated:", stats)
    return out


# ------------------------------------------------------------------- samples

def book_bytes(preds, npred):
    ps = [preds[i % len(preds)] for i in range(npred)]
    b = vadpcm.make_book(ps)
    return b, struct.pack(">ii", b["order"], b["npred"]) + struct.pack(">%dh" % len(b["book"]), *b["book"])


def gen_wave(d):
    k = "smp/%s/%x" % (d["bank"], d["wave"])
    desc = d["desc"]
    if "f0" in d and "loop" in d:
        # sustained instrument: hold the measured pitch (frame estimates have octave errors)
        desc = {"frames": [dict(f, f0=d["f0"]) if f["f0"] > 20 else f for f in desc["frames"]]}
    n = d["nframes"]
    x = descriptor.synthesize(desc, n, d["rate"], seed=gen.h32("smp", k))
    x = np.pad(np.asarray(x, np.float32)[:n], (0, max(0, n - len(x))))
    if "loop" in d and d["loop"][1] > d["loop"][0] and d["loop"][1] <= n:
        x = descriptor.make_loop_seamless(x, d["loop"][0], d["loop"][1])
    dither = np.random.default_rng(gen.h32("dither", k)).integers(-1, 2, n)
    pcm = np.clip(np.round(np.clip(x, -1, 1) * 32000) + dither, -32768, 32767).astype(np.int16)
    preds = gen.two_predictors(pcm.astype(np.float64))
    return pcm, preds


def _wave_job(d):
    pcm, preds = gen_wave(d)
    book, bb = book_bytes(preds, 4)
    data, _, dec = vadpcm.encode(pcm, book)
    st = vadpcm.loop_state(dec, d["loop"][0]) if "loop" in d else None
    return d["bank"], d["wave"], data, bb, st


def gen_audio(rom, samples, cache=None, procs=4):
    """-> {rom offset: bytes} patches for both ctl (LZSS) and tbl regions."""
    jobs = samples
    res = {}
    if cache and os.path.exists(cache):
        import pickle
        res = pickle.load(open(cache, "rb"))
    todo = [d for d in jobs if (d["bank"], d["wave"]) not in res]
    if todo:
        import multiprocessing as mp
        with mp.Pool(procs) as pool:
            for n, (bank, wave, data, bb, st) in enumerate(pool.imap_unordered(_wave_job, todo, chunksize=4)):
                res[(bank, wave)] = (data, bb, st)
        if cache:
            import pickle
            pickle.dump(res, open(cache, "wb"))
    patches = {}
    for name, ctl0, tbl0, tbl1 in BANKS:
        ctl = bytearray(lzss.decode(rom[ctl0:tbl0])[0])
        tbl = bytearray(tbl1 - tbl0)
        books = {}
        nw = 0
        for d in samples:
            if d["bank"] != name:
                continue
            data, bb, st = res[(name, d["wave"])]
            wo = d["wave"]
            base, ln, typ, fl, lp, bk = struct.unpack_from(">IiBBxxII", ctl, wo)
            assert base == d["base"] and ln == d["len"] == len(data), (name, hex(wo))
            order, npred = struct.unpack_from(">ii", ctl, bk)
            assert len(bb) == 8 + 16 * order * npred
            if bk in books and books[bk] != bb:
                # shared codebook: re-encode with the first wave's book
                book = {"order": order, "npred": npred,
                        "book": list(struct.unpack(">%dh" % (8 * order * npred), books[bk][8:]))}
                pcm, _ = gen_wave(d)
                data, _, dec = vadpcm.encode(pcm, book)
                st = vadpcm.loop_state(dec, d["loop"][0]) if "loop" in d else None
            else:
                books[bk] = bb
                ctl[bk:bk + len(bb)] = bb
            if lp:
                struct.pack_into(">16h", ctl, lp + 12, *st)
            tbl[base:base + ln] = data
            nw += 1
        enc = lzss.encode(bytes(ctl))
        assert lzss.decode(enc)[0] == bytes(ctl)
        assert len(enc) <= tbl0 - ctl0, "ctl %s grew: %d > %d" % (name, len(enc), tbl0 - ctl0)
        patches[ctl0] = enc + bytes(tbl0 - ctl0 - len(enc))
        patches[tbl0] = bytes(tbl)
        print("bank %s: %d waves, ctl %d/%d bytes" % (name, nw, len(enc), tbl0 - ctl0))
    return patches


# ----------------------------------------------------------------------- rom

def main(argv):
    rom = open(argv[1], "rb").read()
    spec_dir, outp = argv[2], argv[3]
    spec = json.load(gzip.open(os.path.join(spec_dir, "textures.json.gz"), "rt"))
    hooks = None
    try:
        from . import drawn
        hooks = drawn.hook
    except ImportError:
        pass
    tex = gen_textures(spec, hooks)
    T = Tables(rom)
    need = {(t, i) for t in TEX_TABLES for i, d, g in T.files(t)}
    assert need == set(tex), "texture coverage: %d missing" % len(need - set(tex))
    for k in need:
        assert len(tex[k]) == len(T.file(*k)[0]), k
    out = bytearray(repack(rom, tex))
    if "--no-audio" not in argv:
        smp = json.load(gzip.open(os.path.join(spec_dir, "samples.json.gz"), "rt"))
        cache = argv[argv.index("--audio-cache") + 1] if "--audio-cache" in argv else None
        for off, data in gen_audio(rom, smp, cache).items():
            out[off:off + len(data)] = data
    else:
        print("WARNING: --no-audio build keeps retail samples: DEV ONLY, never publish")
    # the header checksum covers 0x1000-0x101000 (boot + code), which is untouched
    assert out[0x1000:0x101000] == rom[0x1000:0x101000]
    assert hashlib.sha1(out).hexdigest() != RETAIL_SHA1
    open(outp, "wb").write(out)
    print("wrote", outp, "sha1", hashlib.sha1(out).hexdigest()[:12])


if __name__ == "__main__":
    main(sys.argv)
