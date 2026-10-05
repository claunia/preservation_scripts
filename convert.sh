#!/bin/bash

AARU=/mnt/datos2/Aaru/6.0/aaru
CREATOR="Nat Portillo"

# Convert (compress) and compare every .aif file in the current directory,
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
            echo "$f (skipped, ${f%.aif}.compressed.aif already exists)"
            continue
        fi

        # Already converted and finalized (convert stamps the creator, dumps don't)
        if "$AARU" i info "$f" 2>/dev/null | grep -q "Created by: $CREATOR"; then
            echo "$f (skipped, already compressed)"
            continue
        fi

        echo "$f"
        "$AARU" i --logfile "${f%.aif}.convert.log" convert --creator "$CREATOR" --generate-subchannels "$f" "${f%.aif}.compressed.aif"
        "$AARU" i --logfile "${f%.aif}.compare.log" compare "$f" "${f%.aif}.compressed.aif"
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
