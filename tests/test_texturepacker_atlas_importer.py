from pathlib import Path

from PIL import Image

from tools.texturepacker_atlas_importer import (
    process_atlas,
    write_master_include,
    write_shared_palette_file,
)


def _write_repeated_frame_atlas(tmp_path: Path) -> Path:
    atlas_path = tmp_path / "walk.png"
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(atlas_path)

    xml_path = tmp_path / "walk.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<TextureAtlas imagePath="walk.png">
    <sprite n="walk_0.png" x="0" y="0" w="1" h="1"/>
    <sprite n="walk_1.png" x="0" y="0" w="1" h="1"/>
</TextureAtlas>
""",
        encoding="utf-8",
    )
    return xml_path


def test_repeated_frames_are_separate_files_by_default(tmp_path: Path) -> None:
    xml_path = _write_repeated_frame_atlas(tmp_path)

    results, _, _ = process_atlas(str(xml_path), out_dir=str(tmp_path), force=True)

    assert len(results) == 2
    assert (tmp_path / "walk_walk_0.s").exists()
    assert (tmp_path / "walk_walk_1.s").exists()


def test_deduplicated_frames_emit_alias_labels_once(tmp_path: Path) -> None:
    xml_path = _write_repeated_frame_atlas(tmp_path)
    stale_alias = tmp_path / "walk_walk_1.s"
    stale_alias.write_text("stale duplicate", encoding="utf-8")

    results, _, _ = process_atlas(
        str(xml_path),
        out_dir=str(tmp_path),
        force=True,
        deduplicate_frames=True,
    )

    assert len(results) == 2
    assert results[0][0] == results[1][0]
    assert not (tmp_path / "walk_walk_1.s").exists()

    assembly = (tmp_path / "walk_walk_0.s").read_text(encoding="utf-8")
    assert "walk_walk_0:" in assembly
    assert "walk_walk_1:" in assembly
    assert assembly.count("\tDC.L\twalk_walk_0_data, walk_walk_0_mask, walk_walk_0_palette") == 1
    assert "walk_walk_1_data:" in assembly
    assert "walk_walk_1_mask:" in assembly
    assert "walk_walk_1_palette:" in assembly


def test_switching_from_deduplicated_to_default_removes_aliases(tmp_path: Path) -> None:
    xml_path = _write_repeated_frame_atlas(tmp_path)
    process_atlas(
        str(xml_path), out_dir=str(tmp_path), force=True, deduplicate_frames=True
    )

    results, _, _ = process_atlas(str(xml_path), out_dir=str(tmp_path))

    assert len(results) == 2
    first = (tmp_path / "walk_walk_0.s").read_text(encoding="utf-8")
    second = (tmp_path / "walk_walk_1.s").read_text(encoding="utf-8")
    assert "; Alias labels:" not in first
    assert first.count("walk_walk_1:") == 0
    assert second.count("walk_walk_1:") == 1


def test_shared_palette_descriptors_omit_duplicate_palette_words(tmp_path: Path) -> None:
    xml_path = _write_repeated_frame_atlas(tmp_path)

    process_atlas(
        str(xml_path),
        out_dir=str(tmp_path),
        force=True,
        shared_palette_label="walk_palette",
    )

    for frame_name in ("walk_walk_0", "walk_walk_1"):
        assembly = (tmp_path / f"{frame_name}.s").read_text(encoding="utf-8")
        assert "; External shared palette: walk_palette" in assembly
        assert f"{frame_name}_palette EQU walk_palette" in assembly
        assert f"\tDC.L\t{frame_name}_data, {frame_name}_mask, walk_palette" in assembly
        assert "\tDC.W\t$" not in assembly


def test_master_include_places_shared_palette_before_bob_files(tmp_path: Path) -> None:
    xml_path = _write_repeated_frame_atlas(tmp_path)
    results, shared_palette, _ = process_atlas(
        str(xml_path),
        out_dir=str(tmp_path),
        force=True,
        shared_palette_label="walk_palette",
    )
    palette_file = tmp_path / "walk_palette.s"
    master_file = tmp_path / "walk_atlas.s"

    write_shared_palette_file(palette_file, "walk_palette", shared_palette, planes=5)
    write_master_include(results, master_file, "walk", palette_file)

    master = master_file.read_text(encoding="utf-8")
    palette_include = master.index('\tINCLUDE\t"walk_palette.s"')
    first_bob_include = master.index('\tINCLUDE\t"walk_walk_0.s"')
    assert palette_include < first_bob_include