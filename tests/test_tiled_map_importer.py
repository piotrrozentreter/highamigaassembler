"""Unit tests for tools/tiled_map_importer.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import tiled_map_importer as tmap

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "examples" / "tests" / "compiler" / "assets"


def test_export_tmx_csv_indices():
    asm, meta = tmap.export_tilemap_asm(
        str(ASSETS / "mini_map.tmx"),
        "level_map",
        layer="Ground",
    )
    assert meta["width"] == 4
    assert meta["height"] == 3
    assert meta["firstgid"] == 1
    assert "SECTION tilemap,DATA" in asm.replace("\t", " ")
    assert "level_map:" in asm
    assert "DC.W\t4, 3" in asm or "DC.W 4, 3" in asm.replace("\t", " ")
    # GIDs 1,2 → indices 0,1
    assert "$0000" in asm
    assert "$0001" in asm


def test_export_json_array_indices():
    asm, meta = tmap.export_tilemap_asm(
        str(ASSETS / "mini_map.json"),
        "jmap",
        layer="Ground",
        index_size="b",
    )
    assert meta["index_size"] == "b"
    assert "DC.B" in asm
    assert "jmap:" in asm


def test_flip_flags_rejected(tmp_path: Path):
    tmx = tmp_path / "flip.tmx"
    tmx.write_text(
        '<?xml version="1.0"?>\n'
        '<map orientation="orthogonal" width="1" height="1" '
        'tilewidth="16" tileheight="16">\n'
        ' <tileset firstgid="1" name="t" tilewidth="16" tileheight="16"/>\n'
        ' <layer name="L" width="1" height="1">\n'
        '  <data encoding="csv">2147483649</data>\n'  # 0x80000001
        " </layer>\n"
        "</map>\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="flip"):
        tmap.export_tilemap_asm(str(tmx), "m")


def test_allow_flip_strips_flags(tmp_path: Path):
    tmx = tmp_path / "flip.tmx"
    tmx.write_text(
        '<?xml version="1.0"?>\n'
        '<map orientation="orthogonal" width="1" height="1" '
        'tilewidth="16" tileheight="16">\n'
        ' <tileset firstgid="1" name="t" tilewidth="16" tileheight="16"/>\n'
        ' <layer name="L" width="1" height="1">\n'
        '  <data encoding="csv">2147483649</data>\n'
        " </layer>\n"
        "</map>\n",
        encoding="utf-8",
    )
    asm, _ = tmap.export_tilemap_asm(str(tmx), "m", allow_flip=True)
    assert "$0000" in asm  # 1 - firstgid 1 = 0


def test_export_multi_layer_all():
    asm, meta = tmap.export_tilemap_asm(
        str(ASSETS / "mini_map_layers.tmx"),
        "level_map",
        layers="all",
    )
    assert meta["multi_layer"] is True
    assert meta["layer_count"] == 2
    assert meta["layers"] == ["Ground", "Objects"]
    assert meta["width"] == 4 and meta["height"] == 3
    assert meta["tilewidth"] == 16 and meta["tileheight"] == 16
    assert "DC.W\t2" in asm or "DC.W 2" in asm.replace("\t", " ")
    assert "level_map__l0:" in asm
    assert "level_map__l1:" in asm
    assert "DC.L\tlevel_map__l0" in asm or "DC.L level_map__l0" in asm.replace("\t", " ")
    # Ground firstgid=1 → 1-based indices (GID1→1, GID2→2)
    assert meta["layer_meta"][0]["firstgid"] == 1
    # Objects firstgid=10
    assert meta["layer_meta"][1]["firstgid"] == 10
    # 1-based: empty stays 0; first tile of objects is 1
    assert "$0000" in asm
    assert "$0001" in asm


def test_export_layers_name_filter():
    asm, meta = tmap.export_tilemap_asm(
        str(ASSETS / "mini_map_layers.tmx"),
        "m",
        layers="Objects",
    )
    assert meta["layer_count"] == 1
    assert meta["layers"] == ["Objects"]
    assert "m__l0:" in asm
    assert meta["layer_meta"][0]["firstgid"] == 10


def test_mixed_tileset_layer_errors(tmp_path: Path):
    tmx = tmp_path / "mixed.tmx"
    tmx.write_text(
        '<?xml version="1.0"?>\n'
        '<map orientation="orthogonal" width="2" height="1" '
        'tilewidth="16" tileheight="16">\n'
        ' <tileset firstgid="1" name="a" tilewidth="16" tileheight="16" tilecount="2"/>\n'
        ' <tileset firstgid="10" name="b" tilewidth="16" tileheight="16" tilecount="2"/>\n'
        ' <layer name="Bad" width="2" height="1">\n'
        "  <data encoding=\"csv\">1,10</data>\n"
        " </layer>\n"
        "</map>\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="multiple tilesets"):
        tmap.export_tilemap_asm(str(tmx), "m", layers="all")


def test_layer_and_layers_mutually_exclusive():
    with pytest.raises(ValueError, match="either layer= or layers="):
        tmap.export_tilemap_asm(
            str(ASSETS / "mini_map.tmx"),
            "m",
            layer="Ground",
            layers="all",
        )
