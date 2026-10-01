"""Bit-packed LZSS used by DK64 for the sound bank ctl files (boot 0x800028E0).

Flag bit 1 = literal (8 bits). Flag 0 = N-bit window position (0 = end) and
(15-N+1)-bit length, copy length+3 bytes. Window 2^N, write position starts at 1.
"""


def decode(src, n=13):
    out = bytearray()
    W = 1 << n
    win = bytearray(W)
    r = 1
    lbits = 16 - n
    pos = 0
    nb = len(src) * 8

    def bits(k):
        nonlocal pos
        v = 0
        for _ in range(k):
            v = (v << 1) | ((src[pos >> 3] >> (7 - (pos & 7))) & 1)
            pos += 1
        return v

    while pos < nb:
        if bits(1):
            c = bits(8)
            out.append(c); win[r] = c; r = (r + 1) & (W - 1)
        else:
            o = bits(n)
            if o == 0:
                break
            ln = bits(lbits) + 3
            for k in range(ln):
                c = win[(o + k) & (W - 1)]
                out.append(c); win[r] = c; r = (r + 1) & (W - 1)
    return bytes(out), (pos + 7) >> 3


def encode(data, n=13):
    W = 1 << n
    lbits = 16 - n
    maxlen = (1 << lbits) - 1 + 3
    acc = []          # (value, nbits)
    table = {}
    i = 0
    L = len(data)

    def add(j):
        if j + 3 <= L:
            table.setdefault(data[j:j + 3], []).append(j)

    while i < L:
        best = 0; bj = 0
        cands = table.get(data[i:i + 3])
        if cands:
            lo = i - (W - 2)
            for j in reversed(cands[-48:]):
                if j < lo:
                    break
                # the decoder reads from the window while writing: overlap is
                # only safe when the source stays behind the write position
                m = 0
                lim = min(maxlen, L - i, i - j)
                while m < lim and data[j + m] == data[i + m]:
                    m += 1
                if m > best:
                    best = m; bj = j
                    if m == maxlen:
                        break
        if best >= 3 and ((bj + 1) & (W - 1)) != 0:
            acc.append((0, 1)); acc.append(((bj + 1) & (W - 1), n)); acc.append((best - 3, lbits))
            for k in range(best):
                add(i + k)
            i += best
        else:
            acc.append((1, 1)); acc.append((data[i], 8))
            add(i); i += 1
    acc.append((0, 1)); acc.append((0, n))
    v = 0; nb = 0
    for val, k in acc:
        v = (v << k) | val; nb += k
    pad = (-nb) % 8
    v <<= pad; nb += pad
    out = v.to_bytes(nb // 8, "big")
    if len(out) & 1:
        out += b"\0"
    return out
