#!/usr/bin/env python3
"""Full-screen picture importer for HAS `#import image` / CLI.

Converts PNG or IFF/ILBM sources into chip-RAM assembly suitable for
`SetGraphicsMode` + `LoadPalette` + `ShowPicture`:

  mode=lores  → 320×256×32, 5 bitplanes, line-interleaved (mode 0)
  mode=hires  → 640×256×16, 4 bitplanes, line-interleaved (mode 1)
  mode=ham6   → 320×256 HAM6, 6 bitplanes, pure planar (mode 2)

Lores/hires default to Floyd–Steinberg dithering (best quality for photos
onto a small Amiga palette). HAM6 uses a 16-colour median-cut base palette
plus hold-and-modify encoding from tools/iff_importer.py. HAM6 always forces
COLOR0 to black ($000) so left-edge modify codes match Denise scanline reload.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

# Allow running as a script from tools/ or via #import _load_tool.
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import amiga_palette as ap  # noqa: E402
import iff_importer as iff  # noqa: E402

ModeSpec = Tuple[str, int, int, int, int, str]
# name → (width, height, planes, colors, layout)
# layout: "interleaved" | "planar"
_MODE_TABLE = {
    "lores": ("lores", 320, 256, 5, 32, "interleaved"),
    "320x256x32": ("lores", 320, 256, 5, 32, "interleaved"),
    "mode0": ("lores", 320, 256, 5, 32, "interleaved"),
    "hires": ("hires", 640, 256, 4, 16, "interleaved"),
    "640x256x16": ("hires", 640, 256, 4, 16, "interleaved"),
    "mode1": ("hires", 640, 256, 4, 16, "interleaved"),
    "ham6": ("ham6", 320, 256, 6, 16, "planar"),
    "mode2": ("ham6", 320, 256, 6, 16, "planar"),
}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".iff", ".ilbm", ".lbm"}


def normalize_mode(mode: str) -> ModeSpec:
    key = (mode or "").strip().lower()
    if key not in _MODE_TABLE:
        raise ValueError(
            f"image mode must be lores|hires|ham6 "
            f"(aliases: 320x256x32, 640x256x16, mode0|mode1|mode2); got {mode!r}"
        )
    return _MODE_TABLE[key]


def _ensure_pillow() -> None:
    if Image is None:
        raise RuntimeError("Pillow is required for image import (pip install pillow)")


def _pack_row_planes(indices: Sequence[int], width: int, planes: int) -> List[bytes]:
    """Pack one scanline of palette indices into per-plane byte rows (word-aligned)."""
    bytes_per_row = ((width + 15) // 16) * 2
    out = [bytearray(bytes_per_row) for _ in range(planes)]
    for x in range(width):
        idx = int(indices[x]) if x < len(indices) else 0
        byte_i = x // 8
        bit_i = 7 - (x % 8)
        mask = 1 << bit_i
        for p in range(planes):
            if (idx >> p) & 1:
                out[p][byte_i] |= mask
    return [bytes(b) for b in out]


def indices_to_interleaved(indices_by_row: List[List[int]], planes: int) -> bytes:
    """Line-interleaved planar: for each row, plane0..planeN-1 (modes 0/1)."""
    height = len(indices_by_row)
    width = len(indices_by_row[0]) if height else 0
    chunks: List[bytes] = []
    for y in range(height):
        row = indices_by_row[y]
        plane_rows = _pack_row_planes(row, width, planes)
        for p in range(planes):
            chunks.append(plane_rows[p])
    return b"".join(chunks)


def indices_to_planar(indices_by_row: List[List[int]], planes: int) -> bytes:
    """Pure planar: all rows of plane0, then plane1, … (HAM6 layout)."""
    height = len(indices_by_row)
    width = len(indices_by_row[0]) if height else 0
    bytes_per_row = ((width + 15) // 16) * 2
    plane_size = bytes_per_row * height
    planar = bytearray(plane_size * planes)
    for y in range(height):
        plane_rows = _pack_row_planes(indices_by_row[y], width, planes)
        for p in range(planes):
            offset = p * plane_size + y * bytes_per_row
            planar[offset : offset + bytes_per_row] = plane_rows[p]
    return bytes(planar)


def _resize_rgba(img, width: int, height: int):
    _ensure_pillow()
    rgba = img.convert("RGBA")
    if rgba.size == (width, height):
        return rgba
    # LANCZOS for downscale quality; falls back if older Pillow lacks Resampling.
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:  # pragma: no cover
        resample = Image.LANCZOS
    return rgba.resize((width, height), resample)


def _load_pil(source_path: Path):
    _ensure_pillow()
    return Image.open(str(source_path))


def _iff_to_rgba(img: "iff.ILBMImage"):
    """Decode IFF (including HAM) to a Pillow RGBA image (8-bit channels)."""
    _ensure_pillow()
    if img.is_ham6 or img.is_ham8:
        rows = iff.decode_ham_rgb_rows(img)
        # HAM6 hold register is 4-bit (0..15); HAM8 is 6-bit (0..63).
        pixels = []
        for row in rows:
            for r, g, b in row:
                if img.is_ham6:
                    pixels.append((r * 17, g * 17, b * 17, 255))
                else:
                    pixels.append(
                        (
                            min(255, (r << 2) | (r >> 4)),
                            min(255, (g << 2) | (g >> 4)),
                            min(255, (b << 2) | (b >> 4)),
                            255,
                        )
                    )
        out = Image.new("RGBA", (img.width, img.height))
        out.putdata(pixels)
        return out

    if not img.indices_by_row:
        img.indices_by_row = iff.ilbm_to_indices(img)
    pixels = []
    for row in img.indices_by_row:
        for idx in row:
            if idx < len(img.palette):
                r, g, b = img.palette[idx]
            else:
                r = g = b = 0
            pixels.append((r, g, b, 255))
    out = Image.new("RGBA", (img.width, img.height))
    out.putdata(pixels)
    return out


def _palette_words_asm(label: str, words: Sequence[int], count: int) -> str:
    lines = [f"{label}_palette:"]
    for i in range(count):
        w = int(words[i]) & 0xFFF if i < len(words) else 0
        lines.append(f"\tDC.W\t${w:03X}\t; COLOR{i}")
    return "\n".join(lines)


def _bitmap_dc_b(label: str, data: bytes) -> str:
    lines = [f"{label}:"]
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_bytes = ",".join(f"${b:02X}" for b in chunk)
        lines.append(f"\tDC.B\t{hex_bytes}")
    lines.append("\teven")
    return "\n".join(lines)


def export_picture_asm(
    source_path: str,
    out_label: str,
    *,
    mode: str = "lores",
    dither: str = "fs",
) -> str:
    """Convert source image to ShowPicture-ready assembly text."""
    canon, width, height, planes, colors, layout = normalize_mode(mode)
    dither = (dither or "fs").lower()
    if dither not in ("none", "fs", "ordered"):
        raise ValueError(f"dither must be none|fs|ordered (got {dither!r})")

    src = Path(source_path)
    suffix = src.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        raise ValueError(
            f"unsupported image type {src.name} "
            f"(expected PNG/JPEG/GIF/BMP/IFF)"
        )

    # Fast path: native HAM6 IFF already at 320×256 — keep planar codes as-is.
    if canon == "ham6" and suffix in (".iff", ".ilbm", ".lbm"):
        ilbm = iff.parse_iff_ilbm(str(src))
        if ilbm.is_ham6 and ilbm.width == width and ilbm.height == height and ilbm.planes == 6:
            # Reuse iff_importer's planar conversion + palette.
            return iff.export_iff_as_bob(str(src), out_label, ham6=False)

    # Build RGBA at target size (PNG/JPEG/… or decoded IFF).
    if suffix in (".iff", ".ilbm", ".lbm"):
        ilbm = iff.parse_iff_ilbm(str(src))
        rgba = _iff_to_rgba(ilbm)
    else:
        rgba = _load_pil(src)
    rgba = _resize_rgba(rgba, width, height)

    if canon == "ham6":
        # 16-colour base palette + HAM6 encode → pure planar.
        conv = ap.convert_image(
            rgba,
            colors=16,
            dither=dither,
            index0="backdrop",
            requantize=True,
        )
        base_palette = []
        for i in range(16):
            r, g, b = conv["palette_tuples"][i]
            base_palette.append((r >> 4, g >> 4, b >> 4))

        # Amiga HAM reloads COLOR0 at the start of every scanline. encode_ham6_from_rgb
        # also assumes hold=(0,0,0) there — COLOR0 must be black or left-edge "modify"
        # codes paint stripes (often green) from the wrong hold colour.
        base_palette[0] = (0, 0, 0)

        # encode_ham6_from_rgb expects 6-bit RGB rows (0..63); it >>2's to 4-bit.
        rgba_data = ap.flatten_image_pixels(rgba)
        rows_rgb = []
        for y in range(height):
            row = []
            for x in range(width):
                r, g, b, _a = rgba_data[y * width + x]
                row.append((r >> 2, g >> 2, b >> 2))
            rows_rgb.append(row)

        codes = iff.encode_ham6_from_rgb(rows_rgb, base_palette)
        planar = iff.ham6_codes_to_planar(codes)
        words = [
            ((r4 & 15) << 8) | ((g4 & 15) << 4) | (b4 & 15)
            for (r4, g4, b4) in base_palette
        ]

        expected = width * height // 8 * 6
        if len(planar) != expected:
            raise RuntimeError(
                f"HAM6 planar size mismatch: got {len(planar)}, expected {expected}"
            )

        asm = (
            f"; Full-screen picture for SetGraphicsMode(2) + ShowPicture "
            f"(HAM6 {width}x{height}, 6 planes, {expected} bytes, planar)\n"
            f"; Source: {src.name}\n"
            f"; Dither/base palette: {dither}\n"
            f"\tSECTION pictures,DATA_C\n"
            f"\tCNOP\t0,4\n"
            f"\tXDEF\t{out_label}\n"
            f"\tXDEF\t{out_label}_palette\n"
            f"\n; HAM6 base palette (16 colors)\n"
            f"{_palette_words_asm(out_label, words, 16)}\n"
            f"\n; Bitmap data ({expected} bytes, pure planar)\n"
            f"{_bitmap_dc_b(out_label, planar)}\n"
        )
        return asm

    # Indexed lores / hires.
    conv = ap.convert_image(
        rgba,
        colors=colors,
        dither=dither,
        index0="backdrop",
        requantize=True,
    )
    indices = conv["indices_by_row"]
    # Clamp indices to plane budget.
    mask = (1 << planes) - 1
    indices = [[idx & mask for idx in row] for row in indices]

    if layout == "interleaved":
        bitmap = indices_to_interleaved(indices, planes)
    else:
        bitmap = indices_to_planar(indices, planes)

    expected = width * height // 8 * planes
    if len(bitmap) != expected:
        raise RuntimeError(
            f"{canon} bitmap size mismatch: got {len(bitmap)}, expected {expected}"
        )

    mode_id = 0 if canon == "lores" else 1
    asm = (
        f"; Full-screen picture for SetGraphicsMode({mode_id}) + ShowPicture "
        f"({width}x{height}x{colors}, {planes} planes, {expected} bytes, "
        f"{layout})\n"
        f"; Source: {src.name}\n"
        f"; Dither: {dither}\n"
        f"\tSECTION pictures,DATA_C\n"
        f"\tCNOP\t0,4\n"
        f"\tXDEF\t{out_label}\n"
        f"\tXDEF\t{out_label}_palette\n"
        f"\n; Palette ({colors} colors)\n"
        f"{_palette_words_asm(out_label, conv['palette_words'], colors)}\n"
        f"\n; Bitmap data ({expected} bytes, line-interleaved)\n"
        f"{_bitmap_dc_b(out_label, bitmap)}\n"
    )
    return asm


def import_image_to_include(
    source_path: str,
    label: str,
    *,
    mode: str = "lores",
    dither: str = "fs",
    out_dir: Optional[str] = None,
    force: bool = False,
) -> Path:
    """Write `{label}.s` under out_dir (default include/) and return the path."""
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(source_path)

    if out_dir:
        out_file = Path(out_dir) / f"{label}.s"
    else:
        out_file = Path(__file__).parent.parent / "include" / f"{label}.s"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    regenerate = True
    if out_file.exists() and not force:
        try:
            if (
                out_file.stat().st_mtime >= src.stat().st_mtime
                and out_file.stat().st_mtime >= Path(__file__).stat().st_mtime
            ):
                regenerate = False
        except OSError:
            regenerate = True

    if regenerate:
        asm = export_picture_asm(
            str(src), label, mode=mode, dither=dither
        )
        out_file.write_text(
            f"; Auto-generated by image_importer as {label}\n{asm}\n",
            encoding="utf-8",
        )
    return out_file


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert PNG/IFF to full-screen Amiga picture assembly "
        "for ShowPicture (lores 320x256x32 / hires 640x256x16 / HAM6)."
    )
    parser.add_argument("source", help="PNG, JPEG, or IFF/ILBM source image")
    parser.add_argument(
        "--mode",
        default="lores",
        help="lores|hires|ham6 (aliases: 320x256x32, 640x256x16, mode0|1|2)",
    )
    parser.add_argument(
        "--dither",
        default="fs",
        choices=("none", "fs", "ordered"),
        help="Quantization dither (default: fs / Floyd–Steinberg)",
    )
    parser.add_argument("--label", "--label-prefix", dest="label", default=None)
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source)
    label = args.label or ("pic_" + src.stem.replace(" ", "_").replace(".", "_"))
    out = import_image_to_include(
        str(src),
        label,
        mode=args.mode,
        dither=args.dither,
        out_dir=args.outdir,
        force=args.force,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
