"""Smoke tests for 32x32 tile_importer export."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")
from PIL import Image

from tools import tile_importer as tile


def test_export_tileset_32x32(tmp_path: Path):
    png = tmp_path / "grid32.png"
    # 2x1 tiles of 32x32
    img = Image.new("RGB", (64, 32), (0, 0, 0))
    for y in range(32):
        for x in range(32):
            img.putpixel((x, y), (255, 0, 0))
            img.putpixel((x + 32, y), (0, 255, 0))
    img.save(png)

    asm = tile.export_tileset_asm(
        str(png),
        "tiles32",
        tile_width=32,
        tile_height=32,
        planes=2,
        use_dither=False,
        omit_palette=True,
    )
    assert "tile size=32x32" in asm
    assert "SECTION tileset,DATA_C" in asm.replace("\t", " ")
    assert "tiles32:" in asm
    assert "DC.L" in asm
    assert "Tile 0" in asm
    assert "Tile 1" in asm


def test_tile_width_rejects_24():
    from unittest.mock import patch

    with patch.object(tile, "Image", Image):
        with patch.object(tile, "quantize_image") as q:
            q.return_value = {
                "width": 24,
                "height": 8,
                "indices_by_row": [[0] * 24 for _ in range(8)],
                "final_palette": [0, 0, 0, 255, 255, 255],
                "max_colors": 4,
            }
            with pytest.raises(ValueError, match="8, 16, or 32"):
                tile.export_tileset_asm(
                    "dummy.png",
                    "t",
                    tile_width=24,
                    tile_height=8,
                    planes=2,
                )
