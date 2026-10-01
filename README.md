# Donkey Kong 64 — clean room web build

Play: **https://andrewnakas.github.io/dk64-cleanroom/**

Donkey Kong 64 running in the browser (EmulatorJS + mupen64plus-next, WebGL) from a ROM image in which
**every texture and every sound sample has been regenerated**. The game code, level geometry, animations,
text and music sequences are the ones documented by the [dk64 decompilation](https://gitlab.com/dk64_decomp/dk64).

Controls: `Arrows` move · `X` A (jump) · `C` B (attack) · `Z` Z (crouch) · `S` R (camera) · `Q` L ·
`Enter` Start · `I J K L` C-buttons. Gamepads work too. Saves are kept in the browser.

## What is kept, what is generated

| Asset | Kept fact | Generated |
|---|---|---|
| Textures (7173 files: world, characters, sprites, HUD) | format, size, a 4×4 colour grid (16×16 for images of 128 px and up), a 2-bit alpha outline | colour from the grid plus our own noise detail; colour-indexed textures are quantised to new palettes |
| Fonts (8 styles, 43 pages) | cell positions and widths (tables in the game code) | every glyph drawn with an original stroke font; button icons drawn |
| Text-bearing textures | the words | re-typeset (`games/dk64/text_labels.json`) |
| Sound samples (285 instrument waves, 889 effect/voice waves) | length, loop points, a coarse spectral outline, one median-pitch number | resynthesised, encoded with our own ADPCM codebooks |
| Music | the note sequences (MIDI events) | played by the resynthesised instruments |
| Code, geometry, collision, animations, cutscenes, text, demo inputs | as in the decompilation | — |

`games/dk64/taint_report.py` compares every generated texture and sample against the retail data for shared
runs of 32 bytes or more: **0 failing**.

## How it is built

The decompilation does not split assets into files, so this project has its own tools:

- `games/dk64/romtables.py` — the 32 asset pointer tables (parse, byte-exact repack)
- `games/dk64/lzss.py` — the bit-packed LZSS used for the sound bank control files
- `games/dk64/texscan.py`, `texguess.py` — texture format/size from display lists, sprite records, or a smoothness guess
- `games/dk64/extract_spec.py` — the **dirty room**: reads a ROM once and writes only the kept facts (`games/dk64/spec/`)
- `games/dk64/generate.py`, `drawn.py` — the clean room: builds every texture and sample from the spec
- `ports/ejs/` — the web page (EmulatorJS)

```
python -m games.dk64.extract_spec baserom.us.z64 games/dk64/spec
python -m games.dk64.generate baserom.us.z64 games/dk64/spec dk64_clean.z64
python -m games.dk64.taint_report baserom.us.z64 dk64_clean.z64
```

No ROM is included in this repository. Voices are synthetic placeholders; no performer is imitated and no model
was trained on the game's audio.

Donkey Kong 64 is © Nintendo / Rare. This is a non-commercial preservation and research project.
