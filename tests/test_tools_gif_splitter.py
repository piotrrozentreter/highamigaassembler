from PIL import Image

from tools.gif_splitter import split_gif


def test_split_gif_writes_each_frame_as_png(tmp_path):
    source = tmp_path / "animation.gif"
    output_directory = tmp_path / "frames"
    first = Image.new("RGB", (2, 1), "red")
    second = Image.new("RGB", (2, 1), "blue")
    first.save(source, save_all=True, append_images=[second], duration=100, loop=0)

    output_paths = split_gif(source, output_directory)

    assert output_paths == [
        output_directory / "animation_000.png",
        output_directory / "animation_001.png",
    ]
    assert [Image.open(path).convert("RGB").getpixel((0, 0)) for path in output_paths] == [
        (255, 0, 0),
        (0, 0, 255),
    ]