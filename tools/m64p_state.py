"""Dev tool: run a ROM in mupen64plus.dll (ctypes) for N seconds, save a state, report threads.

    python tools/m64p_state.py <rom.z64> <out.st> [--secs 20] [--gfx rice|glide] [--elf build.elf]
Prints frames rendered and the live CPU PC/RA; writes <out>.rdram (big-endian 8 MB image); with --elf lists every
libultra thread (__osActiveQueue) with its saved PC/RA resolved to symbols.
"""
import ctypes as C
import gzip
import os
import struct
import subprocess
import sys
import threading
import time

M64P = r"D:/n64work/dk64/emu/m64p"
DBG = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_char_p)
STATE = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_int)
FRAME = C.CFUNCTYPE(None, C.c_uint)
PROBE = {}
# M64CMD_*: ROM_OPEN 1, EXECUTE 5, STOP 6, STATE_SAVE 11, SET_FRAME_CALLBACK 15
# plugin types: RSP 1, GFX 2, AUDIO 3, INPUT 4 (attach order gfx, audio, input, rsp)


def run(rom, out, secs, gfx="rice"):
    os.add_dll_directory(M64P)
    os.chdir(M64P)
    core = C.CDLL(os.path.join(M64P, "mupen64plus.dll"))
    logs = []
    dbg = DBG(lambda ctx, lvl, msg: logs.append(f"{lvl}:" + msg.decode(errors="replace")))
    st = STATE(lambda ctx, p, v: None)
    assert core.CoreStartup(0x020001, M64P.encode(), M64P.encode(), None, dbg, None, st) == 0
    plugins = [(2, "mupen64plus-video-rice.dll" if gfx == "rice" else "mupen64plus-video-glide64mk2.dll"),
               (4, "mupen64plus-input-script.dll"), (1, "mupen64plus-rsp-hle.dll")]
    handles = []
    for t, name in plugins:
        h = C.CDLL(os.path.join(M64P, name))
        h.PluginStartup(C.c_void_p(core._handle), None, dbg)
        handles.append((t, h))
    data = open(rom, "rb").read()
    buf = C.create_string_buffer(data, len(data))
    assert core.CoreDoCommand(1, len(data), buf) == 0, "rom open"
    for t, h in handles:
        assert core.CoreAttachPlugin(t, C.c_void_p(h._handle)) == 0, f"attach {t}"
    frames = [0]
    fcb = FRAME(lambda i: frames.__setitem__(0, i))
    core.CoreDoCommand(15, 0, fcb)
    rc = []
    th = threading.Thread(target=lambda: rc.append(core.CoreDoCommand(5, 0, None)), daemon=True)
    th.start()
    time.sleep(secs)
    # live probe (works without a savestate): PC, GPRs, RDRAM
    core.DebugGetCPUDataPtr.restype = C.c_void_p
    core.DebugMemGetPointer.restype = C.c_void_p
    pcs = []
    for _ in range(8):
        pcs.append(C.c_uint32.from_address(core.DebugGetCPUDataPtr(1)).value)
        time.sleep(0.05)
    regs = (C.c_int64 * 32).from_address(core.DebugGetCPUDataPtr(2))
    rp = core.DebugMemGetPointer(1)
    le = C.string_at(rp, 0x800000)
    open(out + ".rdram", "wb").write(struct.pack(">%dI" % 0x200000, *struct.unpack("<%dI" % 0x200000, le)))
    cop0 = (C.c_uint32 * 32).from_address(core.DebugGetCPUDataPtr(5))
    PROBE.update(pcs=pcs, ra=regs[31] & 0xFFFFFFFF, sp=regs[29] & 0xFFFFFFFF,
                 epc=cop0[14], badv=cop0[8], cause=cop0[13], regs=[r & 0xFFFFFFFF for r in regs])
    core.CoreDoCommand(6, 0, None)
    th.join(5)
    print(f"frames {frames[0]}; exec rc {rc}; errors: {[l for l in logs if l[0] in '12'][:4]}")


def decode(path, elf=None):
    rdram = open(path + ".rdram", "rb").read()
    if elf:
        threads(rdram, elf)
    return rdram


def symbols(elf):
    nm = subprocess.run([os.path.expanduser("~/.local/mips64/bin/mips64-elf-nm.exe"), "-n", elf],
                        capture_output=True, text=True).stdout.split("\n")
    funcs, byname = [], {}
    for l in nm:
        p = l.split()
        if len(p) == 3:
            byname.setdefault(p[2], int(p[0], 16))
            if p[1] in "tTwW":
                funcs.append((int(p[0], 16), p[2]))
    return funcs, byname


def threads(rdram, elf):
    funcs, byname = symbols(elf)

    def where(a):
        a &= 0xFFFFFFFF
        best = None
        for v, n in funcs:
            if v <= a:
                best = (v, n)
            else:
                break
        return f"{best[1]}+{a - best[0]:#x}" if best else hex(a)

    if PROBE:
        print("cpu pc", " ".join(sorted(set(where(p) for p in PROBE["pcs"]))), "| ra", where(PROBE["ra"]), "sp", hex(PROBE["sp"]))
        print(f"epc {where(PROBE['epc'])} ({PROBE['epc']:#x}) badvaddr {PROBE['badv']:#x} cause {PROBE['cause']:#x} (exc {(PROBE['cause'] >> 2) & 31})")
    w = lambda a: struct.unpack(">I", rdram[(a & 0x7FFFFF):(a & 0x7FFFFF) + 4])[0]
    t = w(byname["__osActiveQueue"])
    run_t = w(byname["__osRunningThread"])
    n = 0
    while t and (t & 0xFF800000) == 0x80000000 and n < 32:
        pc, ra = w(t + 0x11C), w(t + 0x104)
        state = struct.unpack(">H", rdram[(t & 0x7FFFFF) + 0x10:(t & 0x7FFFFF) + 0x12])[0]
        print(f"thread {w(t + 0x14)} pri {w(t + 4)} state {state}{' RUNNING' if t == run_t else ''}: "
              f"pc {where(pc)}  ra {where(ra)}")
        t = w(t + 0xC)
        n += 1


def main(argv):
    rom, out = argv[1], os.path.abspath(argv[2])
    secs = float(argv[argv.index("--secs") + 1]) if "--secs" in argv else 20
    gfx = argv[argv.index("--gfx") + 1] if "--gfx" in argv else "rice"
    elf = argv[argv.index("--elf") + 1] if "--elf" in argv else None
    run(rom, out, secs, gfx)
    decode(out, elf)


if __name__ == "__main__":
    main(sys.argv)
