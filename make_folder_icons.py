#!/usr/bin/env python3
"""Create Windows (desktop.ini/desktop.ico) and XDG (.directory/.directory.png)
folder icons from JPEG-XL scans, for the given folder and all its subfolders.

When a folder has no cover.jxl but has an inlay.jxl with the proportions of a
DVD (273x183mm) or Blu-ray (273x148mm) inlay, its rightmost 130mm (the front
cover) is cut out and used for the icons (it is not kept).
If the folder already had icons, they are only replaced when its desktop.ico
has no PNG (Vista) image, meaning it was taken from an .exe, not a scan."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREFERRED = ("cover.jxl", "front.jxl", "media.jxl", "media1.jxl", "up.jxl")
KEEP_SINGLE = ("cover.jxl", "front.jxl", "media.jxl", "media1.jxl", "inlay.jxl")
TOOLS = ("magick", "oxipng", "icotool")

# Inlay width x height in mm, the front cover is the rightmost COVER_MM of it
INLAYS = {"DVD": (273, 183), "Blu-ray": (273, 148)}
COVER_MM = 130
RATIO_TOLERANCE = 0.05

DESKTOP_INI = "[.ShellClassInfo]\nIconResource=.\\desktop.ico,0"
DOT_DIRECTORY = "[Desktop Entry]\nIcon=./.directory.png"


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def make_png(src, dst, size):
    geometry = f"{size}x{size}"
    run("magick", str(src), "-resize", geometry, "-background", "none",
        "-gravity", "center", "-extent", geometry, "-depth", "8", str(dst))
    run("oxipng", "--quiet", "-o", "max", str(dst))


def image_size(path):
    out = subprocess.run(("magick", "identify", "-ping", "-format", "%w %h\n", str(path)),
                         check=True, capture_output=True, text=True).stdout
    width, height = out.split()[:2]
    return int(width), int(height)


def inlay_kind(width, height):
    """Which inlay these pixel proportions match, or None."""
    ratio = width / height
    for kind, (w_mm, h_mm) in INLAYS.items():
        if abs(ratio / (w_mm / h_mm) - 1) <= RATIO_TOLERANCE:
            return kind
    return None


def inlay_cover_crop(inlay):
    """ImageMagick crop geometry of the front cover of an inlay, or None if
    the inlay does not have the proportions of a DVD or Blu-ray one."""
    width, height = image_size(inlay)
    kind = inlay_kind(width, height)
    if kind is None:
        print(f"ignore: {inlay} ({width}x{height}, ratio {width / height:.2f} "
              f"is not a DVD or Blu-ray inlay)")
        return None
    crop = round(width * COVER_MM / INLAYS[kind][0])
    return f"{crop}x{height}+0+0"


def has_png_icon(ico):
    """Whether an .ico holds any PNG (Vista style) image, as the ones made
    from scans do; icons taken from an .exe usually only have bitmaps."""
    try:
        data = ico.read_bytes()
    except OSError:
        return False
    if len(data) < 6 or data[:4] != b"\0\0\1\0":
        return False
    count = int.from_bytes(data[4:6], "little")
    for i in range(count):
        entry = data[6 + 16 * i:6 + 16 * (i + 1)]
        if len(entry) < 16:
            break
        offset = int.from_bytes(entry[12:16], "little")
        if data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n":
            return True
    return False


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

    # A cover cut out of the inlay is better than an icon taken from an .exe,
    # so it replaces those, but not icons already made from a scan
    crop = None
    if "cover.jxl" not in by_name and "inlay.jxl" in by_name:
        crop = inlay_cover_crop(by_name["inlay.jxl"])

    if (folder / ".directory").exists():
        if crop is None:
            print(f"skip: {folder} (has .directory)")
            return
        if has_png_icon(folder / "desktop.ico"):
            print(f"skip: {folder} (has .directory, icon already made from a scan)")
            return

    if crop is not None:
        src = by_name["inlay.jxl"]
        src_desc = f"front cover of {src.name}"
    else:
        src = next((by_name[n] for n in PREFERRED if n in by_name), None)
        if src is None:
            print(f"skip: {folder} (no cover/front/media/media1/up/inlay.jxl)")
            return
        src_desc = src.name

    if dry_run:
        print(f"would create icons: {folder} (from {src_desc})")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if crop is not None:
            cover = tmp / "cover.png"
            run("magick", str(src), "-gravity", "East", "-crop", crop, "+repage", str(cover))
            src = cover
        png256 = tmp / "256.png"
        png32 = tmp / "32.png"
        make_png(src, png256, 256)
        make_png(src, png32, 32)
        run("icotool", "-c", "-o", str(folder / "desktop.ico"),
            str(png32), "-r", str(png256))
        shutil.copyfile(png256, folder / ".directory.png")

    (folder / "desktop.ini").write_text(DESKTOP_INI, encoding="utf-8")
    (folder / ".directory").write_text(DOT_DIRECTORY, encoding="utf-8")
    print(f"done: {folder} (from {src_desc})")


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
