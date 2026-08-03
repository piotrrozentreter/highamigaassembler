#!/usr/bin/env python3
"""Create a custom TrackIo data disk (ADF) for DOS-free runtime loading.

Container layout (sector 0, 512 bytes):
- magic 'HAST' (u32)
- version (u16 = 1)
- entry_count (u16 <= 31)
- entries[entry_count] where each entry is 16 bytes:
  - file_id (u32)
  - start_lba (u32)
  - size_bytes (u32)
  - flags (u16)      bit0: payload XOR-encoded
  - xor_key (u8)
  - reserved (u8)

Data payload starts at LBA 1.
"""

from __future__ import annotations

import argparse
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List

ADF_SIZE = 901120
SECTOR_SIZE = 512
SECTOR_COUNT = ADF_SIZE // SECTOR_SIZE
MAGIC = 0x48415354  # 'HAST'
VERSION = 1
MAX_ENTRIES = 31


@dataclass
class Asset:
    file_id: int
    path: Path
    size: int
    data: bytes


def parse_asset(value: str) -> tuple[int, Path]:
    if ":" not in value:
        raise argparse.ArgumentTypeError(
            f"Invalid --asset '{value}'. Expected format: <id>:<path>"
        )

    id_part, path_part = value.split(":", 1)
    try:
        file_id = int(id_part, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid asset id '{id_part}' in '{value}'"
        ) from exc

    if file_id < 0:
        raise argparse.ArgumentTypeError(f"Asset id must be >= 0: '{value}'")

    path = Path(path_part)
    return file_id, path


def load_assets(specs: List[str]) -> List[Asset]:
    seen_ids: set[int] = set()
    assets: List[Asset] = []

    for spec in specs:
        file_id, path = parse_asset(spec)
        if file_id in seen_ids:
            raise ValueError(f"Duplicate asset id: {file_id}")
        seen_ids.add(file_id)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Asset file not found: {path}")

        data = path.read_bytes()
        assets.append(Asset(file_id=file_id, path=path, size=len(data), data=data))

    if len(assets) > MAX_ENTRIES:
        raise ValueError(
            f"Too many assets: {len(assets)}. Maximum supported is {MAX_ENTRIES}."
        )

    return assets


def xor_payload(data: bytes, key: int) -> bytes:
    if key == 0:
        return data
    return bytes((b ^ key) for b in data)


def build_adf(assets: List[Asset], xor_key: int) -> bytes:
    adf = bytearray(ADF_SIZE)

    flags = 1 if xor_key != 0 else 0

    struct.pack_into(">LHH", adf, 0, MAGIC, VERSION, len(assets))

    next_lba = 1
    for i, asset in enumerate(assets):
        sectors_needed = math.ceil(asset.size / SECTOR_SIZE) if asset.size > 0 else 0
        start_lba = next_lba

        if start_lba + sectors_needed > SECTOR_COUNT:
            raise ValueError(
                f"Disk full while placing asset id={asset.file_id} ({asset.path}). "
                f"Needs {sectors_needed} sectors, only {SECTOR_COUNT - start_lba} left."
            )

        entry_off = 8 + i * 16
        struct.pack_into(
            ">LLLHB",
            adf,
            entry_off,
            asset.file_id,
            start_lba,
            asset.size,
            flags,
            xor_key,
        )
        adf[entry_off + 15] = 0

        encoded = xor_payload(asset.data, xor_key)
        data_off = start_lba * SECTOR_SIZE
        adf[data_off : data_off + len(encoded)] = encoded

        next_lba += sectors_needed

    return bytes(adf)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a custom TrackIo ADF data disk (DOS-free runtime loader format)."
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output ADF path (for example: disks/trackio_data.adf)",
    )
    parser.add_argument(
        "--asset",
        action="append",
        default=[],
        help="Asset mapping in format <id>:<path>. Can be repeated.",
    )
    parser.add_argument(
        "--xor-key",
        default="0",
        help="Optional XOR key (0..255). Accepts decimal or 0x..",
    )

    args = parser.parse_args()

    if not args.asset:
        parser.error("At least one --asset is required.")

    try:
        xor_key = int(args.xor_key, 0)
    except ValueError as exc:
        raise SystemExit(f"Invalid --xor-key '{args.xor_key}'") from exc

    if xor_key < 0 or xor_key > 255:
        raise SystemExit("--xor-key must be in range 0..255")

    assets = load_assets(args.asset)
    adf_data = build_adf(assets, xor_key)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(adf_data)

    print(f"Wrote {out_path} ({len(adf_data)} bytes)")
    print(f"Assets: {len(assets)}")
    for asset in assets:
        print(f"  id={asset.file_id:>5}  size={asset.size:>7}  path={asset.path}")

    if xor_key:
        print(f"Payload XOR key: 0x{xor_key:02X}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
