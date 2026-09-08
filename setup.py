"""Setuptools resource collection for the HAS release distribution."""

from collections import defaultdict
from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).parent
RESOURCE_DIRS = ("lib", "tools", "scripts", "examples", "guicreator")
EXCLUDED_PARTS = {"__pycache__", "musashi_runner"}
EXCLUDED_NAMES = {"musashi.lock"}
DESTINATION_ROOT = Path("share") / "high-amiga-assembler"


def collect_resource_files():
    """Return data-files entries while retaining each resource's directory layout."""
    grouped_files = defaultdict(list)
    for resource_dir in RESOURCE_DIRS:
        source_dir = ROOT / resource_dir
        for source_file in source_dir.rglob("*"):
            relative_file = source_file.relative_to(ROOT)
            if (
                not source_file.is_file()
                or EXCLUDED_PARTS.intersection(source_file.parts)
                or source_file.name in EXCLUDED_NAMES
                or "musashi" in source_file.name.lower()
                or any("musashi" in part.lower() for part in relative_file.parts)
            ):
                continue
            if source_file.suffix in {".pyc", ".pyo"}:
                continue
            relative_parent = source_file.parent.relative_to(ROOT)
            destination = DESTINATION_ROOT / relative_parent
            grouped_files[str(destination)].append(str(relative_file))
    return sorted(grouped_files.items())


setup(data_files=collect_resource_files())