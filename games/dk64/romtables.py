"""DK64 (US) asset pointer tables: parse, extract, repack.

The ROM keeps every asset in 32 pointer tables at 0x101C50. Each table is an
array of count+1 u32 offsets (relative to the base); top bit = the entry holds
a u16 index of another file in the same table. Files are gzip members or raw.
"""
import struct, zlib

BASE = 0x101C50
NTAB = 32
NAMES = ["midi", "map_geometry", "map_walls", "map_floors", "prop_geometry",
         "actor_geometry", "unused6", "textures_uncompressed", "cutscenes",
         "setup", "scripts", "animations", "text", "anim_code", "textures_hud",
         "paths", "spawners", "dktv", "triggers", "unk19", "unk20", "autowalks",
         "critters", "exits", "checkpoints", "textures_geometry",
         "uncompressed_sizes"] + ["unused%d" % i for i in range(27, 32)]
FLAG = 0x80000000


def gunzip(d):
    return zlib.decompressobj(31).decompress(d)


def gz(d):
    c = zlib.compressobj(9, zlib.DEFLATED, 31)
    out = bytearray(c.compress(d) + c.flush())
    out[4:8] = b"\0\0\0\0"   # mtime
    out[8] = 2; out[9] = 3   # xfl=max, os=unix (as gzip -9)
    return bytes(out)


class Tables:
    def __init__(self, rom):
        self.rom = rom
        self.offs = struct.unpack(">32I", rom[BASE:BASE + 128])
        self.cnt = struct.unpack(">32I", rom[BASE + 128:BASE + 256])
        self.ent = []
        for t in range(NTAB):
            n = self.cnt[t]
            o = BASE + self.offs[t]
            self.ent.append(struct.unpack(">%dI" % (n + 1), rom[o:o + 4 * (n + 1)]) if n else ())
        self.end = max(BASE + (e[-1] & ~FLAG) for e in self.ent if e)

    def raw(self, t, i):
        """Stored bytes of entry i (compressed if it is), b'' if empty."""
        e = self.ent[t]
        return self.rom[BASE + (e[i] & ~FLAG):BASE + (e[i + 1] & ~FLAG)]

    def indirect(self, t, i):
        return bool(self.ent[t][i] & FLAG)

    def file(self, t, i):
        """(data, was_gzip) following indirection; None if empty."""
        if self.indirect(t, i):
            i = struct.unpack(">H", self.raw(t, i)[:2])[0]
        d = self.raw(t, i)
        if not d:
            return None
        if d[:2] == b"\x1f\x8b":
            return gunzip(d), True
        return d, False

    def files(self, t):
        for i in range(self.cnt[t]):
            if self.indirect(t, i):
                continue
            f = self.file(t, i)
            if f:
                yield i, f[0], f[1]


def repack(rom, replace):
    """New ROM bytes with replace[(table, index)] = uncompressed data.

    Unreplaced entries keep their stored bytes. Layout: same table order and
    positions as retail when nothing grows; everything after the tables stays.
    """
    T = Tables(rom)
    out = bytearray(rom)
    pos = BASE + min(e[0] & ~FLAG for e in T.ent if e)
    first = pos
    blobs = []
    for t in sorted(range(NTAB), key=lambda t: T.offs[t]):
        n = T.cnt[t]
        if not n:
            continue
        # each table: data of its files, then (retail order) the table itself
        new = []
        data = bytearray()
        start = BASE + (T.ent[t][0] & ~FLAG)
        tabpos = BASE + T.offs[t]
        assert tabpos < start, "layout: table before data"
        blobs.append((t, tabpos, start, new, data))
        for i in range(n):
            d = T.raw(t, i)
            if (t, i) in replace:
                nd = replace[(t, i)]
                d2 = gz(nd) if d[:2] == b"\x1f\x8b" else nd
                if len(d2) & 1 and not len(d) & 1:
                    d2 += b"\0"
                d = d2
            new.append((len(data), T.ent[t][i] & FLAG))
            data += d
        new.append((len(data), T.ent[t][n] & FLAG))
    # lay out sequentially from the first table position
    pos = min(b[1] for b in blobs)
    hdr = list(T.offs)
    for t, tabpos, start, new, data in sorted(blobs, key=lambda b: b[1]):
        gap = start - (tabpos + 4 * len(new))
        hdr[t] = pos - BASE
        dstart = pos + 4 * len(new) + gap
        tab = b"".join(struct.pack(">I", (dstart + o - BASE) | f) for o, f in new)
        out[pos:pos + len(tab)] = tab
        out[dstart:dstart + len(data)] = data
        pos = dstart + len(data)
        pos += (-pos) & 3
        nxt = [b[1] for b in blobs if b[1] > tabpos]
        if nxt and not replace:
            pos = min(nxt)
    assert pos <= len(rom)
    if pos > T.end + 16:
        # grew into what follows the tables: only allowed if that is padding
        tail = rom[T.end:pos]
        assert tail.count(tail[:1]) == len(tail), "tables grew into data at %x" % T.end
    out[BASE:BASE + 128] = struct.pack(">32I", *hdr)
    return bytes(out)


if __name__ == "__main__":
    import sys, hashlib
    rom = open(sys.argv[1], "rb").read()
    T = Tables(rom)
    for t in range(NTAB):
        if T.cnt[t]:
            fs = list(T.files(t))
            print("%2d %-22s n=%5d files=%5d bytes=%9d" % (t, NAMES[t], T.cnt[t], len(fs), sum(len(f[1]) for f in fs)))
    print("tables end %x" % T.end, "tail byte", rom[T.end:T.end + 64].hex()[:32])
    r2 = repack(rom, {})
    print("roundtrip identical:", r2 == rom)
    # recompress test: replace everything in table 12 with itself
    rep = {(12, i): d for i, d, g in T.files(12)}
    r3 = repack(rom, rep)
    T3 = Tables(r3)
    print("recompress table 12 ok:", all(T3.file(12, i)[0] == d for (t, i), d in rep.items()),
          "end %x" % T3.end)
