#!/bin/bash

AARU=/mnt/datos2/Aaru/6.0/aaru

# For each .aif file in the current directory and all subdirectories that is missing
# its .metadata.json sidecar, create it. Compressed images pending finalization are skipped,
# as are folders (and everything below them) containing a metadata.json file.
# The file list is read from fd 3 so aaru keeps the terminal as stdin (needed for its progress bars).
while IFS= read -r -d '' f <&3; do
    [ -e "${f%.aif}.metadata.json" ] && continue

    echo "$f"
    (cd "$(dirname "$f")" && "$AARU" i create-sidecar "$(basename "$f")") || echo "FAILED: $f"
done 3< <(find . -type d -exec test -e '{}/metadata.json' \; -prune -o \
                -type f -name '*.aif' ! -name '*.compressed.aif' -print0 | sort -z)
