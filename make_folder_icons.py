#!/usr/bin/env python3
"""Create Windows (desktop.ini/desktop.ico) and XDG (.directory/.directory.png)
folder icons from JPEG-XL scans, for the given folder and all its subfolders."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREFERRED = ("cover.jxl", "front.jxl", "media.jxl", "up.jxl")
KEEP_SINGLE = ("cover.jxl", "front.jxl", "media.jxl")
TOOLS = ("magick", "optipng", "icotool")

DESKTOP_INI = "[.ShellClassInfo]\nIconResource=.\\desktop.ico,0"
DOT_DIRECTORY = "[Desktop Entry]\nIcon=./.directory.png"


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def make_png(src, dst, size):
    geometry = f"{size}x{size}"
    run("magick", str(src), "-resize", geometry, "-background", "none",
        "-gravity", "center", "-extent", geometry, "-depth", "8", str(dst))
    run("optipng", "-quiet", "-o7", str(dst))


def jxl_files(folder):
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() == ".jxl")


def process(folder, dry_run):
    jxls = jxl_files(folder)
    by_name = {p.name.lower(): p for p in jxls}

    if len(jxls) == 1 and jxls[0].name.lower() not in KEEP_SINGLE:
        target = folder / "media.jxl"
        print(f"rename: {jxls[0]} -> {target.name}")
        if not dry_run:
            jxls[0].rename(target)
        by_name = {"media.jxl": target}

    if (folder / ".directory").exists():
        print(f"skip: {folder} (has .directory)")
        return

    src = next((by_name[n] for n in PREFERRED if n in by_name), None)
    if src is None:
        print(f"skip: {folder} (no cover/front/media/up.jxl)")
        return

    if dry_run:
        print(f"would create icons: {folder} (from {src.name})")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        png256 = tmp / "256.png"
        png32 = tmp / "32.png"
        make_png(src, png256, 256)
        make_png(src, png32, 32)
        run("icotool", "-c", "-o", str(folder / "desktop.ico"),
            str(png32), "-r", str(png256))
        shutil.copyfile(png256, folder / ".directory.png")

    (folder / "desktop.ini").write_text(DESKTOP_INI, encoding="utf-8")
    (folder / ".directory").write_text(DOT_DIRECTORY, encoding="utf-8")
    print(f"done: {folder} (from {src.name})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".",
                        help="folder to process (default: current folder)")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="only print what would be done")
    args = parser.parse_args()

    missing = [t for t in TOOLS if shutil.which(t) is None]
    if missing:
        sys.exit(f"missing required tools: {', '.join(missing)}")

    errors = 0
    for dirpath, dirnames, _ in os.walk(args.root):
        dirnames.sort()
        try:
            process(Path(dirpath), args.dry_run)
        except (subprocess.CalledProcessError, OSError) as e:
            errors += 1
            print(f"error: {dirpath}: {e}", file=sys.stderr)

    if errors:
        sys.exit(f"{errors} folder(s) failed")


if __name__ == "__main__":
    main()
