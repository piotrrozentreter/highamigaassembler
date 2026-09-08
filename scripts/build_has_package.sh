#!/usr/bin/env bash
set -euo pipefail

# Build and validate the HAS wheel/source distribution for a GitHub Release.
# Usage: ./scripts/build_has_package.sh [output-directory]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"

if [[ "$(uname -s)" != "Linux" ]]; then
	echo "ERROR: build_has_package.sh is supported on Linux only." >&2
	exit 1
fi

if [[ ! -f "$ROOT/pyproject.toml" ]]; then
	echo "ERROR: pyproject.toml not found at $ROOT" >&2
	exit 1
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
	PYTHON="${HASC_PYTHON:-$ROOT/.venv/bin/python}"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
	PYTHON="${HASC_PYTHON:-$ROOT/venv/bin/python}"
elif command -v python3 &>/dev/null; then
	PYTHON="${HASC_PYTHON:-python3}"
else
	PYTHON="${HASC_PYTHON:-python}"
fi

if ! command -v "$PYTHON" &>/dev/null; then
	echo "ERROR: Python interpreter not found: $PYTHON" >&2
	echo "Set HASC_PYTHON=/path/to/python3 to select one explicitly." >&2
	exit 1
fi

VERSION="$(cd "$ROOT" && "$PYTHON" -c 'from hasc import __version__; print(__version__)')"
PACKAGE_STEM="high_amiga_assembler-$VERSION"
STAGING_DIR="$(mktemp -d)"

cleanup() {
	rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

echo "Using Python: $PYTHON"
echo "Building HAS $VERSION"
"$PYTHON" -m pip install --upgrade build twine

# Run from staging so the repository's build/ directory cannot shadow the build frontend.
(
	cd "$STAGING_DIR"
	"$PYTHON" -m build "$ROOT" --outdir "$STAGING_DIR/artifacts"
)

"$PYTHON" -m twine check "$STAGING_DIR/artifacts"/*
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/$PACKAGE_STEM.tar.gz" "$OUT_DIR/$PACKAGE_STEM-py3-none-any.whl"
cp "$STAGING_DIR/artifacts/$PACKAGE_STEM.tar.gz" "$OUT_DIR/"
cp "$STAGING_DIR/artifacts/$PACKAGE_STEM-py3-none-any.whl" "$OUT_DIR/"

WHEEL="$OUT_DIR/$PACKAGE_STEM-py3-none-any.whl"
echo
echo "Built and validated: $WHEEL"
echo "Attach both files in $OUT_DIR to GitHub Release v$VERSION."

REMOTE_URL="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
if [[ "$REMOTE_URL" =~ github.com[:/]([^/]+/[^/.]+)(\.git)?$ ]]; then
	GITHUB_REPO="${BASH_REMATCH[1]}"
	echo
	echo "User installation command after publishing:"
	echo "pipx install https://github.com/$GITHUB_REPO/releases/download/v$VERSION/$PACKAGE_STEM-py3-none-any.whl"
else
	echo "Set the GitHub Release URL after uploading the wheel, then users can run:"
	echo "pipx install <GitHub-Release-wheel-URL>"
fi

echo "vasm and vlink remain separate user downloads for assembly and linking."