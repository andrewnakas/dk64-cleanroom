"""Dev tool: run a ROM in native mupen64plus (unthrottled, no input) and grab frames.

    python tools/m64p_test.py <rom.z64> <out dir> [--frames 600,1200,...]

Adds the ROM's MD5 to the emulator database as a copy of the US BK entry (EEPROM 16 KB), so
modified ROMs get the same settings. Without input the game runs its intro/attract mode.
Writes frame_<n>.png and a contact sheet; prints a one-line summary.
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys

M64P = r"D:/n64work/dk64/emu/m64p"
US = "9EC41ABF2519FC386CADD0731F6E868C"  # Banjo-Kazooie (U) V1.0: EEPROM 4 KB


def main(argv):
    rom, out = argv[1], argv[2]
    frames = argv[argv.index("--frames") + 1] if "--frames" in argv else "600,1200,1800,2400,3000,3600,4200,4800"
    script = argv[argv.index("--script") + 1] if "--script" in argv else None
    md5 = hashlib.md5(open(rom, "rb").read()).hexdigest().upper()
    ini = os.path.join(M64P, "mupen64plus.ini")
    txt = open(ini, encoding="latin1").read()
    if f"[{md5}]" not in txt:
        txt += f"\n[{md5}]\nGoodName=Donkey Kong 64 (U) clean room\nRefMD5={US}\n"
        open(ini, "w", encoding="latin1").write(txt)
    shots = os.path.join(M64P, "shots")
    shutil.rmtree(shots, ignore_errors=True)
    os.makedirs(shots)
    env = dict(os.environ)
    extra = []
    if script:
        env["M64P_SCRIPT"] = os.path.abspath(script)
        extra = ["--input", "mupen64plus-input-script.dll"]
    r = subprocess.run([os.path.join(M64P, "mupen64plus-ui-console.exe"), "--noosd", "--windowed", "--resolution", os.environ.get("M64P_RES", "320x240"),
                        "--nospeed", "--audio", "dummy", "--sshotdir", shots, "--testshots", frames] + extra + [
                        "--configdir", M64P, "--datadir", M64P, os.path.abspath(rom)],
                       cwd=M64P, capture_output=True, text=True, timeout=int(os.environ.get("M64P_TIMEOUT", "240")), env=env)
    os.makedirs(out, exist_ok=True)
    fl = frames.split(",")
    got = sorted(glob.glob(os.path.join(shots, "*.png")))
    for f, n in zip(got, fl):
        shutil.copyfile(f, os.path.join(out, f"shot_{int(n) / 60:.0f}.png"))
    errs = [l for l in r.stdout.splitlines() + r.stderr.splitlines() if "rror" in l][:3]
    print(f"m64p: {len(got)}/{len(fl)} frames -> {out}; exit {r.returncode}; {errs}")


if __name__ == "__main__":
    main(sys.argv)
