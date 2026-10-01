"""Zoomed sheet of tile pairs with a 0.25 grid (dirty ROM = dev only, or the clean ROM).
    python tools/pairsheet.py <rom> <out.png> t:l,r [t:l,r ...]   (r may be omitted)"""
import gzip, json, sys
from PIL import Image, ImageDraw
from games.dk64.romtables import Tables
from games.dk64.sheet import decode
Z = 6
spec = json.load(gzip.open("games/dk64/spec/textures.json.gz", "rt"))
by = {(r["t"], r["i"]): r for r in spec}
if sys.argv[1] == "clean":               # render from the spec with our hooks instead of reading a ROM
    from games.dk64 import drawn, generate

    def decode(T, by, t, i):
        r = by[(t, i)]
        pal = r["pals"][0] if r["fmt"] == 2 else None
        img = drawn.hook(r, pal)
        d = r["variants"][str(pal)] if pal is not None else r
        return img if img is not None else generate.base_image(r, d, generate.key(r))
    T = None
else:
    T = Tables(open(sys.argv[1], "rb").read())
pics = []
for a in sys.argv[3:]:
    t, ids = a.split(":")
    ims = [Image.fromarray(decode(T, by, int(t), int(i)), "RGBA") for i in ids.split(",")]
    W, H = sum(i.width for i in ims), max(i.height for i in ims)
    p = Image.new("RGBA", (W, H), (90, 60, 110, 255)); x = 0
    for im in ims:
        p.alpha_composite(im, (x, 0)); x += im.width
    p = p.resize((W * Z, H * Z), Image.NEAREST).convert("RGB")
    d = ImageDraw.Draw(p); x = 0
    for im in ims:
        for k in range(1, 4):
            d.line([(x + im.width * Z * k // 4, 0), (x + im.width * Z * k // 4, H * Z)], fill=(0, 255, 255) if k == 2 else (0, 110, 110))
            d.line([(x, H * Z * k // 4), (x + im.width * Z, H * Z * k // 4)], fill=(0, 255, 255) if k == 2 else (0, 110, 110))
        x += im.width * Z
        d.line([(x - 1, 0), (x - 1, H * Z)], fill=(255, 255, 0))
    d.text((2, 2), a, fill=(255, 255, 0)); pics.append(p)
cols = 4
cw, ch = max(p.width for p in pics) + 8, max(p.height for p in pics) + 8
sh = Image.new("RGB", (cw * min(cols, len(pics)), ch * ((len(pics) + cols - 1) // cols)), (30, 30, 40))
for n, p in enumerate(pics):
    sh.paste(p, ((n % cols) * cw, (n // cols) * ch))
sh.save(sys.argv[2]); print("pairsheet", sys.argv[2], sh.size)
