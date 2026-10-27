"""Compile-time asset import for #import bob|palette|sprite|atlas|tileset|tilemap|font|music|sound|image.

Orchestrates tools/bob_importer.py, tools/amiga_palette.py,
tools/sprite_importer.py, tools/texturepacker_atlas_importer.py,
tools/tile_importer.py, tools/tiled_map_importer.py,
tools/c64_font_converter.py, tools/extract_8svx.py, and tools/image_importer.py.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union

# Default when CLI does not pass --asset-outdir
DEFAULT_ASSET_OUTDIR = "build/gen"

# Hardware sprites are always one 16-pixel-wide DMA channel (2 planes / 4 colours).
SPRITE_WIDTH_PX = 16
SPRITE_PLANES = 2
SPRITE_COLORS = 4

_IMPORT_KINDS = "bob|palette|sprite|atlas|tileset|tilemap|font|music|sound|image"
_FONT_SUFFIXES = {".bin", ".s", ".asm"}
_SOUND_SUFFIXES = {".raw", ".iff", ".8svx"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".iff", ".ilbm", ".lbm"}
_AUDIO_KINDS = frozenset({"music", "sound"})

_IMPORT_RE = re.compile(
    rf'^#import\s+({_IMPORT_KINDS})\s+"([^"]+)"\s+as\s+([A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<opts>(?:\s+[A-Za-z_][A-Za-z0-9_]*(?:=[^\s;]+)?)*)\s*;?\s*$'
)

# Values: ids, decimals, 0x/$ hex, paths, or comma-separated sprite filters.
_OPT_RE = re.compile(
    r'([A-Za-z_][A-Za-z0-9_]*)(?:=(0[xX][0-9A-Fa-f]+|\$[0-9A-Fa-f]+|[^\s;]+))?'
)


@dataclass
class AssetImport:
    """One resolved #import (bob, palette, sprite, atlas, tileset, tilemap, font, music, sound, image)."""
    kind: str
    source_path: str  # absolute PNG / XML / TMX / JSON / font / MOD / sample / image path
    label: str
    options: Dict[str, Any] = field(default_factory=dict)
    gen_path: str = ""  # absolute path to generated .s (master for atlas)
    labels: List[str] = field(default_factory=list)  # all symbols; empty → [label]
    # music/sound: labels stay [label] (const ID identity); __data is assembly-only.


def asset_symbols(asset: AssetImport) -> List[str]:
    """Addressable HAS/assembly symbols produced by one import."""
    if asset.labels:
        return list(asset.labels)
    return [asset.label]


def _parse_bool_opt(value: Any, line_no: int, name: str) -> bool:
    if value is True or str(value).lower() in ("1", "true", "yes", "on"):
        return True
    if value is False or str(value).lower() in ("0", "false", "no", "off"):
        return False
    raise SyntaxError(
        f"Preprocessor error at line {line_no}: invalid {name} value"
    )


def _parse_int_opt(value: Any, line_no: int, name: str) -> int:
    """Accept decimal or 0x/$ hex integers for import options."""
    if isinstance(value, int):
        return int(value)
    s = str(value).strip()
    try:
        if s.startswith(("0x", "0X")):
            return int(s, 16)
        if s.startswith("$"):
            return int(s[1:], 16)
        return int(s, 10)
    except (TypeError, ValueError):
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: {name} must be an integer"
        ) from None


def _tools_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "tools"


def _load_tool(module_name: str, filename: str):
    """Load a tools/*.py module by path (tools/ is not always a package)."""
    path = _tools_dir() / filename
    if not path.exists():
        raise RuntimeError(f"Asset tool not found: {path}")
    # Prefer already-imported module (tests / package layout).
    pkg_name = f"tools.{module_name}"
    if pkg_name in sys.modules:
        return sys.modules[pkg_name]
    if module_name in sys.modules and getattr(sys.modules[module_name], "__file__", "").endswith(filename):
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(f"hasc_asset_{module_name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load asset tool: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def parse_import_line(stripped: str, line_no: int) -> Tuple[str, str, str, Dict[str, Any]]:
    """
    Parse `#import kind "path" as label [opts...];`.

    Returns (kind, path_raw, label, options).
    """
    m = _IMPORT_RE.match(stripped)
    if not m:
        # Narrower diagnostics for common mistakes
        if stripped.startswith("#import"):
            if ' as ' not in stripped:
                raise SyntaxError(
                    f"Preprocessor error at line {line_no}: "
                    f"#import requires 'as <label>' (e.g. #import bob \"x.png\" as my_bob;)"
                )
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: invalid #import syntax: {stripped}"
            )
        raise SyntaxError(f"Preprocessor error at line {line_no}: not an #import line")

    kind = m.group(1)
    path_raw = m.group(2)
    label = m.group(3)
    opts_blob = (m.group("opts") or "").strip()
    options: Dict[str, Any] = {}
    if opts_blob:
        for om in _OPT_RE.finditer(opts_blob):
            key = om.group(1)
            val = om.group(2)
            if key in options:
                raise SyntaxError(
                    f"Preprocessor error at line {line_no}: duplicate option '{key}' in #import"
                )
            if val is None:
                options[key] = True  # flag form (add_word, requantize)
            else:
                options[key] = val
    return kind, path_raw, label, options


def _normalize_font_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    """Font imports currently accept no options."""
    if options:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown font import option(s): "
            f"{', '.join(sorted(options))}"
        )
    return {}


def _normalize_music_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    """Music imports accept no options."""
    if options:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown music import option(s): "
            f"{', '.join(sorted(options))}"
        )
    return {}


def _normalize_sound_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    """Sound import options for sfx_table (ptplayer SfxStructure)."""
    allowed = {"period", "vol", "pri", "channel"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown sound import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "period": 443,   # ~8 kHz PAL (3546895/8000)
        "vol": 32,
        "pri": 64,
        "channel": -1,   # auto channel
    }
    if "period" in options:
        out["period"] = _parse_int_opt(options["period"], line_no, "period")
    if "vol" in options:
        out["vol"] = _parse_int_opt(options["vol"], line_no, "vol")
    if "pri" in options:
        out["pri"] = _parse_int_opt(options["pri"], line_no, "pri")
    if "channel" in options:
        out["channel"] = _parse_int_opt(options["channel"], line_no, "channel")
    return out


def _normalize_bob_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"planes", "dither", "add_word"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown bob import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "planes": 5,
        "dither": "none",
        "add_word": False,
    }
    if "planes" in options:
        try:
            planes = int(options["planes"])
        except (TypeError, ValueError):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: bob planes must be 1..5"
            ) from None
        if planes < 1 or planes > 5:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: bob planes must be 1..5"
            )
        out["planes"] = planes
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"bob dither must be none|fs (got {d!r})"
            )
        out["dither"] = d
    if "add_word" in options:
        # Extra empty 16px word so the blitter can shift the BOB to any X
        # (cookie-cut / A shift); planar width becomes ceil16(w)+16.
        out["add_word"] = _parse_bool_opt(options["add_word"], line_no, "add_word")
    return out


def _normalize_sprite_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"dither", "vstart", "vstop", "planes", "colors"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown sprite import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "dither": "none",
        "vstart": 0x10,
        "vstop": 0x20,
        "planes": SPRITE_PLANES,
        "colors": SPRITE_COLORS,
    }
    if "planes" in options:
        planes = _parse_int_opt(options["planes"], line_no, "planes")
        if planes != SPRITE_PLANES:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"hardware sprites are fixed at {SPRITE_PLANES} bitplanes "
                f"({SPRITE_COLORS} colours); got planes={planes}"
            )
    if "colors" in options:
        colors = _parse_int_opt(options["colors"], line_no, "colors")
        if colors != SPRITE_COLORS:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"hardware sprites are fixed at {SPRITE_COLORS} colours "
                f"(2 bitplanes); got colors={colors}"
            )
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"sprite dither must be none|fs (got {d!r})"
            )
        out["dither"] = d
    if "vstart" in options:
        out["vstart"] = _parse_int_opt(options["vstart"], line_no, "vstart") & 0x1FF
    if "vstop" in options:
        out["vstop"] = _parse_int_opt(options["vstop"], line_no, "vstop") & 0x1FF
    return out


def _normalize_palette_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"colors", "planes", "dither", "index0", "requantize"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown palette import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    if "colors" in options and "planes" in options:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"palette import: use only one of colors= or planes="
        )
    out: Dict[str, Any] = {
        "colors": 32,
        "dither": "none",
        "index0": "backdrop",
        "requantize": False,
    }
    if "planes" in options:
        try:
            planes = int(options["planes"])
        except (TypeError, ValueError):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette planes must be 1..5"
            ) from None
        if planes < 1 or planes > 5:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette planes must be 1..5"
            )
        out["colors"] = 2 ** planes
    elif "colors" in options:
        try:
            colors = int(options["colors"])
        except (TypeError, ValueError):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette colors must be 2..32"
            ) from None
        if colors < 2 or colors > 32:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: palette colors must be 2..32"
            )
        out["colors"] = colors
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs", "ordered"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"palette dither must be none|fs|ordered (got {d!r})"
            )
        out["dither"] = d
    if "index0" in options:
        i0 = str(options["index0"]).lower()
        if i0 not in ("backdrop", "transparent", "none"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"index0 must be backdrop|transparent|none"
            )
        out["index0"] = i0
    if "requantize" in options:
        out["requantize"] = _parse_bool_opt(options["requantize"], line_no, "requantize")
    return out


# Canonical ShowPicture modes; aliases accepted in #import image mode=.
_IMAGE_MODE_ALIASES = {
    "lores": "lores",
    "320x256x32": "lores",
    "mode0": "lores",
    "hires": "hires",
    "640x256x16": "hires",
    "mode1": "hires",
    "ham6": "ham6",
    "mode2": "ham6",
}


def _normalize_image_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    """Full-screen picture → pure/interleaved planar for ShowPicture."""
    allowed = {"mode", "dither"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown image import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        # Default to lores 320×256×32 (SetGraphicsMode 0).
        "mode": "lores",
        # Floyd–Steinberg is the best general-purpose dither for photos → 16/32 colours.
        "dither": "fs",
    }
    if "mode" in options:
        raw = str(options["mode"]).lower()
        if raw not in _IMAGE_MODE_ALIASES:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"image mode must be lores|hires|ham6 "
                f"(aliases: 320x256x32, 640x256x16, mode0|mode1|mode2); got {raw!r}"
            )
        out["mode"] = _IMAGE_MODE_ALIASES[raw]
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs", "ordered"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"image dither must be none|fs|ordered (got {d!r})"
            )
        out["dither"] = d
    return out


def _normalize_atlas_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    """TexturePacker XML atlas → shared-palette BOBs (v1: kind=bob only)."""
    allowed = {
        "kind", "planes", "dither", "add_word", "shared_palette", "dedupe",
        "restore_original_size", "sprites", "atlas_png",
    }
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown atlas import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "kind": "bob",
        "planes": 5,
        "dither": "none",
        "add_word": False,
        "shared_palette": True,
        "dedupe": False,
        "restore_original_size": False,
        "sprites": None,
        "atlas_png": None,
    }
    if "kind" in options:
        k = str(options["kind"]).lower()
        if k != "bob":
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import atlas v1 supports kind=bob only (got kind={k!r}); "
                f"hardware sprites need 16px-wide single frames via #import sprite"
            )
        out["kind"] = k
    if "planes" in options:
        planes = _parse_int_opt(options["planes"], line_no, "planes")
        if planes < 1 or planes > 5:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: atlas planes must be 1..5"
            )
        out["planes"] = planes
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"atlas dither must be none|fs (got {d!r})"
            )
        out["dither"] = d
    if "add_word" in options:
        out["add_word"] = _parse_bool_opt(options["add_word"], line_no, "add_word")
    if "shared_palette" in options:
        out["shared_palette"] = _parse_bool_opt(
            options["shared_palette"], line_no, "shared_palette"
        )
    if "dedupe" in options:
        out["dedupe"] = _parse_bool_opt(options["dedupe"], line_no, "dedupe")
    if "restore_original_size" in options:
        out["restore_original_size"] = _parse_bool_opt(
            options["restore_original_size"], line_no, "restore_original_size"
        )
    if "sprites" in options:
        raw = str(options["sprites"])
        names = [s.strip() for s in re.split(r'[,+]', raw) if s.strip()]
        if not names:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: atlas sprites= list is empty"
            )
        out["sprites"] = names
    if "atlas_png" in options:
        out["atlas_png"] = str(options["atlas_png"])
    return out


def _normalize_tileset_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {
        "tile_w", "tile_h", "tile_width", "tile_height",
        "planes", "dither", "match_palette", "strict_palette",
    }
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown tileset import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "tile_w": 16,
        "tile_h": 16,
        "planes": 5,
        "dither": "none",
        "match_palette": None,
        "strict_palette": False,
    }
    tw = options.get("tile_w", options.get("tile_width"))
    th = options.get("tile_h", options.get("tile_height"))
    if tw is not None:
        out["tile_w"] = _parse_int_opt(tw, line_no, "tile_w")
    if th is not None:
        out["tile_h"] = _parse_int_opt(th, line_no, "tile_h")
    if out["tile_w"] not in (8, 16, 32):
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: tileset tile_w must be 8, 16, or 32"
        )
    if out["tile_h"] not in (8, 16, 32):
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: tileset tile_h must be 8, 16, or 32"
        )
    if "planes" in options:
        planes = _parse_int_opt(options["planes"], line_no, "planes")
        if planes < 1 or planes > 5:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: tileset planes must be 1..5"
            )
        out["planes"] = planes
    if "dither" in options:
        d = str(options["dither"]).lower()
        if d not in ("none", "fs"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"tileset dither must be none|fs (got {d!r})"
            )
        out["dither"] = d
    if "match_palette" in options:
        out["match_palette"] = str(options["match_palette"])
    if "strict_palette" in options:
        out["strict_palette"] = _parse_bool_opt(
            options["strict_palette"], line_no, "strict_palette"
        )
    if out["strict_palette"] and not out["match_palette"]:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"tileset strict_palette requires match_palette=<label>"
        )
    return out


def _normalize_tilemap_options(options: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    allowed = {"layer", "layers", "allow_flip", "index_size", "firstgid", "tileset"}
    unknown = set(options) - allowed
    if unknown:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: unknown tilemap import option(s): "
            f"{', '.join(sorted(unknown))}"
        )
    out: Dict[str, Any] = {
        "layer": None,
        "layers": None,  # "all" or "Name1,Name2" → multi-layer directory
        "allow_flip": False,
        "index_size": "w",
        "firstgid": None,
        "tileset": None,  # optional label for docs / future cross-check
    }
    if "layer" in options:
        out["layer"] = str(options["layer"])
    if "layers" in options:
        out["layers"] = str(options["layers"])
    if out["layer"] is not None and out["layers"] is not None:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"tilemap layer= and layers= are mutually exclusive"
        )
    if "allow_flip" in options:
        out["allow_flip"] = _parse_bool_opt(options["allow_flip"], line_no, "allow_flip")
    if "index_size" in options:
        sz = str(options["index_size"]).lower()
        if sz not in ("b", "w", "byte", "word"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"tilemap index_size must be b|w (got {sz!r})"
            )
        out["index_size"] = "b" if sz in ("b", "byte") else "w"
    if "firstgid" in options:
        out["firstgid"] = _parse_int_opt(options["firstgid"], line_no, "firstgid")
    if "tileset" in options:
        out["tileset"] = str(options["tileset"])
    return out


def _fingerprint(kind: str, label: str, options: Dict[str, Any], source_path: str) -> str:
    payload = {
        "kind": kind,
        "label": label,
        "options": options,
        "source": os.path.basename(source_path),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _meta_path(gen_path: Path) -> Path:
    return gen_path.with_suffix(gen_path.suffix + ".import.json")


def _tool_mtimes(kind: str) -> List[float]:
    tools = _tools_dir()
    paths = [Path(__file__)]
    if kind == "bob":
        paths.append(tools / "bob_importer.py")
    elif kind == "sprite":
        paths.append(tools / "sprite_importer.py")
    elif kind == "atlas":
        paths.append(tools / "texturepacker_atlas_importer.py")
        paths.append(tools / "bob_importer.py")
    elif kind == "tileset":
        paths.append(tools / "tile_importer.py")
        paths.append(tools / "bob_importer.py")
    elif kind == "tilemap":
        paths.append(tools / "tiled_map_importer.py")
    elif kind == "font":
        paths.append(tools / "c64_font_converter.py")
    elif kind == "music":
        pass  # no external tool; fingerprint covers source + this module
    elif kind == "sound":
        paths.append(tools / "extract_8svx.py")
    elif kind == "image":
        paths.append(tools / "image_importer.py")
        paths.append(tools / "amiga_palette.py")
        paths.append(tools / "iff_importer.py")
    else:
        paths.append(tools / "amiga_palette.py")
    mtimes = []
    for p in paths:
        try:
            mtimes.append(p.stat().st_mtime)
        except OSError:
            mtimes.append(0.0)
    return mtimes


def _png_size(source_path: Path) -> Tuple[int, int]:
    from PIL import Image

    with Image.open(str(source_path)) as img:
        return img.size


def _require_sprite_width(source_path: Path, line_no: int) -> None:
    """Hardware sprites are one DMA channel: exactly 16 pixels wide."""
    w, h = _png_size(source_path)
    if w != SPRITE_WIDTH_PX:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"hardware sprite PNG must be exactly {SPRITE_WIDTH_PX} pixels wide "
            f"(got {w}x{h} from {source_path.name}); "
            f"resize or crop the source — #import will not stretch it"
        )


def _cache_is_fresh(
    gen_path: Path,
    source_path: Path,
    kind: str,
    fingerprint: str,
) -> bool:
    if not gen_path.is_file():
        return False
    meta = _meta_path(gen_path)
    if not meta.is_file():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("fingerprint") != fingerprint:
        return False
    try:
        gen_mtime = gen_path.stat().st_mtime
        src_mtime = source_path.stat().st_mtime
    except OSError:
        return False
    if gen_mtime < src_mtime:
        return False
    for tm in _tool_mtimes(kind):
        if gen_mtime < tm:
            return False
    return True


def _write_cache_meta(gen_path: Path, fingerprint: str, kind: str, label: str) -> None:
    meta = {
        "fingerprint": fingerprint,
        "kind": kind,
        "label": label,
    }
    _meta_path(gen_path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _ensure_pillow() -> None:
    try:
        from PIL import Image  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "Pillow is required for #import (pip install pillow)"
        ) from exc


def _generate_font(
    source_path: Path, label: str, gen_path: Path, line_no: int = 0
) -> None:
    font = _load_tool("c64_font_converter", "c64_font_converter.py")
    try:
        asm = font.export_font_asm(str(source_path), label)
    except ValueError as exc:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: {exc}"
        ) from exc
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import font as {label}\n{asm}",
        encoding="utf-8",
    )


def _incbin_path(target: Path) -> str:
    """Absolute path for incbin.

    vasm resolves ``incbin`` relative to the *main* source file (or cwd), not the
    INCLUDEd fragment. Absolute paths keep music/sound assets findable regardless
    of ``-o`` / ``--asset-outdir`` layout.
    """
    return str(target.resolve()).replace(os.sep, "/")


def _generate_music(source_path: Path, label: str, gen_path: Path) -> None:
    """Emit CHIP DATA_C fragment with XDEF <label>__data and incbin of the MOD."""
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    inc = _incbin_path(source_path)
    asm = (
        f"; Auto-generated by #import music as {label}\n"
        f"\tSECTION\tmusic_data,DATA_C\n"
        f"\tXDEF\t{label}__data\n"
        f"{label}__data:\n"
        f'\tincbin\t"{inc}"\n'
    )
    gen_path.write_text(asm, encoding="utf-8")


def _generate_sound(
    source_path: Path,
    label: str,
    options: Dict[str, Any],
    gen_path: Path,
    line_no: int = 0,
) -> None:
    """Emit CHIP sample fragment: dc.w 0 + raw PCM + <label>__len EQU (words)."""
    suffix = source_path.suffix.lower()
    gen_path.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".raw":
        raw_path = source_path
    elif suffix in (".iff", ".8svx"):
        raw_path = gen_path.parent / f"{label}.raw"
        extract = _load_tool("extract_8svx", "extract_8svx.py")
        try:
            extract.extract_8svx(str(source_path), str(raw_path))
        except Exception as exc:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import sound 8SVX extract failed: {exc}"
            ) from exc
    else:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"#import sound expects .raw, .iff, or .8svx (got {source_path.name})"
        )

    # options retained on AssetImport for sfx_table emission (period/vol/pri/channel)
    _ = options
    inc = _incbin_path(raw_path)
    asm = (
        f"; Auto-generated by #import sound as {label}\n"
        f"\tSECTION\tsound_data,DATA_C\n"
        f"\tXDEF\t{label}__data\n"
        f"\tXDEF\t{label}__len\n"
        f"{label}__data:\n"
        f"\tdc.w\t0\t\t; ptplayer requires leading zero word\n"
        f'\tincbin\t"{inc}"\n'
        f"\teven\n"
        f"{label}__len\tEQU\t(*-{label}__data)/2\n"
    )
    gen_path.write_text(asm, encoding="utf-8")


def _generate_bob(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> None:
    bob = _load_tool("bob_importer", "bob_importer.py")
    use_dither = options["dither"] == "fs"
    asm = bob.export_bob_asm(
        str(source_path),
        label,
        planes=int(options["planes"]),
        use_dither=use_dither,
        add_word=bool(options["add_word"]),
    )
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import bob as {label}\n{asm}\n",
        encoding="utf-8",
    )


def _generate_palette(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> None:
    ap = _load_tool("amiga_palette", "amiga_palette.py")
    result = ap.convert_image(
        source_path,
        colors=int(options["colors"]),
        dither=str(options["dither"]),
        index0=str(options["index0"]),
        requantize=bool(options["requantize"]),
    )
    ap.write_palette_asm(
        gen_path,
        label,
        result["palette_words"],
        source_name=source_path.name,
        num_colors=int(options["colors"]),
        section="data,DATA",
    )


def _generate_image(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> List[str]:
    """Emit full-screen picture `.s` with `label` bitmap + `label_palette`."""
    img = _load_tool("image_importer", "image_importer.py")
    asm = img.export_picture_asm(
        str(source_path),
        label,
        mode=str(options["mode"]),
        dither=str(options["dither"]),
    )
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import image as {label}\n{asm}\n",
        encoding="utf-8",
    )
    return [label, f"{label}_palette"]


def _generate_sprite(source_path: Path, label: str, options: Dict[str, Any], gen_path: Path) -> None:
    sprite = _load_tool("sprite_importer", "sprite_importer.py")
    use_dither = options["dither"] == "fs"
    asm = sprite.export_sprite_asm(
        str(source_path),
        label,
        vstart=int(options["vstart"]),
        vstop=int(options["vstop"]),
        use_dither=use_dither,
    )
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import sprite as {label}\n{asm}\n",
        encoding="utf-8",
    )


def _atlas_palette_label(prefix: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9_]+', '_', prefix)
    safe = re.sub(r'_+', '_', safe).strip('_') or 'atlas'
    if safe[0].isdigit():
        safe = '_' + safe
    return f"{safe}_palette"


def _resolve_atlas_png(
    xml_path: Path,
    options: Dict[str, Any],
    current_dir: str,
    line_no: int,
) -> Path:
    override = options.get("atlas_png")
    if override:
        raw = str(override)
        if os.path.isabs(raw):
            png = Path(os.path.normpath(raw))
        else:
            # Prefer beside the XML, then relative to the including .has dir.
            beside_xml = xml_path.parent / raw
            png = beside_xml if beside_xml.is_file() else Path(
                os.path.normpath(os.path.join(current_dir, raw))
            )
        if not png.is_file():
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import atlas atlas_png not found: {png}"
            )
        return png

    atlas = _load_tool("texturepacker_atlas_importer", "texturepacker_atlas_importer.py")
    image_path_attr, _ = atlas.parse_atlas_xml(str(xml_path))
    png = xml_path.parent / image_path_attr
    if not png.is_file():
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"#import atlas PNG not found: {png} "
            f"(from XML imagePath={image_path_attr!r}; use atlas_png=...)"
        )
    return png


def _generate_atlas(
    xml_path: Path,
    atlas_png: Path,
    label: str,
    options: Dict[str, Any],
    outdir: Path,
    force: bool,
) -> Tuple[Path, List[str]]:
    """
    Run TexturePacker → shared-palette BOBs + master include.

    Returns (master_include_path, all_labels).
    """
    atlas = _load_tool("texturepacker_atlas_importer", "texturepacker_atlas_importer.py")
    outdir.mkdir(parents=True, exist_ok=True)
    palette_label = _atlas_palette_label(label)
    shared_palette_label = palette_label if options["shared_palette"] else None
    palette_path = outdir / f"{palette_label}.s"
    master_path = outdir / f"{label}_atlas.s"

    # Quiet the tool's progress prints during compile.
    buf = io.StringIO()
    os.environ.setdefault("HAS_HIDE_IMPORT_METADATA", "1")
    with contextlib.redirect_stdout(buf):
        results, shared_palette, _has_t = atlas.process_atlas(
            xml_path=str(xml_path),
            atlas_png_override=str(atlas_png),
            label_prefix=label,
            planes=int(options["planes"]),
            use_dither=(options["dither"] == "fs"),
            add_word=bool(options["add_word"]),
            restore_original_size=bool(options["restore_original_size"]),
            out_dir=str(outdir),
            only_sprites=options.get("sprites"),
            force=force,
            deduplicate_frames=bool(options["dedupe"]),
            shared_palette_label=shared_palette_label,
        )

        if not results:
            raise RuntimeError(f"#import atlas produced no BOBs from {xml_path.name}")

        frame_labels: List[str] = []
        seen = set()
        for _path, frame_label, _meta in results:
            if frame_label not in seen:
                seen.add(frame_label)
                frame_labels.append(frame_label)

        labels: List[str] = []
        if options["shared_palette"]:
            atlas.write_shared_palette_file(
                palette_path, palette_label, shared_palette, int(options["planes"])
            )
            labels.append(palette_label)

        atlas.write_master_include(
            results,
            master_path,
            atlas_name=xml_path.stem,
            shared_palette_file=palette_path if options["shared_palette"] else None,
        )
        labels.extend(frame_labels)
    return master_path, labels


def _write_cache_meta_full(
    gen_path: Path,
    fingerprint: str,
    kind: str,
    label: str,
    labels: Optional[List[str]] = None,
) -> None:
    meta = {
        "fingerprint": fingerprint,
        "kind": kind,
        "label": label,
        "labels": list(labels) if labels else [label],
    }
    _meta_path(gen_path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _read_cached_labels(gen_path: Path) -> List[str]:
    meta = _meta_path(gen_path)
    if not meta.is_file():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    labels = data.get("labels")
    if isinstance(labels, list) and labels:
        return [str(x) for x in labels]
    lab = data.get("label")
    return [str(lab)] if lab else []


def _resolve_match_palette_asm(
    match_palette: str,
    outdir: Path,
    line_no: int,
) -> Tuple[Path, str]:
    """
    Resolve match_palette=<label> to a generated palette .s under asset outdir.

    Accepts `hero_palette` or `hero` (tries hero_palette.s).
    Returns (path, palette_label_in_file).
    """
    name = match_palette.strip()
    if not name:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: match_palette= is empty"
        )
    candidates = [
        (outdir / f"{name}.s", name),
        (outdir / f"{name}_palette.s", f"{name}_palette"),
    ]
    # Prefer exact name.s when it exists.
    for path, pal_label in candidates:
        if path.is_file():
            return path, pal_label
    raise SyntaxError(
        f"Preprocessor error at line {line_no}: "
        f"match_palette={match_palette!r} not found under {outdir} "
        f"(import the atlas/bob/palette that defines it first)"
    )


def _generate_tileset(
    source_path: Path,
    label: str,
    options: Dict[str, Any],
    gen_path: Path,
    outdir: Path,
    line_no: int,
) -> None:
    tile = _load_tool("tile_importer", "tile_importer.py")
    match_path = None
    match_label = None
    omit_palette = False
    if options.get("match_palette"):
        match_path_p, match_label = _resolve_match_palette_asm(
            str(options["match_palette"]), outdir, line_no
        )
        match_path = str(match_path_p)
        omit_palette = True
    try:
        asm = tile.export_tileset_asm(
            str(source_path),
            label,
            tile_width=int(options["tile_w"]),
            tile_height=int(options["tile_h"]),
            planes=int(options["planes"]),
            use_dither=(options["dither"] == "fs"),
            match_bob_palette_from_asm=match_path,
            match_bob_palette_label=match_label,
            strict_palette_match=bool(options["strict_palette"]),
            omit_palette=omit_palette,
        )
    except ValueError as exc:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: #import tileset: {exc}"
        ) from exc
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import tileset as {label}\n{asm}\n",
        encoding="utf-8",
    )


def _generate_tilemap(
    source_path: Path,
    label: str,
    options: Dict[str, Any],
    gen_path: Path,
    line_no: int,
) -> List[str]:
    tmap = _load_tool("tiled_map_importer", "tiled_map_importer.py")
    try:
        asm, meta = tmap.export_tilemap_asm(
            str(source_path),
            label,
            layer=options.get("layer"),
            layers=options.get("layers"),
            allow_flip=bool(options.get("allow_flip")),
            index_size=str(options.get("index_size") or "w"),
            firstgid=options.get("firstgid"),
        )
    except ValueError as exc:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: #import tilemap: {exc}"
        ) from exc
    gen_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.write_text(
        f"; Auto-generated by #import tilemap as {label}\n{asm}",
        encoding="utf-8",
    )
    labels = [label]
    if meta.get("multi_layer"):
        for layer_meta in meta.get("layer_meta") or []:
            layer_label = layer_meta.get("label")
            if layer_label and layer_label not in labels:
                labels.append(str(layer_label))
    return labels


def process_import(
    kind: str,
    path_raw: str,
    label: str,
    options: Dict[str, Any],
    *,
    current_dir: str,
    asset_outdir: str,
    force: bool = False,
    line_no: int = 0,
) -> AssetImport:
    """Resolve, convert (or reuse cache), and return an AssetImport record."""
    if kind == "bob":
        norm = _normalize_bob_options(options, line_no)
    elif kind == "palette":
        norm = _normalize_palette_options(options, line_no)
    elif kind == "sprite":
        norm = _normalize_sprite_options(options, line_no)
    elif kind == "atlas":
        norm = _normalize_atlas_options(options, line_no)
    elif kind == "tileset":
        norm = _normalize_tileset_options(options, line_no)
    elif kind == "tilemap":
        norm = _normalize_tilemap_options(options, line_no)
    elif kind == "font":
        norm = _normalize_font_options(options, line_no)
    elif kind == "music":
        norm = _normalize_music_options(options, line_no)
    elif kind == "sound":
        norm = _normalize_sound_options(options, line_no)
    elif kind == "image":
        norm = _normalize_image_options(options, line_no)
    else:
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: "
            f"unknown #import kind '{kind}' "
            f"(expected bob|palette|sprite|atlas|tileset|tilemap|font|music|sound|image)"
        )

    if os.path.isabs(path_raw):
        source_path = Path(os.path.normpath(path_raw))
    else:
        source_path = Path(os.path.normpath(os.path.join(current_dir, path_raw)))

    if not source_path.is_file():
        raise SyntaxError(
            f"Preprocessor error at line {line_no}: #import file not found: {source_path}"
        )

    outdir = Path(asset_outdir)
    if not outdir.is_absolute():
        outdir = Path(os.getcwd()) / outdir

    extra_sources: List[Path] = []
    atlas_png = None  # type: Optional[Path]
    if kind == "atlas":
        if source_path.suffix.lower() != ".xml":
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import atlas expects a TexturePacker .xml file (got {source_path.name})"
            )
        atlas_png = _resolve_atlas_png(source_path, norm, current_dir, line_no)
        extra_sources.append(atlas_png)
        gen_path = outdir / f"{label}_atlas.s"
        fingerprint = _fingerprint(
            kind, label, {**norm, "_atlas_png": atlas_png.name}, str(source_path)
        )
    elif kind == "tilemap":
        if source_path.suffix.lower() not in (".tmx", ".json"):
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import tilemap expects a Tiled .tmx or .json file "
                f"(got {source_path.name})"
            )
        gen_path = outdir / f"{label}.s"
        fingerprint = _fingerprint(kind, label, norm, str(source_path))
    elif kind == "font":
        if source_path.suffix.lower() not in _FONT_SUFFIXES:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import font expects a C64 charset .bin, .s, or .asm file "
                f"(got {source_path.name})"
            )
        gen_path = outdir / f"{label}.s"
        fingerprint = _fingerprint(kind, label, norm, str(source_path))
    elif kind == "music":
        if source_path.suffix.lower() != ".mod":
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import music expects a ProTracker .mod file "
                f"(got {source_path.name})"
            )
        gen_path = outdir / f"{label}_music.s"
        # _incbin marks absolute-path emit style (cache bust if that changes).
        fingerprint = _fingerprint(
            kind, label, {**norm, "_incbin": "abs"}, str(source_path)
        )
    elif kind == "sound":
        if source_path.suffix.lower() not in _SOUND_SUFFIXES:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import sound expects a .raw, .iff, or .8svx file "
                f"(got {source_path.name})"
            )
        gen_path = outdir / f"{label}.s"
        fingerprint = _fingerprint(
            kind, label, {**norm, "_incbin": "abs"}, str(source_path)
        )
    elif kind == "image":
        if source_path.suffix.lower() not in _IMAGE_SUFFIXES:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: "
                f"#import image expects PNG/JPEG/GIF/BMP/IFF "
                f"(got {source_path.name})"
            )
        gen_path = outdir / f"{label}.s"
        fingerprint = _fingerprint(kind, label, norm, str(source_path))
    else:
        gen_path = outdir / f"{label}.s"
        fingerprint = _fingerprint(kind, label, norm, str(source_path))

    if kind == "tileset" and norm.get("match_palette"):
        # Invalidate cache when the matched palette file changes.
        try:
            pal_path, _ = _resolve_match_palette_asm(
                str(norm["match_palette"]), outdir, line_no
            )
            extra_sources.append(pal_path)
            fingerprint = _fingerprint(
                kind, label, {**norm, "_match": pal_path.name}, str(source_path)
            )
        except SyntaxError:
            # Palette may not exist yet on first parse of a bad order; still try generate.
            pass

    fresh = (not force) and _cache_is_fresh(gen_path, source_path, kind, fingerprint)
    if fresh and extra_sources:
        try:
            gen_mtime = gen_path.stat().st_mtime
            for extra in extra_sources:
                if gen_mtime < extra.stat().st_mtime:
                    fresh = False
                    break
        except OSError:
            fresh = False

    labels: List[str] = []
    if fresh:
        labels = _read_cached_labels(gen_path)
        # IFF/8SVX sound also needs the converted .raw beside the fragment.
        if kind == "sound" and source_path.suffix.lower() in (".iff", ".8svx"):
            raw_beside = gen_path.parent / f"{label}.raw"
            if not raw_beside.is_file():
                fresh = False
                labels = []
    if not fresh:
        # tilemap / font / music / sound do not need Pillow; others do.
        if kind not in ("tilemap", "font", "music", "sound"):
            _ensure_pillow()
        if kind == "atlas":
            assert atlas_png is not None
            master, labels = _generate_atlas(
                source_path, atlas_png, label, norm, outdir, force=True
            )
            gen_path = master
        elif kind == "sprite":
            _require_sprite_width(source_path, line_no)
            _generate_sprite(source_path, label, norm, gen_path)
            labels = [label]
        elif kind == "bob":
            _generate_bob(source_path, label, norm, gen_path)
            labels = [label]
        elif kind == "palette":
            _generate_palette(source_path, label, norm, gen_path)
            labels = [label]
        elif kind == "tileset":
            _generate_tileset(source_path, label, norm, gen_path, outdir, line_no)
            labels = [label]
        elif kind == "tilemap":
            labels = _generate_tilemap(source_path, label, norm, gen_path, line_no)
        elif kind == "font":
            _generate_font(source_path, label, gen_path, line_no)
            labels = [label]
        elif kind == "music":
            _generate_music(source_path, label, gen_path)
            labels = [label]
        elif kind == "sound":
            _generate_sound(source_path, label, norm, gen_path, line_no)
            labels = [label]
        elif kind == "image":
            labels = _generate_image(source_path, label, norm, gen_path)
        else:
            raise SyntaxError(
                f"Preprocessor error at line {line_no}: unhandled #import kind {kind!r}"
            )
        _write_cache_meta_full(gen_path, fingerprint, kind, label, labels)

    if not labels:
        labels = [label]

    return AssetImport(
        kind=kind,
        source_path=str(source_path.resolve()),
        label=label,
        options=norm,
        gen_path=str(gen_path.resolve()),
        labels=labels,
    )


def include_path_for_output(gen_path: str, output_path: Optional[str] = None) -> str:
    """Path string suitable for vasm INCLUDE relative to the output .s when possible."""
    gen = Path(gen_path).resolve()
    if output_path:
        try:
            rel = os.path.relpath(str(gen), start=str(Path(output_path).resolve().parent))
            return rel.replace(os.sep, "/")
        except ValueError:
            pass
    try:
        rel = os.path.relpath(str(gen), start=os.getcwd())
        return rel.replace(os.sep, "/")
    except ValueError:
        return str(gen).replace(os.sep, "/")


def iter_audio_imports(
    assets: Optional[Iterable[AssetImport]],
    kind: str,
) -> Iterator[AssetImport]:
    """Yield music or sound AssetImport records in source order."""
    if kind not in _AUDIO_KINDS:
        raise ValueError(f"iter_audio_imports kind must be music|sound, got {kind!r}")
    for asset in assets or []:
        if asset.kind == kind:
            yield asset


def assign_audio_ids(assets: Optional[Iterable[AssetImport]]) -> Dict[str, int]:
    """Map import as-label → table index (separate counters per music/sound)."""
    ids: Dict[str, int] = {}
    music_i = 0
    sound_i = 0
    for asset in assets or []:
        if asset.kind == "music":
            ids[asset.label] = music_i
            music_i += 1
        elif asset.kind == "sound":
            ids[asset.label] = sound_i
            sound_i += 1
    return ids


def generate_audio_tables_asm(assets: Optional[Iterable[AssetImport]]) -> Optional[str]:
    """Build music_table + sfx_table assembly when any music/sound import exists.

    Always emits both XDEF labels (empty table body is fine) so linking
    audio.s / ptplayer.s does not fail on a missing symbol. sfx_table layout
    matches lib/ptplayer.i (ptr.l, len.w, period.w, vol.w, channel.b, pri.b).
    """
    asset_list = list(assets or [])
    music = [a for a in asset_list if a.kind == "music"]
    sound = [a for a in asset_list if a.kind == "sound"]
    if not music and not sound:
        return None

    lines: List[str] = [
        "; Auto-generated audio tables from #import music / #import sound",
        "\tSECTION\taudio_tables,DATA",
        "\tXDEF\tmusic_table",
        "\tXDEF\tsfx_table",
        "",
        "music_table:",
    ]
    if music:
        for a in music:
            lines.append(f"\tdc.l\t{a.label}__data")
    else:
        lines.append("\t; (no #import music)")

    lines.append("")
    lines.append("sfx_table:")
    if sound:
        for a in sound:
            opts = a.options or {}
            period = int(opts.get("period", 443))
            vol = int(opts.get("vol", 32))
            pri = int(opts.get("pri", 64))
            channel = int(opts.get("channel", -1))
            lines.append(f"\t; {a.label}")
            lines.append(f"\tdc.l\t{a.label}__data")
            lines.append(f"\tdc.w\t{a.label}__len")
            lines.append(f"\tdc.w\t{period}")
            lines.append(f"\tdc.w\t{vol}")
            lines.append(f"\tdc.b\t{channel}")
            lines.append(f"\tdc.b\t{pri}")
    else:
        lines.append("\t; (no #import sound)")

    lines.append("")
    return "\n".join(lines) + "\n"


def write_audio_tables(
    outdir: Union[str, Path],
    assets: Optional[Iterable[AssetImport]],
) -> Optional[Path]:
    """Write ``audio_tables.s`` under ``outdir``; return path or None if unused."""
    asm = generate_audio_tables_asm(assets)
    if asm is None:
        return None
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "audio_tables.s"
    path.write_text(asm, encoding="utf-8")
    return path
