# TexturePacker Atlas Importer

`tools/texturepacker_atlas_importer.py` converts a TexturePacker XML atlas and PNG into Amiga BOB
assembly files. All frames use one shared quantized palette, so they can be used as an animation.

## Basic Usage

```bash
python tools/texturepacker_atlas_importer.py walk.xml \
    --outdir build/gen \
    --master-include build/gen/walk_atlas.s
```

Each XML sprite produces a sanitized, prefixed descriptor label. For example, `walk_0.png` in
`walk.xml` produces `walk_walk_0` by default. Pass its address to `CreateBobAnimation` or `CreateBob`.

## Repeated Frames

TexturePacker may list the same frame more than once. By default, the importer writes a complete BOB
file for every XML entry, preserving the existing one-file-per-frame behavior.

Use `--deduplicate-frames` to store identical converted frames only once:

```bash
python tools/texturepacker_atlas_importer.py walk.xml \
    --outdir build/gen \
    --master-include build/gen/walk_atlas.s \
    --deduplicate-frames
```

The first matching frame is the canonical file. Later frames export alias labels at the same
descriptor, data, mask, and palette addresses. Every logical frame name remains usable in an
animation, but the master include references the physical file only once.

Frames are compared after extraction, optional size restoration, and shared-palette quantization.
Consequently, source pixels that become identical at the selected bitplane depth can be deduplicated.
Changing from normal output to deduplicated output also removes stale duplicate frame files.

## Common Options

| Option | Purpose |
|---|---|
| `--planes 1..5` | Select 2 to 32 colours; default is 5 bitplanes. |
| `--label-prefix NAME` | Override the XML filename prefix used for assembly labels. |
| `--restore-original-size` | Pad trimmed sprites back to their original dimensions. |
| `--dither` | Enable Floyd-Steinberg dithering during shared-palette quantization. |
| `--add-word` | Add a 16-pixel blitter safety word. |
| `--sprites a,b` | Import only the listed TexturePacker names or stems. |
| `--shared-palette-file PATH` | Write the shared palette as a standalone assembly file. |
| `--force` | Regenerate output even when existing files are current. |

See [LIBRARY_REFERENCE.md](LIBRARY_REFERENCE.md) for the runtime animation API.