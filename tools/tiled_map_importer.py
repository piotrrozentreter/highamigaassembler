#!/usr/bin/env python3
"""
Tiled map importer for HAS / Amiga.

Reads a Tiled orthogonal map (TMX or JSON) and emits a compact index grid.

Single-layer (default / layer=NAME):

    <label>:
        DC.W <width>, <height>
        DC.W <tile0>, <tile1>, ...   ; row-major, 0-based local index
                                     ; empty → 0

Multi-layer (layers=all or layers=Name1,Name2), bottom → top:

    <label>:
        DC.W <width>, <height>
        DC.W <layer_count>
        DC.W <tilewidth>, <tileheight>
        DC.L <label>__l0             ; bottom
        DC.L <label>__l1
    <label>__l0:
        DC.W <firstgid>
        DC.W <idx>...                ; 1-based local index (empty → 0)

Empty / invalid cells become 0. Flip flags are rejected unless --allow-flip
(then bits are stripped). Layer selection via --layer NAME (default: first
tile layer) or --layers all|Name1,Name2.
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# Tiled GID flip flags (high bits)
_FLIP_H = 0x80000000
_FLIP_V = 0x40000000
_FLIP_D = 0x20000000
_FLIP_MASK = _FLIP_H | _FLIP_V | _FLIP_D
_GID_MAX = 0x1FFFFFFF


def _decode_csv(data: str) -> List[int]:
    text = data.replace("\n", ",").replace(" ", "")
    parts = [p for p in text.split(",") if p != ""]
    return [int(p) for p in parts]


def _decode_base64(data: str, encoding: str, expected: int) -> List[int]:
    raw = base64.b64decode(data.strip())
    enc = (encoding or "csv").lower()
    if enc in ("base64", ""):
        pass
    elif enc == "zlib" or enc == "gzip":
        # Tiled uses zlib for "zlib"; gzip wraps zlib differently — try zlib first.
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, wbits=16 + zlib.MAX_WBITS)
    else:
        raise ValueError(f"Unsupported layer encoding: {encoding!r}")

    if len(raw) != expected * 4:
        raise ValueError(
            f"Layer data size mismatch: got {len(raw)} bytes, expected {expected * 4}"
        )
    return list(struct.unpack("<" + "I" * expected, raw))


def _gids_to_indices(
    gids: Sequence[int],
    firstgid: int,
    *,
    allow_flip: bool,
    one_based: bool = False,
) -> List[int]:
    out: List[int] = []
    for gid in gids:
        flags = gid & _FLIP_MASK
        if flags and not allow_flip:
            raise ValueError(
                f"Tile GID 0x{gid:08X} has flip flags; re-export without "
                f"flipped tiles or pass allow_flip"
            )
        clear = gid & ~_FLIP_MASK
        if clear == 0:
            out.append(0)
            continue
        idx = clear - firstgid
        if idx < 0:
            out.append(0)
        elif one_based:
            out.append(int(idx) + 1)
        else:
            out.append(int(idx))
    return out


def _parse_tmx(path: Path) -> Dict[str, Any]:
    tree = ET.parse(str(path))
    root = tree.getroot()
    width = int(root.get("width", 0))
    height = int(root.get("height", 0))
    tilewidth = int(root.get("tilewidth", 0))
    tileheight = int(root.get("tileheight", 0))
    orientation = root.get("orientation", "orthogonal")

    tilesets = []
    for ts in root.findall("tileset"):
        tilesets.append({
            "firstgid": int(ts.get("firstgid", 1)),
            "name": ts.get("name", ""),
            "tilecount": int(ts.get("tilecount", 0)) if ts.get("tilecount") else None,
            "source": ts.get("source"),
        })

    layers = []
    for layer in root.findall("layer"):
        data_el = layer.find("data")
        if data_el is None:
            continue
        encoding = data_el.get("encoding", "csv")
        compression = data_el.get("compression")
        text = (data_el.text or "").strip()
        enc = compression or encoding
        layers.append({
            "name": layer.get("name", ""),
            "width": int(layer.get("width", width)),
            "height": int(layer.get("height", height)),
            "encoding": enc,
            "data": text,
        })

    return {
        "format": "tmx",
        "width": width,
        "height": height,
        "tilewidth": tilewidth,
        "tileheight": tileheight,
        "orientation": orientation,
        "tilesets": tilesets,
        "layers": layers,
    }


def _parse_json_map(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    layers = []
    for layer in data.get("layers", []):
        if layer.get("type") != "tilelayer":
            continue
        enc = layer.get("compression") or layer.get("encoding") or "csv"
        if "data" in layer and isinstance(layer["data"], list):
            layers.append({
                "name": layer.get("name", ""),
                "width": int(layer.get("width", data.get("width", 0))),
                "height": int(layer.get("height", data.get("height", 0))),
                "encoding": "array",
                "data": layer["data"],
            })
        else:
            layers.append({
                "name": layer.get("name", ""),
                "width": int(layer.get("width", data.get("width", 0))),
                "height": int(layer.get("height", data.get("height", 0))),
                "encoding": enc,
                "data": layer.get("data", ""),
            })
    tilesets = []
    for ts in data.get("tilesets", []):
        tilesets.append({
            "firstgid": int(ts.get("firstgid", 1)),
            "name": ts.get("name", ""),
            "tilecount": ts.get("tilecount"),
            "source": ts.get("source"),
        })
    return {
        "format": "json",
        "width": int(data.get("width", 0)),
        "height": int(data.get("height", 0)),
        "tilewidth": int(data.get("tilewidth", 0)),
        "tileheight": int(data.get("tileheight", 0)),
        "orientation": data.get("orientation", "orthogonal"),
        "tilesets": tilesets,
        "layers": layers,
    }


def load_tiled_map(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    if p.suffix.lower() == ".json":
        return _parse_json_map(p)
    return _parse_tmx(p)


def _select_layer(layers: List[Dict], layer_name: Optional[str]) -> Dict:
    if not layers:
        raise ValueError("Map has no tile layers")
    if layer_name:
        for layer in layers:
            if layer.get("name") == layer_name:
                return layer
        names = ", ".join(repr(l.get("name")) for l in layers)
        raise ValueError(f"Layer {layer_name!r} not found (available: {names})")
    return layers[0]


def _select_layers(
    layers: List[Dict],
    layers_opt: Union[str, Sequence[str]],
) -> List[Dict]:
    if not layers:
        raise ValueError("Map has no tile layers")
    if isinstance(layers_opt, str):
        raw = layers_opt.strip()
        if raw.lower() == "all":
            return list(layers)
        names = [n.strip() for n in raw.split(",") if n.strip()]
    else:
        names = [str(n).strip() for n in layers_opt if str(n).strip()]
    if not names:
        raise ValueError("layers= requires 'all' or a comma-separated name list")
    by_name = {str(l.get("name")): l for l in layers}
    selected: List[Dict] = []
    for name in names:
        if name not in by_name:
            available = ", ".join(repr(l.get("name")) for l in layers)
            raise ValueError(f"Layer {name!r} not found (available: {available})")
        selected.append(by_name[name])
    return selected


def _layer_gids(layer: Dict, width: int, height: int) -> List[int]:
    expected = width * height
    enc = layer.get("encoding", "csv")
    data = layer.get("data")
    if enc == "array":
        gids = [int(x) for x in data]
    elif enc in ("csv", None):
        gids = _decode_csv(str(data))
    else:
        gids = _decode_base64(str(data), str(enc), expected)
    if len(gids) != expected:
        raise ValueError(
            f"Layer '{layer.get('name')}' has {len(gids)} tiles, "
            f"expected {expected} ({width}x{height})"
        )
    return gids


def _tileset_ranges(tilesets: Sequence[Dict[str, Any]]) -> List[Tuple[int, int, Dict]]:
    """Return (firstgid, lastgid_inclusive, tileset) sorted by firstgid."""
    if not tilesets:
        return []
    sorted_ts = sorted(tilesets, key=lambda t: int(t["firstgid"]))
    ranges: List[Tuple[int, int, Dict]] = []
    for i, ts in enumerate(sorted_ts):
        fg = int(ts["firstgid"])
        tc = ts.get("tilecount")
        if tc:
            last = fg + int(tc) - 1
        elif i + 1 < len(sorted_ts):
            last = int(sorted_ts[i + 1]["firstgid"]) - 1
        else:
            last = _GID_MAX
        ranges.append((fg, last, ts))
    return ranges


def _resolve_layer_firstgid(
    gids: Sequence[int],
    tilesets: Sequence[Dict[str, Any]],
    *,
    allow_flip: bool,
    override: Optional[int] = None,
) -> int:
    """Pick the single tileset firstgid that owns all non-empty GIDs in a layer."""
    clear: List[int] = []
    for gid in gids:
        flags = gid & _FLIP_MASK
        if flags and not allow_flip:
            raise ValueError(
                f"Tile GID 0x{gid:08X} has flip flags; re-export without "
                f"flipped tiles or pass allow_flip"
            )
        c = gid & ~_FLIP_MASK
        if c != 0:
            clear.append(c)

    if not tilesets:
        if override is not None:
            return int(override)
        return 1
    if not clear:
        if override is not None:
            return int(override)
        return min(int(ts["firstgid"]) for ts in tilesets)

    ranges = _tileset_ranges(tilesets)
    owners: List[int] = []
    for gid in clear:
        matched = None
        for fg, last, _ts in ranges:
            if fg <= gid <= last:
                matched = fg
                break
        if matched is None:
            raise ValueError(
                f"GID {gid} does not fall in any tileset range"
            )
        owners.append(matched)

    unique = set(owners)
    if len(unique) > 1:
        raise ValueError(
            f"Layer mixes tiles from multiple tilesets (firstgids={sorted(unique)}); "
            f"split into separate layers or use one tileset per layer"
        )
    resolved = owners[0]
    if override is not None and int(override) != resolved:
        raise ValueError(
            f"firstgid override {int(override)} does not match layer tileset "
            f"firstgid {resolved}"
        )
    if override is not None:
        return int(override)
    return resolved


def _emit_index_rows(
    lines: List[str],
    indices: Sequence[int],
    lw: int,
    lh: int,
    index_size: str,
) -> None:
    if index_size == "w":
        for y in range(lh):
            row = indices[y * lw:(y + 1) * lw]
            for x0 in range(0, lw, 8):
                chunk = row[x0:x0 + 8]
                ops = ", ".join(f"${v & 0xFFFF:04X}" for v in chunk)
                lines.append(f"\tDC.W\t{ops}\t; y={y} x={x0}")
    else:
        for y in range(lh):
            row = indices[y * lw:(y + 1) * lw]
            for x0 in range(0, lw, 16):
                chunk = row[x0:x0 + 16]
                ops = ", ".join(f"${v & 0xFF:02X}" for v in chunk)
                lines.append(f"\tDC.B\t{ops}\t; y={y} x={x0}")
        lines.append("\teven")


def _export_single_layer(
    map_path: str,
    out_label: str,
    info: Dict[str, Any],
    layer_info: Dict[str, Any],
    *,
    allow_flip: bool,
    index_size: str,
    firstgid: Optional[int],
) -> Tuple[str, Dict[str, Any]]:
    width = int(info["width"])
    height = int(info["height"])
    lw = int(layer_info.get("width", width))
    lh = int(layer_info.get("height", height))
    gids = _layer_gids(layer_info, lw, lh)

    resolved = _resolve_layer_firstgid(
        gids,
        info["tilesets"],
        allow_flip=allow_flip,
        override=firstgid,
    )

    indices = _gids_to_indices(gids, resolved, allow_flip=allow_flip, one_based=False)

    lines = [
        f"; Auto-generated tilemap from {Path(map_path).name}",
        f"; Layer: {layer_info.get('name')!r}  size={lw}x{lh}  firstgid={resolved}",
        f"; Indices are 0-based into the matched tileset (empty → 0)",
        "\tSECTION tilemap,DATA",
        "\tCNOP\t0,4",
        f"\tXDEF\t{out_label}",
        f"{out_label}:",
        f"\tDC.W\t{lw}, {lh}",
    ]
    _emit_index_rows(lines, indices, lw, lh, index_size)

    meta = {
        "width": lw,
        "height": lh,
        "tilewidth": info.get("tilewidth"),
        "tileheight": info.get("tileheight"),
        "layer": layer_info.get("name"),
        "layers": [layer_info.get("name")],
        "layer_count": 1,
        "multi_layer": False,
        "firstgid": resolved,
        "index_size": index_size,
        "tile_count": len(indices),
    }
    return "\n".join(lines) + "\n", meta


def _export_multi_layer(
    map_path: str,
    out_label: str,
    info: Dict[str, Any],
    selected: List[Dict[str, Any]],
    *,
    allow_flip: bool,
    index_size: str,
    firstgid: Optional[int],
) -> Tuple[str, Dict[str, Any]]:
    width = int(info["width"])
    height = int(info["height"])
    tilewidth = int(info.get("tilewidth") or 0)
    tileheight = int(info.get("tileheight") or 0)
    layer_count = len(selected)

    lines = [
        f"; Auto-generated multi-layer tilemap from {Path(map_path).name}",
        f"; Layers bottom→top ({layer_count}): "
        + ", ".join(repr(l.get("name")) for l in selected),
        f"; Per-layer indices are 1-based local (empty → 0) for skip-on-draw",
        "\tSECTION tilemap,DATA",
        "\tCNOP\t0,4",
        f"\tXDEF\t{out_label}",
    ]
    for i in range(layer_count):
        lines.append(f"\tXDEF\t{out_label}__l{i}")

    lines.extend([
        f"{out_label}:",
        f"\tDC.W\t{width}, {height}",
        f"\tDC.W\t{layer_count}",
        f"\tDC.W\t{tilewidth}, {tileheight}",
    ])
    for i in range(layer_count):
        lines.append(f"\tDC.L\t{out_label}__l{i}")

    layer_metas: List[Dict[str, Any]] = []
    for i, layer_info in enumerate(selected):
        lw = int(layer_info.get("width", width))
        lh = int(layer_info.get("height", height))
        if lw != width or lh != height:
            raise ValueError(
                f"Layer {layer_info.get('name')!r} size {lw}x{lh} "
                f"does not match map {width}x{height}"
            )
        gids = _layer_gids(layer_info, lw, lh)
        resolved = _resolve_layer_firstgid(
            gids,
            info["tilesets"],
            allow_flip=allow_flip,
            override=firstgid,
        )
        indices = _gids_to_indices(
            gids, resolved, allow_flip=allow_flip, one_based=True
        )
        lname = layer_info.get("name")
        lines.append(f"; Layer {i} name={lname!r} firstgid={resolved}")
        lines.append(f"{out_label}__l{i}:")
        lines.append(f"\tDC.W\t{resolved}")
        _emit_index_rows(lines, indices, lw, lh, index_size)
        layer_metas.append({
            "name": lname,
            "index": i,
            "firstgid": resolved,
            "label": f"{out_label}__l{i}",
        })

    meta = {
        "width": width,
        "height": height,
        "tilewidth": tilewidth,
        "tileheight": tileheight,
        "layer": selected[0].get("name") if selected else None,
        "layers": [m["name"] for m in layer_metas],
        "layer_count": layer_count,
        "multi_layer": True,
        "layer_meta": layer_metas,
        "firstgid": layer_metas[0]["firstgid"] if layer_metas else None,
        "index_size": index_size,
        "tile_count": width * height * layer_count,
    }
    return "\n".join(lines) + "\n", meta


def export_tilemap_asm(
    map_path: str,
    out_label: str,
    *,
    layer: Optional[str] = None,
    layers: Optional[Union[str, Sequence[str]]] = None,
    allow_flip: bool = False,
    index_size: str = "w",
    firstgid: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Export a Tiled map to assembly.

    Returns (asm_text, metadata).
    """
    info = load_tiled_map(map_path)
    if info.get("orientation", "orthogonal") != "orthogonal":
        raise ValueError(
            f"Only orthogonal maps are supported (got {info.get('orientation')!r})"
        )

    if index_size not in ("b", "w"):
        raise ValueError("index_size must be 'b' or 'w'")

    if layers is not None and layer is not None:
        raise ValueError("Specify either layer= or layers=, not both")

    if layers is not None:
        selected = _select_layers(info["layers"], layers)
        return _export_multi_layer(
            map_path,
            out_label,
            info,
            selected,
            allow_flip=allow_flip,
            index_size=index_size,
            firstgid=firstgid,
        )

    layer_info = _select_layer(info["layers"], layer)
    return _export_single_layer(
        map_path,
        out_label,
        info,
        layer_info,
        allow_flip=allow_flip,
        index_size=index_size,
        firstgid=firstgid,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Import Tiled TMX/JSON map to HAS assembly")
    ap.add_argument("map", help="Tiled .tmx or .json map")
    ap.add_argument("--label", default=None, help="Output label (default: map stem)")
    ap.add_argument("--layer", default=None, help="Tile layer name (default: first)")
    ap.add_argument(
        "--layers",
        default=None,
        help="Multi-layer export: 'all' or comma-separated names (bottom→top order)",
    )
    ap.add_argument("--allow-flip", action="store_true", help="Strip flip flags instead of erroring")
    ap.add_argument("--index-size", choices=["b", "w"], default="w", help="DC.B or DC.W indices")
    ap.add_argument("--firstgid", type=int, default=None, help="Override tileset firstgid")
    ap.add_argument("--outdir", default=None, help="Output directory")
    args = ap.parse_args()

    src = Path(args.map)
    label = args.label or src.stem.replace("-", "_").replace(" ", "_")
    out_dir = Path(args.outdir) if args.outdir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{label}.s"

    asm, meta = export_tilemap_asm(
        str(src),
        label,
        layer=args.layer,
        layers=args.layers,
        allow_flip=args.allow_flip,
        index_size=args.index_size,
        firstgid=args.firstgid,
    )
    out_file.write_text(asm, encoding="utf-8")
    if meta.get("multi_layer"):
        print(
            f"[tilemap] wrote {out_file} | {meta['width']}x{meta['height']} "
            f"layers={meta['layers']!r} count={meta['layer_count']}"
        )
    else:
        print(
            f"[tilemap] wrote {out_file} | {meta['width']}x{meta['height']} "
            f"layer={meta['layer']!r} firstgid={meta['firstgid']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
