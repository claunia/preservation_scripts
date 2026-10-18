#!/bin/bash

AARU="${AARU:-/usr/bin/aaru}"
# Parallel jobs. Reading the LZMA compressed images is CPU bound, so a few jobs use more cores,
# but too many make a hard disk seek between images. Each job takes up to ~900MB of memory.
JOBS="${JOBS:-4}"

# For each .aif file in the current directory and all subdirectories that is missing
# its .metadata.json sidecar, create it. Compressed images pending finalization are skipped,
# as are folders (and everything below them) containing a metadata.json file.
# With JOBS=1 aaru keeps the terminal (for its progress bars). Otherwise the output of each
# image goes to <image>.sidecar.log, which is removed when it succeeds.
# On Ctrl+C aaru stops and still writes the partial sidecar, so it is removed.
find_images() {
    find . -type d -exec test -e '{}/metadata.json' \; -prune -o \
         -type f -name '*.aif' ! -name '*.compressed.aif' -print0 | sort -z
}

if [ "$JOBS" -le 1 ]; then
    interrupted=
    trap 'interrupted=1' INT TERM
    # The file list is read from fd 3 so aaru keeps the terminal as stdin
    while IFS= read -r -d '' f <&3; do
        [ -e "${f%.aif}.metadata.json" ] && continue

        echo "$f"
        ok=1
        (cd "$(dirname "$f")" && "$AARU" i create-sidecar "$(basename "$f")") || ok=
        if [ -n "$interrupted" ]; then
            rm -f "${f%.aif}.metadata.json"
            echo "interrupted: $f"
            exit 130
        fi
        [ -z "$ok" ] && echo "FAILED: $f"
    done 3< <(find_images)
    exit
fi

sidecar() {
    local f="$1" log="${1%.aif}.sidecar.log"
    [ -e "${f%.aif}.metadata.json" ] && return

    local interrupted= ok=1
    trap 'interrupted=1' INT TERM
    echo "start: $f"
    (cd "$(dirname "$f")" && "$AARU" i create-sidecar "$(basename "$f")") </dev/null >"$log" 2>&1 || ok=
    if [ -n "$interrupted" ]; then
        rm -f "${f%.aif}.metadata.json" "$log"
        echo "interrupted: $f"
        exit 130
    elif [ -n "$ok" ]; then
        rm -f "$log"
        echo "done: $f"
    else
        echo "FAILED: $f (see $log)"
    fi
}
export -f sidecar
export AARU

find_images | xargs -0 -r -n 1 -P "$JOBS" bash -c 'sidecar "$1"' _
