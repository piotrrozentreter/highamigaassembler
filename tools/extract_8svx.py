#!/usr/bin/env python3
"""Extract IFF 8SVX BODY PCM to a raw signed 8-bit sample file.

Supports uncompressed BODY only (VHDR sCompression == 0).

CLI:
    .venv/bin/python3 tools/extract_8svx.py in.iff out.raw

Library:
    extract_8svx(src, dst) -> dict  # includes sample_rate when VHDR is present
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union


class EightSvxError(ValueError):
    """Raised when an IFF 8SVX file cannot be parsed or extracted."""


def _read_chunk_header(data: bytes, offset: int) -> Tuple[bytes, int, int]:
    """Return (chunk_id, size, header_end_offset)."""
    if offset + 8 > len(data):
        raise EightSvxError("Unexpected EOF reading chunk header")
    chunk_id = data[offset : offset + 4]
    size = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
    return chunk_id, size, offset + 8


def _parse_8svx(data: bytes) -> Tuple[bytes, Optional[int]]:
    """Parse FORM/8SVX; return (body_pcm, sample_rate_or_None)."""
    if len(data) < 12:
        raise EightSvxError("File too short for IFF FORM header")
    if data[0:4] != b"FORM":
        raise EightSvxError(f"Not an IFF file (expected FORM, got {data[0:4]!r})")
    form_type = data[8:12]
    if form_type != b"8SVX":
        raise EightSvxError(f"Not an 8SVX FORM (got {form_type!r})")

    form_size = struct.unpack(">I", data[4:8])[0]
    # FORM size counts from offset 8; payload ends at 8 + form_size.
    end = min(len(data), 8 + form_size)
    offset = 12

    sample_rate: Optional[int] = None
    compression = 0
    body: Optional[bytes] = None

    while offset + 8 <= end:
        chunk_id, size, data_off = _read_chunk_header(data, offset)
        chunk_end = data_off + size
        if chunk_end > len(data):
            raise EightSvxError(f"Chunk {chunk_id!r} extends past end of file")

        payload = data[data_off:chunk_end]

        if chunk_id == b"VHDR":
            # Voice8Header (20 bytes); samplesPerSec at +12, sCompression at +15.
            if len(payload) < 16:
                raise EightSvxError("VHDR chunk too short")
            sample_rate = struct.unpack(">H", payload[12:14])[0]
            compression = payload[15]
        elif chunk_id == b"BODY":
            body = payload

        # Chunks are word-aligned; odd sizes have a pad byte.
        offset = chunk_end + (size & 1)

    if body is None:
        raise EightSvxError("Missing BODY chunk")
    if compression != 0:
        raise EightSvxError(
            f"Compressed 8SVX BODY not supported (sCompression={compression}); "
            "only uncompressed PCM is handled"
        )
    return body, sample_rate


def extract_8svx(
    src: Union[str, Path],
    dst: Union[str, Path],
) -> Dict[str, Any]:
    """Extract uncompressed 8SVX BODY to ``dst`` as raw PCM.

    Returns a dict with at least ``bytes_written``. When a VHDR chunk is
    present, also includes ``sample_rate`` (samples per second).
    """
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.is_file():
        raise EightSvxError(f"Source not found: {src_path}")

    data = src_path.read_bytes()
    body, sample_rate = _parse_8svx(data)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_bytes(body)

    result: Dict[str, Any] = {
        "bytes_written": len(body),
        "source": str(src_path),
        "dest": str(dst_path),
    }
    if sample_rate is not None:
        result["sample_rate"] = int(sample_rate)
    return result


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract IFF 8SVX BODY PCM to a raw sample file"
    )
    parser.add_argument("src", help="Input .iff / .8svx file")
    parser.add_argument("dst", help="Output .raw PCM path")
    args = parser.parse_args(argv)
    try:
        info = extract_8svx(args.src, args.dst)
    except EightSvxError as exc:
        print(f"extract_8svx: {exc}", file=sys.stderr)
        return 1
    rate = info.get("sample_rate")
    extra = f", sample_rate={rate}" if rate is not None else ""
    print(f"Wrote {info['bytes_written']} bytes to {info['dest']}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
