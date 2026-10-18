#!/usr/bin/env python3
"""Add Name, Publishers, Release and ReleaseDate to Aaru metadata.json or *.metadata.json files in subfolders.

Name        -> subfolder name
Publishers  -> [publisher from command line]
Release     -> "Coverdisc"
ReleaseDate -> the month in the subfolder name if there is one ("Septiembre 1997", "julio-agosto 2003",
               "IX-95"; with no year, the year closest to the disc date is used), otherwise
               the first day of the month after the first filesystem ModificationDate found
               (or, with --first-file, after the LastWriteTime of the first file in that filesystem).
               Filesystems with a missing or bogus (before 1985, when CD-ROM appeared, or in the future) ModificationDate fall back
               to their CreationDate, then to the newest file date, ignoring stray outlier files.

A backup (<file>.bak) is written next to each file before it is modified.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
         "XI": 11, "XII": 12}

MONTH_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\b(?:\s*[-/]\s*[a-z]+)?(?:\s+(\d{4}|\d{2})\b)?", re.IGNORECASE)
ROMAN_RE = re.compile(r"\b(" + "|".join(sorted(ROMAN, key=len, reverse=True)) + r")-(\d{4}|\d{2})\b")


def full_year(year):
    if len(year) == 4:
        return int(year)
    return 1900 + int(year) if int(year) >= 50 else 2000 + int(year)


def folder_month(name):
    """Return (month, year or None) from the folder name; double issues ("julio-agosto") use the first month."""
    m = ROMAN_RE.search(name)
    if m:
        return ROMAN[m[1]], full_year(m[2])
    m = MONTH_RE.search(name)
    if m:
        return MONTHS[m[1].lower()], full_year(m[2]) if m[2] else None
    return None


def parse_date(date_str):
    # Some dates carry "Z" and some don't; drop the zone so they can be compared
    return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)


def next_month(date_str):
    d = parse_date(date_str)
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


def closest_year(month, disc_year, disc_month):
    # Folder only says the month: pick the year that puts it nearest the disc-derived month
    return min((disc_year - 1, disc_year, disc_year + 1),
               key=lambda y: abs((y * 12 + month) - (disc_year * 12 + disc_month)))


# CD-ROM (Yellow Book) dates from 1985, so earlier dates are a mastering PC with an unset clock
FIRST_VALID_YEAR = 1985


def valid_date(date_str):
    try:
        return FIRST_VALID_YEAR <= parse_date(date_str).year <= datetime.now().year
    except (AttributeError, TypeError, ValueError):
        return False


def iter_files(contents):
    for f in contents.get("Files") or []:
        yield f
    for d in contents.get("Directories") or []:
        yield from iter_files(d)


def newest_file_date(contents):
    dates = sorted(f["LastWriteTime"] for f in iter_files(contents) if valid_date(f.get("LastWriteTime")))
    if not dates:
        return None
    # A few files with a wrong clock (e.g. 2010 on a 1997 disc) must not win: ignore anything
    # more than a year newer than the 95th percentile
    p95 = parse_date(dates[int(len(dates) * 0.95)])
    newest = max(d for d in dates if (parse_date(d) - p95).days <= 365)
    return f"newest file {newest}", newest


def iter_filesystems(meta):
    for disc in meta["OpticalDiscs"]:
        for track in disc.get("Track") or []:
            for partition in track.get("FileSystemInformation") or []:
                yield from partition.get("FileSystems") or []


def first_file_date(contents):
    # Root files first, then recurse into directories in listed order
    for f in contents.get("Files") or []:
        if f.get("LastWriteTime"):
            return f"{f['Name']} {f['LastWriteTime']}", f["LastWriteTime"]
    for d in contents.get("Directories") or []:
        found = first_file_date(d)
        if found:
            return found
    return None


def find_date(meta, use_first_file):
    # Partitioned discs (e.g. Apple partition map) have partitions without filesystems
    # before the real one, so take the first filesystem that has the wanted date
    for fs in iter_filesystems(meta):
        if use_first_file:
            found = first_file_date(fs.get("Contents") or {})
            if found:
                return found
            continue
        for field in ("ModificationDate", "CreationDate"):
            if valid_date(fs.get(field)):
                return f"{field} {fs[field]}", fs[field]
        found = newest_file_date(fs.get("Contents") or {})
        if found:
            return found
    raise KeyError("no file with a LastWriteTime found" if use_first_file
                   else "no filesystem or file with a valid date found")


def process(path, publisher, dry_run, use_first_file, use_folder):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    meta = data["AaruMetadata"]
    try:
        source, date = find_date(meta, use_first_file)
        disc_year, disc_month = next_month(date)
    except KeyError:
        source = disc_year = disc_month = None

    from_folder = folder_month(path.parent.name) if use_folder else None
    if from_folder and (from_folder[1] or disc_year):
        month, year = from_folder
        if year is None:
            year = closest_year(month, disc_year, disc_month)
        source = f"folder name (disc: {source})"
    elif disc_year:
        year, month = disc_year, disc_month
    else:
        raise KeyError(f"no date in folder name and {'no file with a LastWriteTime' if use_first_file else 'no filesystem or file with a valid date'} found")

    new_fields = {
        "Publishers": [publisher],
        "Name": path.parent.name,
        "Release": "Coverdisc",
        "ReleaseDate": f"{year:04d}-{month:02d}-01T00:00:00Z",
    }

    warning = "  WARNING: suspicious date" if not FIRST_VALID_YEAR <= year <= datetime.now().year else ""
    print(f"{path}: {source} -> {new_fields}{warning}")
    if dry_run:
        return

    # Put the new fields first (schema order), keeping everything else as is
    data["AaruMetadata"] = {**new_fields, **{k: v for k, v in meta.items() if k not in new_fields}}

    backup = path.with_name(path.name + ".bak")
    if not backup.exists():  # never overwrite the original backup on re-runs
        shutil.copy2(path, backup)

    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("publisher", help="Publisher name to set")
    parser.add_argument("folder", nargs="?", default=".", help="Folder containing the subfolders (default: current)")
    parser.add_argument("-f", "--first-file", action="store_true",
                        help="Use the LastWriteTime of the first file instead of the volume ModificationDate")
    parser.add_argument("--no-folder-date", action="store_true",
                        help="Ignore month/year in the subfolder name and always use the disc date")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    errors = 0
    for sub in sorted(p for p in Path(args.folder).iterdir() if p.is_dir()):
        files = sorted(sub.glob("*metadata.json"))
        if not files:
            print(f"{sub}: no metadata.json found, skipping", file=sys.stderr)
            continue
        for path in files:
            try:
                process(path, args.publisher, args.dry_run, args.first_file, not args.no_folder_date)
            except (KeyError, IndexError, ValueError, OSError) as e:
                errors += 1
                print(f"{path}: ERROR {e!r}", file=sys.stderr)

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
