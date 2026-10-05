#!/usr/bin/env bash
# Walks all subfolders of the given directory (default: current directory) and,
# in every leaf folder (one with no subfolders), creates PAR2 recovery files:
#   par2 c -r10 -u -n5 -R "<folder name>.par2" *
# Folders are processed one at a time; leaves that already have
# "<folder name>.par2" or contain no files are skipped.

shopt -s nullglob

root="${1:-.}"

while IFS= read -r -d '' dir; do
    # Skip non-leaf folders
    if [[ -n "$(find "$dir" -mindepth 1 -maxdepth 1 -type d -print -quit)" ]]; then
        continue
    fi

    name="$(basename "$(realpath "$dir")")"

    if [[ -e "$dir/$name.par2" ]]; then
        echo "Skipping (already done): $dir"
        continue
    fi

    (
        cd "$dir" || exit 1
        files=(*)
        if (( ${#files[@]} == 0 )); then
            echo "Skipping (empty): $dir"
            exit 0
        fi
        echo "Processing: $dir"
        par2 c -r10 -u -n5 -R "$name.par2" "${files[@]}" || echo "par2 FAILED in: $dir" >&2
    )
done < <(find "$root" -type d -print0 | sort -z)
