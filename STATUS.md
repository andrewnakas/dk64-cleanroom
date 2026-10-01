# Donkey Kong 64 clean room: status

## Decisions (logged as made)
- **Web route = 3: clean ROM + WASM N64 emulator (EmulatorJS + mupen64plus_next)**, decided in the first 30 min.
  Why: no DK64 PC port exists; the decomp (gitlab dk64_decomp) only links an *uncompressed code image* and keeps
  all assets as one binary blob, so there is nothing to compile for the web. `ports/ejs` is reused from the
  Banjo-Kazooie session (core ROM-DB slot "Donkey Kong 64 (U) [b1]" pointed at our ROM's MD5: EEPROM 16 KB).
- **The decomp does not split assets.** Our own tools do it: `games/dk64/romtables.py` (32 pointer tables at
  0x101C50, gzip members, byte-exact repack verified), `lzss.py` (the handwritten bit-LZSS at boot 0x800028E0 used
  for the two sound-bank ctl files).
- **Code = kept fact, taken as the matching bytes.** The decomp matches the retail code (90 % C, rest asm from the
  ROM), so building it yields the same bytes; the clean ROM keeps boot + overlays as they are. Kept as well (user
  scope): geometry, collision, animations, cutscenes, setup/scripts, text (table 12), MIDI sequences (table 0),
  DKTV demo inputs (table 17).
- **Regenerated:** every file of texture tables 7 / 14 / 25 (7173 files) and every byte of both sample tables
  (A = 285 music instrument waves, B = 889 sound-effect waves) with our own VADPCM codebooks and loop states.
  `generate.py` asserts that coverage.
- Texture format/size is not stored with the texels. Sources, in order: display lists in map/prop/actor geometry
  (`texscan.scan`, 3788 files; CI palettes = the TLUT load that *follows* the texture), sprite records in
  code_124780 (`scan_sprites`, 1327), smoothness guess (`texguess`, 1151, ~90 % exact on known ones), 901 palettes.
- CI textures: image regenerated from the grid, then quantised to a new palette shared by all textures of that palette.

## Works
- Retail baseline in native mupen64plus (dev only): boots to the DK Rap.

## Next
- see bottom of file (updated each loop)
