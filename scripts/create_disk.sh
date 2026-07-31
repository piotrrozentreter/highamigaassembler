#!/bin/bash

# create_disk.sh - Universal ADF disk creation script for HAS (High Amiga Assembler) projects
# Usage: ./create_disk.sh <diskname> <program_to_copy>
# 
# Uses xdftool from amitools for proper Amiga filesystem creation
#
# Arguments:
#   diskname      - Name of the ADF file to create (without .adf extension)
#   program       - Path to the executable program to copy
#
# Examples:
#   ./create_disk.sh MyGame build/launchers.exe
#   ./create_disk.sh MyDemo build/myprogram.exe

if [ $# -lt 2 ]; then
    echo "Usage: $0 <diskname> <program_to_copy>"
    echo ""
    echo "Arguments:"
    echo "  diskname      - Name of ADF file (without .adf)"
    echo "  program       - Path to executable program"
    echo ""
    echo "Examples:"
    echo "  $0 Launchers build/launchers.exe"
    echo "  $0 MyGame build/mygame.exe" 
    exit 1
fi

DISKNAME="$1"
PROGRAM="$2"
ADF_FILE="disks/${DISKNAME}.adf"

# Go to script directory then back to project root
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
cd "$PROJECT_ROOT" || exit 1

echo "Creating ADF disk: $DISKNAME"
echo "Program: $PROGRAM"

# Check if program exists
if [ ! -f "$PROGRAM" ]; then
    echo "Error: Program '$PROGRAM' not found!"
    echo "Make sure to compile your HAS program first:"
    echo "  cd examples/games/launchers && make"
    exit 1
fi

XDFTOOL_CMD=()

python_has_xdftool_module() {
    local py="$1"
    "$py" -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('amitools.tools.xdftool') else 1)" >/dev/null 2>&1
}

resolve_xdftool() {
    if [ -n "${XDFTOOL:-}" ]; then
        XDFTOOL_CMD=(${XDFTOOL})
        return 0
    fi

    if command -v xdftool >/dev/null 2>&1; then
        XDFTOOL_CMD=(xdftool)
        return 0
    fi

    local candidates=(
        "${AMITOOLS_PYTHON:-}"
        "python3"
        "python"
        "$PROJECT_ROOT/.venv/bin/python"
    )
    local py
    for py in "${candidates[@]}"; do
        [ -z "$py" ] && continue

        if [ -x "$py" ]; then
            if python_has_xdftool_module "$py"; then
                XDFTOOL_CMD=("$py" -m amitools.tools.xdftool)
                return 0
            fi
            continue
        fi

        if command -v "$py" >/dev/null 2>&1 && python_has_xdftool_module "$py"; then
            XDFTOOL_CMD=("$py" -m amitools.tools.xdftool)
            return 0
        fi
    done

    return 1
}

run_xdftool() {
    "${XDFTOOL_CMD[@]}" "$@"
}

# Check for xdftool (from amitools)
if ! resolve_xdftool; then
    echo "xdftool not found. Installing amitools (contains xdftool)..."

    # Try to install amitools
    if command -v pip3 >/dev/null 2>&1; then
        if ! pip3 install --user amitools >/dev/null 2>&1; then
            echo "Warning: pip3 --user install failed, trying python-based install..."
        fi
    fi

    if ! resolve_xdftool; then
        local_py_install_target="${AMITOOLS_PYTHON:-python3}"
        if command -v "$local_py_install_target" >/dev/null 2>&1; then
            "$local_py_install_target" -m pip install amitools >/dev/null 2>&1 || true
        fi
    fi

    if ! resolve_xdftool; then
        echo "Error: amitools installed, but xdftool is still not available."
        echo "Try one of the following:"
        echo "  export PATH=\"$HOME/.local/bin:$PATH\""
        echo "  export AMITOOLS_PYTHON=/path/to/python-with-amitools"
        echo "  export XDFTOOL='xdftool'"
        exit 1
    fi

    echo "amitools installed successfully"
fi

# Ensure disks directory exists
mkdir -p disks

# Remove existing ADF
rm -f "$ADF_FILE"

echo "Creating ADF with xdftool..."

PROG_SIZE=$(stat -c%s "$PROGRAM")
PROG_NAME=$(basename "$PROGRAM")
STARTUP_FILE=$(mktemp)

cat > "$STARTUP_FILE" <<EOF
; Auto-generated startup-sequence
echo "Starting ${PROG_NAME}..."
SYS:${PROG_NAME}
endcli >NIL:
EOF

cleanup() {
    rm -f "$STARTUP_FILE"
}
trap cleanup EXIT

# Create a bootable ADF with startup-sequence that launches the program.
run_xdftool "$ADF_FILE" create + format "$DISKNAME" + makedir "S" + write "$PROGRAM" "$PROG_NAME" + write "$STARTUP_FILE" "S/startup-sequence"

if [ $? -eq 0 ]; then
    echo ""
    echo "ADF disk created successfully"
    echo "File: $ADF_FILE"
    echo "Program: $PROG_NAME (${PROG_SIZE} bytes)"
    echo "Volume: $DISKNAME"
    echo "Tool: ${XDFTOOL_CMD[*]}"
    echo "Boot: S/startup-sequence launches SYS:$PROG_NAME"
    echo ""
    echo "Contents:"
    run_xdftool "$ADF_FILE" list
    echo ""
    echo "Usage:"
    echo "  - Load $ADF_FILE in FS-UAE or other Amiga emulator"
    echo "  - Disk should boot and run $PROG_NAME automatically"
else
    echo "Error: Failed to create ADF disk"
    exit 1
fi