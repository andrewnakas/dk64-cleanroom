"""Contact sheet of textures as the spec interprets them (dirty ROM = dev only, or the clean ROM).

    python -m games.dk64.sheet <rom.z64> <spec dir> <out.png> <table> [first] [count] [--cell 68] [--ids a,b,c]
"""
import gzip
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from cleanroom.gfx import texfmt

from .romtables import Tables


def decode(T, by, t, i):
    r = by.get((t, i))
    f = T.file(t, i)
    if r is None or f is None:
        return None
    d = f[0]
    if r["kind"] == "tlut":
        n = len(d) // 2
        return texfmt.decode(d, n, 1, 0, 2).reshape(1, n, 4).repeat(8, 0).repeat(max(1, 64 // n), 1)
    if r["kind"] != "tex":
        return None
    w, h, fmt, siz = r["w"], r["h"], r["fmt"], r["siz"]
    if fmt == 2:
        pd = T.file(25, r["pals"][0])[0]
        pal = texfmt.decode(pd, len(pd) // 2, 1, 0, 2).reshape(-1, 4)
        idx = texfmt.decode(d, w, h, 2, siz)[..., 0]
        return pal[np.minimum(idx, len(pal) - 1)]
    return texfmt.decode(d, w, h, fmt, siz)


def main(argv):
    rom, spec_dir, out, t = argv[1], argv[2], argv[3], int(argv[4])
    cell = int(argv[argv.index("--cell") + 1]) if "--cell" in argv else 68
    spec = json.load(gzip.open(os.path.join(spec_dir, "textures.json.gz"), "rt"))
    by = {(r["t"], r["i"]): r for r in spec}
    T = Tables(open(rom, "rb").read())
    if "--ids" in argv:
        ids = [int(x) for x in argv[argv.index("--ids") + 1].split(",")]
    else:
        pos = [a for a in argv[5:] if not a.startswith("--") and a.isdigit()]
        first = int(pos[0]) if pos else 0
        count = int(pos[1]) if len(pos) > 1 else 200
        ids = [i for (tt, i) in sorted(by) if tt == t and i >= first][:count]
    cols = max(1, 1500 // cell)
    rows_ = (len(ids) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows_ * (cell + 10)), (40, 40, 60))
    dr = ImageDraw.Draw(sheet)
    for n, i in enumerate(ids):
        img = decode(T, by, t, i)
        x, y = (n % cols) * cell, (n // cols) * (cell + 10)
        r = by[(t, i)]
        tag = "%d" % i + ({"guess": "?", "sprite": "s", "dl": ""}.get(r.get("src"), ""))
        dr.text((x + 1, y), tag, fill=(255, 255, 0))
        if img is None:
            continue
        im = Image.fromarray(img, "RGBA")
        sc = min((cell - 2) / im.width, (cell - 2) / im.height)
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.NEAREST if sc >= 1 else Image.BILINEAR)
        bg = Image.new("RGBA", im.size, (90, 60, 110, 255))
        bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB"), (x + 1, y + 10))
    sheet.save(out)
    print("sheet", out, len(ids), "textures", sheet.size)


if __name__ == "__main__":
    main(sys.argv)
