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


def hook(rec, pal=None):
    if rec["t"] == 14 and rec.get("src") == "font":
        return font_page(rec)
    return None
