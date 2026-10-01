"""DIRTY ROOM check: clean ROM vs retail ROM, every regenerated asset.

    python -m games.dk64.taint_report <baserom.us.z64> <clean.z64>

Streams compared (runs >= 32 identical non-trivial bytes fail):
  textures  - every file of tables 7/14/25 (stored texel bytes)
  samples   - both sample tables (ADPCM bytes) and decoded ctl codebooks/loop states region by wave
Kept facts (code, geometry, text, sequences, bank structure) are not scanned.
"""
import struct
import sys

from cleanroom import taint
from cleanroom.audio import albank

from . import lzss
from .romtables import Tables

BANKS = (("A", 0x188AF20, 0x1897860, 0x1A97280), ("B", 0x1A97280, 0x1ABCBF0, 0x1FED020))
TEX_TABLES = (7, 14, 25)


def streams(rom):
    T = Tables(rom)
    for t in TEX_TABLES:
        for i, d, g in T.files(t):
            yield "tex %d/%d" % (t, i), d
    import json, os
    from . import minigames
    mg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec", "minigames.json")))
    for ov, k in ((minigames.ARCADE, "arcade"), (minigames.JETPAC, "jetpac")):
        data = minigames.blobs(rom, ov)[1]
        for r in mg[k]:
            yield "mini %s/%x" % (k, r["off"]), data[r["off"]:r["off"] + r["len"]]
    for name, ctl0, tbl0, tbl1 in BANKS:
        ctl = lzss.decode(rom[ctl0:tbl0])[0]
        bf = albank.parse_bankfile(ctl)
        b = bf["banks"][0]
        seen = set()
        for ins in [x for x in b["insts"] if x] + ([b["percussion"]] if b["percussion"] else []):
            for sd in ins["sounds"]:
                w = sd["wave"]
                if w["_id"] in seen:
                    continue
                seen.add(w["_id"])
                yield "smp %s/%s" % (name, w["_id"]), rom[tbl0 + w["base"]:tbl0 + w["base"] + w["len"]]
                bk = struct.pack(">%dh" % len(w["book"]["book"]), *w["book"]["book"])
                yield "book %s/%s" % (name, w["_id"]), bk
        yield "tbl %s whole" % name, rom[tbl0:tbl1]


def main(argv):
    retail = open(argv[1], "rb").read()
    clean = open(argv[2], "rb").read()
    index = taint.build_index(s for _, s in streams(retail))
    n = 0

    def counted():
        nonlocal n
        for l, s in streams(clean):
            n += 1
            yield l, s
    hits = taint.scan(index, counted())
    bad = sorted((h for h in hits if h[3] >= taint.FAIL_RUN), key=lambda h: -h[3])
    print(f"taint: {n} generated streams scanned; {len(hits)} with short coincidental matches; "
          f"{len(bad)} failing (run >= {taint.FAIL_RUN} B)")
    import collections
    print("  failing by kind:", dict(collections.Counter(h[0].split()[0] for h in bad)))
    for label, off, ln, run in [h for h in bad if h[0].startswith("tex")][:6] + bad[:6]:
        print(f"  FAIL {label} run {run} B")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
