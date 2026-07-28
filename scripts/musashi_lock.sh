#!/usr/bin/env bash

# Read tools/musashi.lock as plain data (not executable shell source).
# Exports:
#   MUSASHI_REPO
#   MUSASHI_REF
#   MUSASHI_PINNED_ON
#   MUSASHI_NOTES
musashi_lock_load() {
    local lock_file="$1"
    local line key value

    if [[ ! -f "$lock_file" ]]; then
        echo "ERROR: lock file not found: $lock_file" >&2
        return 1
    fi

    MUSASHI_REPO=""
    MUSASHI_REF=""
    MUSASHI_PINNED_ON=""
    MUSASHI_NOTES=""

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ -z "$line" ]] && continue
        [[ "$line" == \#* ]] && continue

        key="${line%%=*}"
        value="${line#*=}"
        if [[ "$key" == "$line" ]]; then
            echo "ERROR: invalid lock line (missing '='): $line" >&2
            return 1
        fi

        case "$key" in
            MUSASHI_REPO) MUSASHI_REPO="$value" ;;
            MUSASHI_REF) MUSASHI_REF="$value" ;;
            MUSASHI_PINNED_ON) MUSASHI_PINNED_ON="$value" ;;
            MUSASHI_NOTES) MUSASHI_NOTES="$value" ;;
            *)
                echo "ERROR: unsupported lock key: $key" >&2
                return 1
                ;;
        esac
    done < "$lock_file"

    if [[ -z "$MUSASHI_REPO" || -z "$MUSASHI_REF" ]]; then
        echo "ERROR: MUSASHI_REPO and MUSASHI_REF must be set in $lock_file" >&2
        return 1
    fi

    export MUSASHI_REPO MUSASHI_REF MUSASHI_PINNED_ON MUSASHI_NOTES
}
