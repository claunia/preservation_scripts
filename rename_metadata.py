#!/usr/bin/env python3
"""Rename *.metadata.json to metadata.json in every subfolder.

Renames silently. Logs a folder and leaves it alone when:
  - it already has a metadata.json and also a *.metadata.json, or
  - it has more than one *.metadata.json.

Usage: rename_metadata.py [root] [--dry-run]
"""

import os
import sys

SUFFIX = ".metadata.json"
TARGET = "metadata.json"


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    root = args[0] if args else "."

    for dirpath, _dirnames, filenames in os.walk(root):
        candidates = sorted(f for f in filenames if f.endswith(SUFFIX) and f != TARGET)
        if not candidates:
            continue

        if TARGET in filenames:
            print(f"[EXISTS] {dirpath}: metadata.json already present alongside: {', '.join(candidates)}")
            continue

        if len(candidates) > 1:
            print(f"[MULTIPLE] {dirpath}: {', '.join(candidates)}")
            continue

        src = os.path.join(dirpath, candidates[0])
        dst = os.path.join(dirpath, TARGET)
        if dry_run:
            print(f"[DRY-RUN] {src} -> {dst}")
            continue
        try:
            os.rename(src, dst)
        except OSError as e:
            print(f"[ERROR] {src}: {e}")


if __name__ == "__main__":
    main()
