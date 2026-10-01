"""Textures drawn by us instead of grid-upsampled: fonts, HUD digits, icons, labels.

hook(rec, pal=None) -> RGBA uint8 (h, w, 4) or None (fall back to the grid image).
Fonts come from spec/fonts.json: the cell tables are code data (kept), the glyph
shapes are our stroke font.
"""
import json
import os

import numpy as np

from cleanroom.gfx import glyphs, strokefont

HERE = os.path.dirname(os.path.abspath(__file__))

# characters the shared stroke font lacks (design box 4 x 6, baseline y = 6)
strokefont.G.update({
    "0": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],   # no slash: reads as 8 when small
    "$": [[(4, 1), (1, 1), (0, 2), (1, 3), (3, 3), (4, 4), (3, 5), (0, 5)], [(2, 0), (2, 6)]],
    ";": [[(0.6, 2.5), (0.6, 2.5)], [(0.6, 5.6), (0, 7)]],
    "@": [[(3, 4), (3, 2), (1.5, 2), (1.5, 4), (4, 4), (4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (4, 6)]],
    "[": [[(1.5, 0), (0, 0), (0, 6), (1.5, 6)]],
    "]": [[(0, 0), (1.5, 0), (1.5, 6), (0, 6)]],
    "^": [[(0, 2), (1.5, 0), (3, 2)]],
    "_": [[(0, 6.5), (4, 6.5)]],
    "`": [[(0, 0), (1, 1.5)]],
    "{": [[(2, 0), (1, 0.5), (1, 2.5), (0, 3), (1, 3.5), (1, 5.5), (2, 6)]],
    "}": [[(0, 0), (1, 0.5), (1, 2.5), (2, 3), (1, 3.5), (1, 5.5), (0, 6)]],
    "|": [[(0, 0), (0, 6)]],
    "~": [[(0, 3.5), (1, 2.5), (2.5, 3.5), (3.5, 2.5)]],
    "£": [[(4, 1), (3, 0), (2, 0), (1, 1), (1, 6)], [(0, 3), (3, 3)], [(0, 6), (4, 6)]],
    "©": [[(3, 2), (2, 1.5), (1, 2.5), (1, 3.5), (2, 4.5), (3, 4)],
               [(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
    "∞": [[(2, 3), (1, 2), (0, 3), (1, 4), (2, 3), (3, 2), (4, 3), (3, 4), (2, 3)]],
    "¡": [[(0, 0), (0, 0)], [(0, 1.8), (0, 6)]],
    "¿": [[(2, 0), (2, 0)], [(2, 1.8), (2, 3), (0, 4.5), (0, 5.2), (1, 6), (3, 6), (4, 5.2)]],
    "▲": [[(2, 0.5), (4, 5), (0, 5), (2, 0.5)], [(2, 2), (2, 4.5)], [(1.2, 4), (2.8, 4)]],
    "▼": [[(2, 5.5), (4, 1), (0, 1), (2, 5.5)], [(2, 4), (2, 1.5)], [(1.2, 2), (2.8, 2)]],
})

FONTS = None


def _fonts():
    global FONTS
    if FONTS is None:
        FONTS = {}
        p = os.path.join(HERE, "spec", "fonts.json")
        for st in (json.load(open(p)) if os.path.exists(p) else []):
            for ch, page, x, w in st["glyphs"]:
                FONTS.setdefault(page, (st, []))[1].append((ch, x, w))
    return FONTS


# style 1 (menu font) control characters -> what we draw
BTN = {"r": "R", "l": "L", "q": "A", "b": "B", "z": "Z", "g": "S"}
ARROW = {"n": "C-up", "s": "C-down", "w": "C-left", "e": "C-right"}
SYM1 = {"c": "©", "o": "∞"}
# style 2 (small caps font): shifted digits are small digits, braces are numerals
SYM2 = {")": "0", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "c": "©",
        "{": "I", "}": "II", "a": "E", "b": "R", "m": "m"}
SYM0 = {"#": "£", "\x7f": "▲", "\x80": "▼"}


def _white(m):
    img = np.zeros(m.shape + (4,), np.float32)
    img[..., :3] = 255
    img[..., 3] = m * 255
    return img


def _outlined(m, fill=(255, 255, 255), edge=(20, 20, 30)):
    o = glyphs._outline(m, 1)
    img = np.zeros(m.shape + (4,), np.float32)
    img[..., :3] = edge
    img[..., 3] = np.clip(o + m, 0, 1) * 255
    img[..., :3] = img[..., :3] * (1 - m[..., None]) + np.asarray(fill, np.float32) * m[..., None]
    return img


def _glow(m, color=(150, 190, 255)):
    h, w = m.shape
    g = m.copy()
    for _ in range(4):
        p = np.pad(g, 1)
        g = np.maximum(g, (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + p[1:-1, 1:-1]) / 5.0)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = np.asarray(color, np.float32) * (1 - m[..., None]) + 255 * m[..., None]
    img[..., 3] = np.clip(np.maximum(m, g * 0.85), 0, 1) * 255
    return img


def font_page(rec):
    f = _fonts().get(rec["i"])
    if f is None:
        return None
    st, gl = f
    s = st["style"]
    h, w = rec["h"], rec["w"]
    img = np.zeros((h, w, 4), np.float32)
    if s == 7:
        gl = [g for g in gl if g[0].isdigit()]
    for ch, x, cw in gl:
        cw = min(cw, w - x)
        if cw < 2:
            continue
        if s == 0:
            ch = SYM0.get(ch, ch)
            m = strokefont.render(ch, cw, h - 1, thickness=1.0)
            cell = _outlined(np.pad(m, ((0, 1), (0, 0))))
        elif s == 1:
            if ch in BTN:
                cell = glyphs.button(BTN[ch], cw, min(cw, h))
                cell = np.pad(cell, (((h - cell.shape[0]) // 2, h - cell.shape[0] - (h - cell.shape[0]) // 2), (0, 0), (0, 0)))
            elif ch in ARROW:
                cell = glyphs.button(ARROW[ch], cw, min(cw, h))
                cell = np.pad(cell, (((h - cell.shape[0]) // 2, h - cell.shape[0] - (h - cell.shape[0]) // 2), (0, 0), (0, 0)))
            else:
                cell = glyphs.text_glyph(SYM1.get(ch, ch), cw, h, "hud", thickness=2.0)
        elif s in (3,):
            cell = glyphs.text_glyph(ch, cw, h, "hud", thickness=3.0)
        elif s == 7:
            cell = _glow(strokefont.render(ch, cw, h, thickness=2.2))
        elif s == 2:
            cell = _white(strokefont.render(SYM2.get(ch, ch), cw, h, thickness=0.75))
        elif s == 6:
            cell = _white(strokefont.render(ch, cw, h, thickness=0.95))
        else:
            cell = _white(strokefont.render(ch, cw, h, thickness=0.7))
        img[:, x:x + cw] = np.maximum(img[:, x:x + cw], cell[:, :cw]) if s != 1 else cell[:, :cw]
    if rec["fmt"] == 4:   # intensity: value = coverage
        a = img[..., 3]
        img = np.stack([a, a, a, a], -1)
    if rec["siz"] == 2 and rec["fmt"] == 0:
        img[..., 3] = (img[..., 3] >= 110) * 255.0
    return np.clip(img, 0, 255).astype(np.uint8)


LABELS = None


def label(rec):
    """Text-bearing textures re-typeset from text_labels.json: {"table/index": {lines, ink, bg, flip}}."""
    global LABELS
    if LABELS is None:
        p = os.path.join(HERE, "text_labels.json")
        LABELS = json.load(open(p)) if os.path.exists(p) else {}
    lb = LABELS.get("%d/%d" % (rec["t"], rec["i"]))
    if lb is None:
        return None
    w, h = rec["w"], rec["h"]
    rot = lb.get("rot", 0)                      # texture stored rotated: draw upright then rotate
    dw, dh = (h, w) if rot in (90, 270) else (w, h)
    lb2 = dict(lb, bg=lb.get("bg", [0, 0, 0, 0]), ink=lb.get("ink", [255, 255, 255, 255]))
    if lb.get("over"):
        # words drawn over the regenerated (grid) image instead of a flat background
        from cleanroom.decomp import gen
        d = {"w": w, "h": h, "grid": rec["grid"]}
        if "alpha2" in rec:
            d["alpha2"] = rec["alpha2"]
        base = gen.from_digest("t%d/%d" % (rec["t"], rec["i"]), d).astype(np.float32)
        m = glyphs.label_texture(dict(lb2, bg=[0, 0, 0, 0], ink=[255, 255, 255, 255]), dw, dh)[..., 3] / 255.0
        if rot:
            m = np.rot90(m, k=rot // 90)
        if "v" in lb.get("flip", ""):
            m = m[::-1]
        if "h" in lb.get("flip", ""):
            m = m[:, ::-1]
        o = glyphs._outline(np.ascontiguousarray(m), 1)
        base[..., :3] *= (1 - 0.7 * np.clip(o, 0, 1))[..., None]
        ink = np.asarray(lb2["ink"][:3], np.float32)
        base[..., :3] = base[..., :3] * (1 - m[..., None]) + ink * m[..., None]
        return np.clip(base, 0, 255).astype(np.uint8)
    img = glyphs.label_texture(lb2, dw, dh)
    if lb.get("edge"):
        m = img[..., 3] / 255.0
        o = np.clip(glyphs._outline(np.ascontiguousarray(m), int(lb.get("edge_w", 2))) + m, 0, 1)
        e = np.zeros_like(img)
        e[..., :3] = lb["edge"][:3]
        e[..., 3] = o * 255
        e[..., :3] = e[..., :3] * (1 - m[..., None]) + img[..., :3] * m[..., None]
        img = e
    if lb.get("frame"):
        m = np.zeros((dh, dw), np.float32)
        t = max(1, int(lb.get("frame_w", 2)))
        m[:t] = m[-t:] = 1; m[:, :t] = 1; m[:, -t:] = 1
        glyphs._layer(img, m, lb["frame"])
    if rot:
        img = np.rot90(img, k=rot // 90)
    if "v" in lb.get("flip", ""):
        img = img[::-1]
    if "h" in lb.get("flip", ""):
        img = img[:, ::-1]
    img = np.clip(img, 0, 255)
    if rec["fmt"] == 0 and rec["siz"] == 2:
        img[..., 3] = (img[..., 3] >= 110) * 255.0
    if rec["fmt"] == 4:
        a = img[..., 3]
        img = np.stack([a, a, a, a], -1)
    return np.ascontiguousarray(img).astype(np.uint8)


FACES = None


def _faces():
    global FACES
    if FACES is None:
        p = os.path.join(HERE, "face_briefs.json")
        FACES = {}
        if os.path.exists(p):
            for grp in json.load(open(p))["eyes"]:
                for i in grp["ids"]:
                    FACES[(grp.get("t", 25), i)] = grp
    return FACES


def auto_eye(rec, cfg):
    """Eye texture from the kept grid: the bright cells give where the eyeball shows (so blink
    frames work); the eyeball, iris, pupil and highlight are drawn by us (colours from the brief)."""
    from cleanroom.decomp import gen
    w, h = rec["w"], rec["h"]
    S = 4
    g = gen.upsample_grid(rec["grid"], int(round(len(rec["grid"]) ** 0.5)), w * S, h * S)[..., :3]
    cells = np.asarray(rec["grid"], np.float32)[:, :3]
    sc = np.asarray(cfg.get("sclera", [255, 255, 255]), np.float32)
    # closeness to the eyeball colour, per cell and per pixel
    d_cells = np.abs(cells - sc).sum(1)
    d = np.abs(g - sc).sum(-1)
    lo, hi = d_cells.min(), d_cells.max()
    skin_cells = cells[d_cells > (lo + hi) / 2] if hi - lo > 120 else cells
    skin = skin_cells.mean(0) if len(skin_cells) else cells.mean(0)
    img = np.empty((h * S, w * S, 3), np.float32)
    img[:] = skin
    # keep the skin's own coarse shading
    lum = g.mean(-1, keepdims=True) / max(1.0, g.mean())
    img *= np.clip(0.75 + 0.25 * lum, 0.6, 1.25)
    if lo < 150 and hi - lo > 120:
        m = d < (lo + hi) / 2
        ys, xs = np.nonzero(m)
        if len(ys) > 40:
            cy, cx = ys.mean(), xs.mean()
            bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
            yy, xx = np.mgrid[0:h * S, 0:w * S].astype(np.float32)
            shade = 1.0 - 0.18 * np.clip(np.hypot((xx - cx) / bw, (yy - cy) / bh) * 1.6, 0, 1)
            img[m] = (sc[None, :] * shade[..., None])[m]
            rx, ry = cfg.get("iris_rx", 0.2) * bw, cfg.get("iris_ry", 0.3) * bh
            e = ((xx - cx) / max(rx, 1)) ** 2 + ((yy - cy) / max(ry, 1)) ** 2
            iris = (e < 1) & m
            img[iris] = np.asarray(cfg.get("iris", [40, 80, 200]), np.float32)
            img[(e < 0.3) & m] = (10, 10, 15)
            hl = (((xx - (cx - rx * 0.35)) / max(rx * 0.28, 1)) ** 2 + ((yy - (cy - ry * 0.4)) / max(ry * 0.22, 1)) ** 2 < 1) & iris
            img[hl] = (255, 255, 255)
            # dark rim where eyeball meets skin
            p = np.pad(m, S, mode="edge")
            er = p[S:-S, S:-S] & p[:-2 * S, S:-S] & p[2 * S:, S:-S] & p[S:-S, :-2 * S] & p[S:-S, 2 * S:]
            img[m & ~er] *= 0.35
    out = img.reshape(h, S, w, S, 3).mean((1, 3))
    out *= gen.detail(gen.h32("eye", rec["i"]), w, h, 0.03)[..., None]
    rgba = np.concatenate([out, np.full((h, w, 1), 255, np.float32)], -1)
    if "alpha2" in rec:
        rgba[..., 3] = gen.unpack_alpha2(rec["alpha2"], w, h)
    return np.clip(rgba, 0, 255).astype(np.uint8)


RINDS = None


def rind(rec, cfg):
    """Cartoon sprite from its kept outline: our fill colour, an edge band, optional seeds/shine."""
    from cleanroom.decomp import gen
    w, h = rec["w"], rec["h"]
    if "alpha2" not in rec:
        return None
    a = gen.unpack_alpha2(rec["alpha2"], w, h) > 120
    depth = np.zeros((h, w), np.int32)
    cur = a.copy()
    for k in range(1, 8):
        p = np.pad(cur, 1)
        cur = cur & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        depth += cur
    img = np.zeros((h, w, 4), np.float32)
    fill = np.asarray(cfg["fill"], np.float32)
    yy = np.linspace(1.12, 0.82, h, dtype=np.float32)[:, None, None]
    img[..., :3] = fill * yy
    ew = cfg.get("edge_px", 2)
    img[depth < ew, :3] = cfg["edge"]
    if cfg.get("edge2"):
        img[(depth >= ew) & (depth < ew + cfg.get("edge2_px", 1)), :3] = cfg["edge2"]
    if cfg.get("dots"):
        rng = np.random.default_rng(gen.h32("dots", rec["t"], rec["i"]))
        ys, xs = np.nonzero(depth >= ew + 2)
        for j in rng.choice(len(ys), min(len(ys), max(2, len(ys) // 40)), replace=False) if len(ys) else []:
            img[ys[j], xs[j], :3] = cfg["dots"]
    img[..., 3] = a * 255
    return np.clip(img, 0, 255).astype(np.uint8)


def _rinds():
    global RINDS
    if RINDS is None:
        RINDS = {}
        p = os.path.join(HERE, "sprite_briefs.json")
        if os.path.exists(p):
            for grp in json.load(open(p))["sprites"]:
                for i in grp["ids"]:
                    RINDS[(grp["t"], i)] = grp
    return RINDS


def hook(rec, pal=None):
    r = _rinds().get((rec["t"], rec["i"]))
    if r is not None and rec["fmt"] != 2:
        img = rind(rec, r)
        if img is not None:
            return img
    f = _faces().get((rec["t"], rec["i"]))
    if f is not None and rec["fmt"] != 2:
        return auto_eye(rec, f)
    if rec["t"] == 14 and rec.get("src") == "font":
        return font_page(rec)
    if rec["fmt"] != 2:
        return label(rec)
    return None
