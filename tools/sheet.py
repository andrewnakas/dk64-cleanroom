"""Contact sheet of headless shots: python tools/sheet.py <shots dir> [out.png] [--w 320]
Tiles shot_<t>.png in time order with the time label, one row of up to 4."""
import glob
import os
import sys

from PIL import Image, ImageDraw


def main(argv):
    d = argv[1]
    out = argv[2] if len(argv) > 2 and not argv[2].startswith("--") else os.path.join(d, "sheet.png")
    w = int(argv[argv.index("--w") + 1]) if "--w" in argv else 320
    files = sorted(glob.glob(os.path.join(d, "shot_*.png")), key=lambda p: float(os.path.basename(p)[5:-4]))
    if not files:
        print("no shots"); return
    ims = []
    for f in files:
        im = Image.open(f).convert("RGB")
        im = im.resize((w, int(im.height * w / im.width)))
        ImageDraw.Draw(im).text((4, 4), os.path.basename(f)[5:-4] + "s", fill=(255, 255, 0))
        ims.append(im)
    cols = min(4, len(ims))
    rows = (len(ims) + cols - 1) // cols
    h = max(i.height for i in ims)
    sheet = Image.new("RGB", (cols * w, rows * h))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out)
    print(f"{len(ims)} shots -> {out}")


if __name__ == "__main__":
    main(sys.argv)
