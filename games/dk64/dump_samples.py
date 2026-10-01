"""DIRTY ROOM, dev only: decode the retail samples to WAV files (never published) so the voice
tools (practice pack, Whisper word finder) can read them.

    python -m games.dk64.dump_samples <baserom.us.z64> <dirty dir> [--whisper]

Writes <dirty>/samples/<bank>/<wave hex>.wav and games/dk64/spec/samples.json (path -> rate, nframes;
facts only). --whisper lists samples in which faster-whisper hears words -> <dirty>/speech.json.
"""
import gzip
import json
import os
import sys
import wave

import numpy as np

from cleanroom.audio import albank, vadpcm

from . import lzss
from .extract_spec import BANKS

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    rom = open(argv[1], "rb").read()
    out = argv[2]
    index = {}
    for name, ctl0, tbl0, tbl1 in BANKS:
        ctl, _ = lzss.decode(rom[ctl0:tbl0])
        b = albank.parse_bankfile(ctl)["banks"][0]
        os.makedirs(os.path.join(out, "samples", name), exist_ok=True)
        waves = {}
        for ins in [x for x in b["insts"] if x] + ([b["percussion"]] if b["percussion"] else []):
            for sd in ins["sounds"]:
                waves[sd["wave"]["_id"]] = (sd["wave"], sd["keymap"]["key_base"])
        for wid, (w, key) in waves.items():
            rel = "samples/%s/%s.wav" % (name, wid.split("@")[1])
            n = w["len"] // 9 * 16
            p = os.path.join(out, rel)
            if not os.path.exists(p):
                pcm = vadpcm.decode(rom[tbl0 + w["base"]:tbl0 + w["base"] + w["len"]], w["book"], n)
                with wave.open(p, "wb") as f:
                    f.setnchannels(1); f.setsampwidth(2); f.setframerate(b["rate"])
                    f.writeframes(np.asarray(pcm, "<i2").tobytes())
            index[rel] = {"rate": b["rate"], "nframes": n, "key": key}
    json.dump(index, open(os.path.join(HERE, "spec", "samples.json"), "w"), separators=(",", ":"))
    print("dumped", len(index), "samples")
    if "--whisper" in argv:
        from faster_whisper import WhisperModel
        model = WhisperModel("small.en", device="cpu", compute_type="int8")
        found = {}
        for rel, d in sorted(index.items()):
            if d["nframes"] < 0.35 * d["rate"]:
                continue
            segs, _ = model.transcribe(os.path.join(out, rel), beam_size=1, vad_filter=False,
                                       condition_on_previous_text=False, no_speech_threshold=0.5)
            segs = list(segs)
            text = " ".join(s.text.strip() for s in segs).strip()
            if text and segs and min(s.no_speech_prob for s in segs) < 0.4 and np.mean([s.avg_logprob for s in segs]) > -0.9:
                found[rel] = {"text": text, "secs": round(d["nframes"] / d["rate"], 2)}
        json.dump(found, open(os.path.join(out, "speech.json"), "w"), indent=1)
        print("speech candidates:", len(found))
        for k, v in list(found.items())[:60]:
            print(" ", k, v["secs"], v["text"][:70])


if __name__ == "__main__":
    main(sys.argv)
