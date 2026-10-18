#!/bin/bash
# Usage: convert.sh [-j JOBS]
#
# Converts (compresses) and compares every .aif file in the subdirectories
# (up to 3 levels deep) of the current directory, running up to JOBS images at
# the same time (default 4, or the JOBS environment variable).
#
# With more than one job, aaru's console output is discarded so the jobs do not
# garble each other; everything is still in the .convert.log and .compare.log.

AARU="${AARU:-/usr/bin/aaru}"
CREATOR="Nat Portillo"
JOBS="${JOBS:-4}"

while getopts "j:" opt; do
    case "$opt" in
        j) JOBS="$OPTARG" ;;
        *) sed -n '2,/^$/p' "$0"; exit 1 ;;
    esac
done

if ! [[ "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Invalid number of jobs: $JOBS" >&2
    exit 1
fi

failures="$(mktemp)"
trap 'rm -f "$failures"' EXIT

# Convert and compare one image, in the current directory.
# With "compare" as second argument, only compares an already converted image.
convert_image() {
    local f="$1" path="$PWD/$1" convert=1
    [ "$2" = compare ] && convert=0

    if [ "$JOBS" = 1 ]; then
        echo "$path"
        { [ "$convert" = 0 ] ||
          "$AARU" i --logfile "${f%.aif}.convert.log" convert --creator "$CREATOR" --generate-subchannels "$f" "${f%.aif}.compressed.aif"; } &&
        "$AARU" i --logfile "${f%.aif}.compare.log" compare "$f" "${f%.aif}.compressed.aif"
    else
        echo "start: $path"
        { [ "$convert" = 0 ] ||
          "$AARU" i --logfile "${f%.aif}.convert.log" convert --creator "$CREATOR" --generate-subchannels "$f" "${f%.aif}.compressed.aif" >/dev/null 2>&1; } &&
        "$AARU" i --logfile "${f%.aif}.compare.log" compare "$f" "${f%.aif}.compressed.aif" >/dev/null 2>&1
    fi

    if [ $? -eq 0 ]; then
        echo "done: $path"
    else
        echo "FAILED: $path (see ${f%.aif}.convert.log / ${f%.aif}.compare.log)"
        echo "$path" >> "$failures"
    fi
}

# Start a job in the background, waiting first if JOBS are already running
queue_image() {
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do
        wait -n
    done
    convert_image "$1" "$2" &
}

# Queue every .aif file in the current directory,
# skipping images that are already compressed
convert_dir() {
    for f in *.aif ; do
        [ -e "$f" ] || continue

        # Output of a previous conversion, not a source image
        case "$f" in
            *.compressed.aif) continue ;;
        esac

        # Already converted, pending finalization
        if [ -e "${f%.aif}.compressed.aif" ]; then
            # Conversion finished but the compare never ran (failed or interrupted run)
            if [ ! -e "${f%.aif}.compare.log" ] &&
               tail -n 5 "${f%.aif}.convert.log" 2>/dev/null | grep -q "Conversion done"; then
                echo "$f (converted but not compared, comparing)"
                queue_image "$f" compare
                continue
            fi

            echo "$f (skipped, ${f%.aif}.compressed.aif already exists)"
            continue
        fi

        # Already converted and finalized (convert stamps the creator, dumps don't)
        if "$AARU" i info "$f" 2>/dev/null | grep -q "Created by: $CREATOR"; then
            echo "$f (skipped, already compressed)"
            continue
        fi

        queue_image "$f"
    done
}

# For each subdirectory, but not files, in the current directory
for d1 in */ ; do
    [ -d "$d1" ] || continue
    # Enter the subdirectory
    cd "$d1" || continue

    convert_dir

    # For each subdirectory, but not file, in the current directory
    for d2 in */ ; do
        [ -d "$d2" ] || continue
        # Enter the subdirectory
        cd "$d2" || continue

        convert_dir

        # For each subdirectory, but not file, in the current directory
        for d3 in */ ; do
            [ -d "$d3" ] || continue
            # Enter the subdirectory
            cd "$d3" || continue

            convert_dir

            # Exit the subdirectory
            cd ..
        done

        # Exit the subdirectory
        cd ..
    done

    # Exit the subdirectory
    cd ..
done

# Wait for the jobs still running
wait

if [ -s "$failures" ]; then
    echo
    echo "$(wc -l < "$failures") image(s) failed:"
    cat "$failures"
    exit 1
fi
