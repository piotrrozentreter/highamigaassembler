"""Linux-only runtime smoke tests executed via Musashi.

These tests are intentionally optional and gated by platform + external tools.
Use scripts/test_runtime_musashi.sh directly for detailed logs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.runtime
@pytest.mark.musashi
def test_runtime_suite_via_musashi_script() -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("Musashi runtime tests are Linux-only")

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "test_runtime_musashi.sh"

    if not script.exists():
        pytest.skip("Musashi runtime script missing")

    result = subprocess.run(
        ["bash", str(script)],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )

    if result.returncode == 77:
        pytest.skip(result.stderr.strip() or "Musashi runtime prerequisites missing")

    if result.returncode != 0:
        raise AssertionError(
            "Musashi runtime suite failed\n"
            f"exit={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
