#!/usr/bin/env python3
"""Combine the discs of two (or more) Aaru metadata JSON files into a single multi-disc metadata JSON.

Discs are kept in the order the files are given (a file that already holds several discs keeps
its internal order) and renumbered: Sequence.MediaSequence = 1..N, Sequence.TotalMedia = N.
Other Sequence fields such as Title are kept.

Top-level fields (Name, Publishers, Release, ReleaseDate...) are taken from the first file that
has them; if a later file has a different value, a warning is printed and the first one is kept.

By default the result is written as metadata.json next to the first file. Input files are never
modified, except when one of them is the output file, which is then backed up to <file>.bak first.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Top-level lists that hold media: these are concatenated. Any other list is merged without duplicates.
MEDIA_KEYS = ("OpticalDiscs", "BlockMedias", "LinearMedias", "AudioMedias")


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "AaruMetadata" not in data:
        raise ValueError(f"{path}: not an Aaru metadata file (no AaruMetadata key)")
    return data["AaruMetadata"]


def image_name(media):
    image = media.get("Image")
    return image.get("Value") if isinstance(image, dict) else image


def merge(paths):
    merged = {}
    for path in paths:
        meta = load(path)
        for key, value in meta.items():
            if key in MEDIA_KEYS:
                merged.setdefault(key, []).extend(value or [])
            elif key not in merged:
                merged[key] = value
            elif isinstance(value, list) and isinstance(merged[key], list):
                merged[key] += [v for v in value if v not in merged[key]]
            elif merged[key] != value:
                print(f"WARNING: {key} differs, keeping {merged[key]!r} and ignoring {value!r} from {path}",
                      file=sys.stderr)

    media = [m for key in MEDIA_KEYS for m in merged.get(key) or []]

    names = [image_name(m) for m in media]
    duplicates = {n for n in names if n and names.count(n) > 1}
    if duplicates:
        raise ValueError(f"the same image appears more than once: {', '.join(sorted(duplicates))}")

    # Same contents under a different image name (e.g. a recompressed copy)
    seen = {}
    for m in media:
        digest = next((c["Value"] for c in m.get("Checksums") or [] if c.get("Type") == "Sha1"), None)
        if digest and digest in seen:
            raise ValueError(f"{image_name(m)} has the same contents (SHA-1 {digest}) as {seen[digest]}")
        seen.setdefault(digest, image_name(m))

    for number, m in enumerate(media, 1):
        m["Sequence"] = {**(m.get("Sequence") or {}), "MediaSequence": number, "TotalMedia": len(media)}

    return {"AaruMetadata": merged}, media


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", type=Path, help="Aaru metadata JSON files, in disc order (at least two)")
    parser.add_argument("-o", "--output", type=Path,
                        help="Output file (default: metadata.json in the first file's folder)")
    parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Show the resulting disc list without writing")
    args = parser.parse_args()

    if len(args.inputs) < 2:
        parser.error("give at least two metadata files")

    output = args.output or args.inputs[0].parent / "metadata.json"
    resolved_inputs = [p.resolve() for p in args.inputs]
    output_is_input = output.resolve() in resolved_inputs

    if len(set(resolved_inputs)) != len(resolved_inputs):
        parser.error("the same file was given twice")
    if output.exists() and not output_is_input and not args.force and not args.dry_run:
        parser.error(f"{output} already exists and is not one of the inputs; use --force to overwrite it")

    if len({p.parent for p in resolved_inputs}) > 1:
        print("WARNING: the inputs are in different folders; image file names in the result are relative "
              "and will only resolve if the images are moved next to the output file", file=sys.stderr)

    try:
        data, media = merge(args.inputs)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        sys.exit(f"ERROR: {e}")

    for m in media:
        title = m["Sequence"].get("Title")
        print(f"  {m['Sequence']['MediaSequence']}/{m['Sequence']['TotalMedia']}: {image_name(m)}"
              + (f" ({title})" if title else ""))

    if args.dry_run:
        print(f"Would write {output}")
        return

    if output_is_input:
        backup = output.with_name(output.name + ".bak")
        if not backup.exists():  # never overwrite an earlier backup
            shutil.copy2(output, backup)

    tmp = output.with_name(output.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(output)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
