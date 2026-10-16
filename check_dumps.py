#!/usr/bin/env python3
"""Check every dump under the given folder (default: current folder).

A dump is OK when:
  - its dump log (<name>.log) says "0 sectors could not be read",
  - its verify log (<name>.verify.log), if there is one, has 0 errors+unknowns,
  - its resume file (<name>.resume.json) has no bad blocks.

When a log contains several runs (resumed dumps, repeated verifies), the last
result is the one that counts."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Logs that are not the dump log itself
OTHER_LOGS = (".verify", ".compare", ".convert", ".sub", ".error")

UNREADABLE_RE = re.compile(r"(\d+) sectors could not be read")
VERIFY_RE = re.compile(r"Total errors\+unknowns: (\d+)")


def colour(text, code):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def last_match(path, regex):
    """Last captured number of regex in path, or None if it never appears."""
    # Some logs contain binary garbage, so do not insist on valid UTF-8
    matches = regex.findall(path.read_text(encoding="utf-8", errors="replace"))
    return int(matches[-1]) if matches else None


def dump_names(folder, files):
    """Base names of the dumps in a folder."""
    names = set()
    for f in files:
        if f.endswith(".resume.json"):
            names.add(f[:-len(".resume.json")])
        elif f.endswith(".aif") and not f.endswith(".compressed.aif"):
            names.add(f[:-len(".aif")])
        elif f.endswith(".log") and not f[:-len(".log")].endswith(OTHER_LOGS):
            names.add(f[:-len(".log")])
    return sorted(names)


def check_dump(folder, name):
    """List of problems found in a dump, empty if it is OK."""
    problems = []

    log = folder / f"{name}.log"
    if not log.is_file():
        problems.append("no dump log")
    else:
        unreadable = last_match(log, UNREADABLE_RE)
        if unreadable is None:
            problems.append("dump log has no result (dump did not finish?)")
        elif unreadable:
            problems.append(f"{unreadable} sectors could not be read")

    verify = folder / f"{name}.verify.log"
    if verify.is_file():
        errors = last_match(verify, VERIFY_RE)
        if errors is None:
            problems.append("verify log has no result (verify did not finish?)")
        elif errors:
            problems.append(f"verify found {errors} errors+unknowns")

    resume = folder / f"{name}.resume.json"
    if not resume.is_file():
        problems.append("no resume.json")
    else:
        try:
            data = json.loads(resume.read_text(encoding="utf-8-sig"))["AaruResume"]
        except (ValueError, KeyError) as e:
            problems.append(f"unreadable resume.json ({e})")
        else:
            bad = len(data.get("BadBlocks") or [])
            if bad:
                problems.append(f"resume.json has {bad} bad blocks")
            if data.get("NextBlock", 0) <= data.get("LastBlock", 0):
                problems.append("resume.json says the dump did not reach the last block")

    return problems


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".",
                        help="folder to check (default: current folder)")
    parser.add_argument("-f", "--failures-only", action="store_true",
                        help="only print the dumps that failed")
    args = parser.parse_args()

    ok = failed = 0
    for dirpath, dirnames, files in os.walk(args.root):
        dirnames.sort()
        folder = Path(dirpath)
        for name in dump_names(folder, files):
            problems = check_dump(folder, name)
            path = folder / name
            if problems:
                failed += 1
                print(f"{colour('DUMP FAILURE', '1;31')}: {path}")
                for p in problems:
                    print(f"    {p}")
            else:
                ok += 1
                if not args.failures_only:
                    print(f"{colour('DUMP OK', '1;32')}: {path}")

    print(f"\n{ok} OK, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
