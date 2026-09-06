#!/usr/bin/env python3
"""Split every frame of an animated GIF into individual PNG files.

Usage:
    python3 tools/gif_splitter.py input.gif [output_directory]
"""

import argparse
from pathlib import Path
from typing import List, Optional, Sequence, Union

try:
    from PIL import Image, ImageSequence
except ImportError:
    Image = None
    ImageSequence = None


def split_gif(
    input_path: Union[str, Path], output_directory: Union[str, Path, None] = None
) -> List[Path]:
    """Save every frame from a GIF as a numbered PNG and return its paths."""
    if Image is None or ImageSequence is None:
        raise RuntimeError("Pillow is required for GIF splitting (pip install pillow)")

    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"GIF file not found: {source}")

    destination = Path(output_directory) if output_directory else source.with_name(source.stem)
    destination.mkdir(parents=True, exist_ok=True)

    output_paths = []
    with Image.open(source) as gif:
        if gif.format != "GIF":
            raise ValueError(f"Input file is not a GIF: {source}")

        for index, frame in enumerate(ImageSequence.Iterator(gif)):
            output_path = destination / f"{source.stem}_{index:03d}.png"
            frame.convert("RGBA").save(output_path, "PNG")
            output_paths.append(output_path)

    return output_paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the GIF frame splitter command-line interface."""
    parser = argparse.ArgumentParser(description="Split GIF frames into PNG files.")
    parser.add_argument("input", type=Path, help="GIF file to split")
    parser.add_argument(
        "output_directory",
        nargs="?",
        type=Path,
        help="Directory for PNG files (default: a folder named after the GIF)",
    )
    args = parser.parse_args(argv)

    try:
        output_paths = split_gif(args.input, args.output_directory)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    print(f"Extracted {len(output_paths)} frame(s) to {output_paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())