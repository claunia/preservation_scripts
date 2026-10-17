#!/usr/bin/env python3
"""
Finalize Aaru compressed images.

Walks a directory tree looking for "<name>.compressed.aif" files that have a
matching "<name>.convert.log" and "<name>.compare.log". For each one it checks:

  * the convert log ends with "Conversion done"
  * the last run in the compare log says "Images have identical contents",
    and, if it compared the Data Position Measurements that follow it, that
    they "match within the measurement noise"
  * if "<name>.verify.log" exists, "Total errors+unknowns" is 0

If everything passes, "<name>.compressed.aif" replaces "<name>.aif" and the
auxiliary files (convert/compare/verify logs, mhddlog bin/png, verify png)
are removed.

Usage: finalize_compressed.py [ROOT] [--dry-run] [--no-color]
"""

import argparse
import os
import re
import sys
from pathlib import Path

SUFFIX = ".compressed.aif"
CLEANUP_SUFFIXES = (
    ".convert.log",
    ".compare.log",
    ".mhddlog.bin",
    ".mhddlog.png",
    ".verify.log",
    ".verify.png",
)
VERIFY_RE = re.compile(r"Total errors\+unknowns:\s*(\d+)")

# Every aaru run appends to the log starting with this line
RUN_START = "Start logging at"
IDENTICAL = "Images have identical contents"
DPM_TITLE = "Data Position Measurement comparison"
DPM_MATCH = "Data Position Measurements match within the measurement noise"
DPM_PROBLEMS = (
    "Only the first image has a Data Position Measurement",
    "Only the second image has a Data Position Measurement",
)


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"

    @classmethod
    def disable(cls):
        for name in ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN"):
            setattr(cls, name, "")


def last_line(path: Path) -> str:
    """Return the last non-empty line of a text file (reads only the tail)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 8192))
        tail = f.read().decode("utf-8", errors="replace")
    lines = [l.strip() for l in tail.splitlines() if l.strip()]
    return lines[-1] if lines else ""


def check_compare(compare: Path) -> list[str]:
    """Check the last run in a compare log, contents and DPM. Returns error messages."""
    text = compare.read_text(encoding="utf-8", errors="replace")
    run = text[max(0, text.rfind(RUN_START)):]

    if IDENTICAL not in run:
        verdict = next((l.strip() for l in run.splitlines() if l.startswith("Images have ")), None)
        found = f"it says {verdict!r}" if verdict else f"last line: {last_line(compare) or '<empty>'!r}"
        return [f"Compare log does not say '{IDENTICAL}' ({found})"]

    # Newer aaru compares the Data Position Measurements after the contents
    errors = [f"Compare log says '{p}'" for p in DPM_PROBLEMS if p in run]
    if DPM_TITLE in run and DPM_MATCH not in run:
        dpm = run[run.rfind(DPM_TITLE):].splitlines()
        result = next((l for l in reversed(dpm) if l.strip()), "")
        errors.append(f"Data Position Measurements do not match (last line: {result.strip()!r})")

    return errors


def check(base: Path) -> list[str]:
    """Run all checks for an image base path (no extension). Returns error messages."""
    errors = []

    convert = base.with_name(base.name + ".convert.log")
    line = last_line(convert)
    if "Conversion done" not in line:
        errors.append(f"Convert log does not end in 'Conversion done' (last line: {line or '<empty>'!r})")

    compare = base.with_name(base.name + ".compare.log")
    errors.extend(check_compare(compare))

    verify = base.with_name(base.name + ".verify.log")
    if verify.exists():
        text = verify.read_text(encoding="utf-8", errors="replace")
        matches = VERIFY_RE.findall(text)
        if not matches:
            errors.append("Verify log has no 'Total errors+unknowns' line")
        elif int(matches[-1]) != 0:
            errors.append(f"Verify log reports {matches[-1]} errors+unknowns")

    return errors


def finalize(base: Path, dry_run: bool) -> None:
    compressed = base.with_name(base.name + SUFFIX)
    target = base.with_name(base.name + ".aif")
    if not dry_run:
        os.replace(compressed, target)
    for suffix in CLEANUP_SUFFIXES:
        p = base.with_name(base.name + suffix)
        if p.exists() and not dry_run:
            p.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="Finalize verified *.compressed.aif images.")
    ap.add_argument("root", nargs="?", default=".", help="Root folder to scan (default: current directory)")
    ap.add_argument("-n", "--dry-run", action="store_true", help="Only check, don't move or delete anything")
    ap.add_argument("--no-color", action="store_true", help="Disable colored output")
    args = ap.parse_args()

    if args.no_color or not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        C.disable()

    root = Path(args.root).resolve()
    print(f"{C.BOLD}{C.CYAN}══ Aaru compressed image finalizer ══{C.RESET}")
    print(f"{C.DIM}Scanning:{C.RESET} {root}")
    if args.dry_run:
        print(f"{C.YELLOW}{C.BOLD}DRY RUN{C.RESET}{C.YELLOW} — no files will be changed{C.RESET}")
    print()

    candidates = sorted(root.rglob("*" + SUFFIX))
    ok, failed, skipped = [], [], []

    for compressed in candidates:
        base = compressed.with_name(compressed.name[: -len(SUFFIX)])
        rel = compressed.relative_to(root).parent / base.name

        missing = [s for s in (".convert.log", ".compare.log")
                   if not base.with_name(base.name + s).exists()]
        if missing:
            skipped.append(rel)
            print(f"{C.YELLOW}⚠ SKIP{C.RESET}  {rel}")
            print(f"        {C.DIM}missing {', '.join(missing)}{C.RESET}")
            continue

        try:
            errors = check(base)
        except OSError as e:
            errors = [f"Could not read logs: {e}"]

        if errors:
            failed.append((rel, errors))
            print(f"{C.RED}{C.BOLD}✗ FAIL{C.RESET}  {rel}")
            for err in errors:
                print(f"        {C.RED}→ {err}{C.RESET}")
            continue

        try:
            finalize(base, args.dry_run)
        except OSError as e:
            failed.append((rel, [f"Could not move/clean up files: {e}"]))
            print(f"{C.RED}{C.BOLD}✗ FAIL{C.RESET}  {rel}")
            print(f"        {C.RED}→ Could not move/clean up files: {e}{C.RESET}")
            continue

        ok.append(rel)
        verb = "would finalize" if args.dry_run else "finalized"
        print(f"{C.GREEN}{C.BOLD}✓ OK{C.RESET}    {rel} {C.DIM}({verb}){C.RESET}")

    print()
    print(f"{C.BOLD}══ Summary ══{C.RESET}")
    print(f"  {C.GREEN}✓ Succeeded: {len(ok)}{C.RESET}")
    print(f"  {C.RED}✗ Failed:    {len(failed)}{C.RESET}")
    print(f"  {C.YELLOW}⚠ Skipped:   {len(skipped)}{C.RESET}")

    if failed:
        print()
        print(f"{C.RED}{C.BOLD}Files needing attention:{C.RESET}")
        for rel, errors in failed:
            print(f"  {C.RED}• {rel}{C.RESET}")
            for err in errors:
                print(f"      {C.DIM}{err}{C.RESET}")

    if not candidates:
        print(f"\n{C.BLUE}No *{SUFFIX} files found.{C.RESET}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
