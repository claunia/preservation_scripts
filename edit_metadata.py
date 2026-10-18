#!/usr/bin/python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["rich"]
# ///
"""Fill in or edit the Aaru metadata.json of folders interactively, field by field, without any online database.

Every field is asked in turn, showing what the metadata has, a suggestion when there is one and the format
expected:
  Name            the folder name without what is in parentheses (editable)
  Version         "Versión 2.0" / "Version 2.0" / "v2.0" in the folder name
  Release type    Retail unless the metadata says otherwise, all types offered
  Release date    the newest file date of the filesystems in the discs (stray files with a wrong clock ignored)
  Part number     what is in parentheses in the folder name (Enter for none)
  Serial number   (Enter for none)
  Developers, Publishers, Authors, Performers
                  asked one after another until Enter; companies used before are offered
  Keywords, Categories
                  the same, offering common ones and the ones used before
  Languages       full names separated by ";" (Spanish; English; French), or Aaru codes (spa)
  Operating systems
                  none, or "name[version;version]" separated by ";" (Windows 95[4.00.950]; Windows NT[3.10;3.50]);
                  known names (Windows 95, XP, MS-DOS 6.22...) are stored as Aaru does: Windows, Windows NT, DOS...
                  with their version number
  Barcodes        EAN-13, UPC-A, EAN-8 or ISBN separated by ";" or ",", the type told by length and check digit;
                  barcodes and ISBNs in parentheses in the folder name are suggested
  Discs           optionally, the part and serial number of each disc, the part number suggested from what is in
                  parentheses in its image name
Subcategories and systems are left as they are. At the end all the changes are shown, and any field can be edited
again before saving.

The metadata used is metadata.json in the folder, otherwise each *.metadata.json sidecar in it (the answers for
the first are suggested for the next), otherwise a new metadata.json is created. A backup (<file>.bak) is written
before a file is modified for the first time.

The keywords, categories and people used are remembered (~/.local/share/edit_metadata/vocabulary.json) to be
offered again; --learn FOLDER also learns them from the metadata already below FOLDER.
"""

import argparse
import copy
import difflib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from metadata_ui import (KEY_ORDER, LANGUAGES, RELEASE_TYPES, Quit, ask, choose_part, confirm, console,
                         disc_title, fail, folder_barcodes, human_size, image_name, iso_date, keys, load, media_list,
                         metadata_files, parse_barcodes, part_candidates, part_numbers_in, save, set_parts, unique)

from rich import box
from rich.columns import Columns
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

VOCABULARY = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "edit_metadata" / \
    "vocabulary.json"
LEARNED = ("Developers", "Publishers", "Authors", "Performers", "Keywords", "Categories")

# Categories used in the dumps, plus the usual software categories (freedesktop.org menu categories and software
# genres), in the spelling the metadata should settle on
CATEGORIES = (
    "Videogame", "Games", "Compilation", "Demo", "Operating system", "Drivers", "Service pack", "Firmware update",
    "Software development kit", "Development environment", "Office suite", "Graphics", "Multimedia", "Music",
    "Soundtrack", "Video", "Audio", "Antivirus", "Security", "Backup", "Burning software", "Utilities", "Education",
    "Edutainment", "Encyclopedia", "Reference", "Documentation", "Internet", "Network", "ISP disc", "Book disc",
    "Magazine coverdisc", "Sampler", "Advertisement", "Karaoke", "Science", "Health and fitness", "Business",
    "Finance", "Fonts", "Clip art", "Screensavers", "Wallpapers", "Emulation", "Accessibility",
)
KEYWORDS = (
    "Star Wars", "Dungeons & Dragons", "DOOM", "Quake", "LEGO", "DUNE", "WarCraft", "StarCraft", "Diablo", "Star Trek",
    "The Sims", "SimCity", "Duke Nukem", "Halo", "Lemmings", "Wolfenstein", "Myst", "Barbie", "Bionicle", "Alien",
    "Aliens", "Predator", "Harry Potter", "Disney", "Linux", "Visual C++", "Visual Basic", "Symbian", "Compiler",
    "Development kit", "Video Game Music", "Soundtrack",
)

# Operating systems: what is typed or listed, and the name and version Aaru metadata stores for it
OPERATING_SYSTEMS = (
    ("DOS", "DOS", None), ("MS-DOS 3.30", "DOS", "3.30"), ("MS-DOS 5.0", "DOS", "5.00"), ("MS-DOS 6.0", "DOS", "6.00"),
    ("MS-DOS 6.22", "DOS", "6.22"), ("PC DOS", "PC DOS", None), ("DR-DOS", "DR-DOS", None),
    ("Windows", "Windows", None), ("Windows 3.0", "Windows", "3.00"), ("Windows 3.1", "Windows", "3.10"),
    ("Windows 3.11", "Windows", "3.11"), ("Windows 95", "Windows", "4.00.950"), ("Windows 98", "Windows", "4.10.1998"),
    ("Windows 98 SE", "Windows", "4.10.2222"), ("Windows Me", "Windows", "4.90.3000"),
    ("Windows NT", "Windows NT", None), ("Windows NT 3.1", "Windows NT", "3.10.528"),
    ("Windows NT 3.5", "Windows NT", "3.50.807"), ("Windows NT 3.51", "Windows NT", "3.51.1057"),
    ("Windows NT 4.0", "Windows NT", "4.00.1381"), ("Windows 2000", "Windows NT", "5.00.2195"),
    ("Windows XP", "Windows NT", "5.10.2600"), ("Windows XP x64", "Windows NT", "5.20.3790"),
    ("Windows Vista", "Windows NT", "6.00.6000"), ("Windows 7", "Windows NT", "6.10.7600"),
    ("Windows 8", "Windows NT", "6.20.9200"), ("Windows 8.1", "Windows NT", "6.30.9600"),
    ("Windows 10", "Windows NT", "10.0.10240"), ("Windows 11", "Windows NT", "10.0.22000"),
    ("Mac OS", "Mac OS", None), ("System 6", "Mac OS", "6.0"), ("System 7", "Mac OS", "7.0"),
    ("Mac OS 8", "Mac OS", "8.0"), ("Mac OS 9", "Mac OS", "9.0"), ("Mac OS X", "Mac OS X", None),
    ("macOS", "macOS", None), ("Linux", "Linux", None), ("FreeBSD", "FreeBSD", None), ("OS/2", "OS/2", None),
    ("OS/2 Warp 3", "OS/2", "3.0"), ("OS/2 Warp 4", "OS/2", "4.0"), ("BeOS", "BeOS", None), ("Solaris", "Solaris", None),
    ("IRIX", "IRIX", None), ("AIX", "AIX", None), ("HP-UX", "HP-UX", None), ("NeXTSTEP", "NeXTSTEP", None),
    ("UNIX", "UNIX", None), ("AmigaOS", "AmigaOS", None), ("RISC OS", "RISC OS", None), ("Atari TOS", "Atari TOS", None),
    ("CP/M", "CP/M", None), ("OpenVMS", "OpenVMS", None),
)
OS_BY_LABEL = {label.casefold(): (name, version) for label, name, version in OPERATING_SYSTEMS}

# Language names people type that are not the English name Aaru has
LANGUAGE_ALIASES = {
    "greek": "gre", "modern greek": "gre", "norwegian": "nor", "chinese": "chi", "persian": "per", "farsi": "per",
    "malay": "may", "castilian": "spa", "español": "spa", "castellano": "spa", "inglés": "eng", "ingles": "eng",
    "francés": "fre", "frances": "fre", "alemán": "ger", "aleman": "ger", "italiano": "ita", "portugués": "por",
    "portugues": "por", "catalán": "cat", "catala": "cat", "català": "cat", "euskera": "baq", "gallego": "glg",
    "holandés": "dut", "neerlandés": "dut", "flemish": "dut", "sueco": "swe", "danés": "dan", "noruego": "nor",
    "finés": "fin", "finlandés": "fin", "polaco": "pol", "ruso": "rus", "japonés": "jpn", "chino": "chi",
    "coreano": "kor", "checo": "cze", "húngaro": "hun", "griego": "gre", "turco": "tur", "árabe": "ara",
}
LANGUAGE_BY_NAME = {name.casefold(): code for code, name in LANGUAGES.items()} | LANGUAGE_ALIASES

FIRST_VALID_YEAR = 1985  # CD-ROM appeared; older file dates come from a mastering PC with its clock unset


class Back(Exception):
    """Go back to the summary."""


# ---------------------------------------------------------------- Suggestions from the folder and discs

def folder_title(folder_name):
    return " ".join(re.sub(r"[(\[][^)\]]*[)\]]", " ", folder_name).split())


def folder_version(folder_name):
    m = re.search(r"(?i)\bversi[oó]n\s*(\d[\w.]*)|\bv(\d+(?:\.\d+)+)\b", folder_name)
    return (m[1] or m[2]) if m else None


def parse_file_date(text):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except (AttributeError, TypeError, ValueError):
        return None


def iter_files(contents):
    for f in contents.get("Files") or []:
        yield f
    for d in contents.get("Directories") or []:
        yield from iter_files(d)


def newest_file_date(meta):
    """The newest file date in all the filesystems of all the discs, ignoring dates before CD-ROM existed, in the
    future, or more than a year newer than the 95th percentile (a few files with a wrong clock)."""
    dates = []
    for disc in meta.get("OpticalDiscs") or []:
        for track in disc.get("Track") or []:
            for partition in track.get("FileSystemInformation") or []:
                for fs in partition.get("FileSystems") or []:
                    for f in iter_files(fs.get("Contents") or {}):
                        date = parse_file_date(f.get("LastWriteTime"))
                        if date and FIRST_VALID_YEAR <= date.year and date <= datetime.now():
                            dates.append(date)
    if not dates:
        return None
    dates.sort()
    p95 = dates[int(len(dates) * 0.95)]
    return max(d for d in dates if (d - p95).days <= 365)


# ---------------------------------------------------------------- Vocabulary

def load_vocabulary():
    try:
        return json.loads(VOCABULARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def learn(vocabulary, meta):
    for key in LEARNED:
        counts = vocabulary.setdefault(key, {})
        for value in meta.get(key) or []:
            if isinstance(value, str) and value:
                counts[value] = counts.get(value, 0) + 1


def save_vocabulary(vocabulary):
    VOCABULARY.parent.mkdir(parents=True, exist_ok=True)
    tmp = VOCABULARY.with_name(VOCABULARY.name + ".tmp")
    tmp.write_text(json.dumps(vocabulary, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(VOCABULARY)


def learn_folder(vocabulary, folder):
    count = 0
    with console.status(f"Learning from the metadata below {folder}…"):
        for root, _, files in os.walk(folder):
            for name in files:
                if name.endswith("metadata.json"):
                    try:
                        learn(vocabulary, load(Path(root) / name)["AaruMetadata"])
                        count += 1
                    except (OSError, ValueError, KeyError):
                        pass
    console.print(f"[green]Learned from {count} metadata files[/green]")


def suggestions(vocabulary, key, builtin=(), limit=40):
    """Builtin and learned values, the most used first; values differing only in case are offered once."""
    counts = {}
    for value in builtin:
        counts.setdefault(value, 0)
    for value, count in (vocabulary.get(key) or {}).items():
        same = next((v for v in counts if v.casefold() == value.casefold()), value)
        counts[same] = counts.get(same, 0) + count
    order = {v: i for i, v in enumerate(builtin)}
    return sorted(counts, key=lambda v: (-counts[v], order.get(v, len(order)), v.casefold()))[:limit]


# ---------------------------------------------------------------- Languages and operating systems

def language_names(codes):
    return "; ".join(LANGUAGES.get(c, c) for c in codes)


def parse_languages(text):
    codes = []
    for part in filter(None, (p.strip() for p in text.split(";"))):
        found = LANGUAGE_BY_NAME.get(part.casefold()) or (part.lower() if part.lower() in LANGUAGES else None)
        # "Spanish, English" when "," was used to separate them (names like "Greek, Modern" have one)
        pieces = [LANGUAGE_BY_NAME.get(p.strip().casefold()) for p in part.split(",")] if not found else []
        if found:
            codes.append(found)
        elif pieces and all(pieces):
            codes += pieces
        else:
            close = difflib.get_close_matches(part.casefold(), LANGUAGE_BY_NAME, n=4, cutoff=0.6)
            hint = f" Did you mean {', '.join(LANGUAGES[LANGUAGE_BY_NAME[c]] for c in close)}?" if close else ""
            return None, f"Unknown language “{part}”.{hint}"
    return unique(codes), None


def split_top(text):
    """Split on ";" and "," outside brackets."""
    parts, depth, current = [], 0, ""
    for char in text:
        depth += char == "["
        depth -= char == "]"
        if char in ";," and depth <= 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return [p.strip() for p in parts + [current] if p.strip()]


def os_name(text):
    """Known capitalizations for operating system names typed in lower case."""
    known = {"dos": "DOS", "ms-dos": "MS-DOS", "nt": "NT", "xp": "XP", "me": "Me", "os/2": "OS/2", "os": "OS",
             "irix": "IRIX", "aix": "AIX", "hp-ux": "HP-UX", "beos": "BeOS", "macos": "macOS", "unix": "UNIX"}
    if text != text.lower():
        return text
    return " ".join(known.get(w, w.capitalize()) for w in text.split())


def parse_systems(text):
    systems = []
    for part in split_top(text):
        m = re.fullmatch(r"([^\[\]]+?)\s*(?:\[([^\]]*)\])?", part)
        if not m:
            return None, f"“{part}” is not name or name[version;version]"
        label, versions = m[1].strip(), [v.strip() for v in re.split(r"[;,]", m[2] or "") if v.strip()]
        if label.isdigit() and 1 <= int(label) <= len(OPERATING_SYSTEMS):
            _, name, version = OPERATING_SYSTEMS[int(label) - 1]
        elif label.casefold() in OS_BY_LABEL:
            name, version = OS_BY_LABEL[label.casefold()]
        else:
            name, version = os_name(label), None
        versions = versions or ([version] if version else [])
        existing = next((s for s in systems if s["Name"] == name), None)
        if existing:
            existing["Versions"] = unique(existing.get("Versions", []) + versions) or None
            if not existing["Versions"]:
                existing.pop("Versions")
        else:
            systems.append({"Name": name, **({"Versions": versions} if versions else {})})
    return systems, None


def normalize_systems(systems):
    """Old metadata may have "Version" instead of "Versions"."""
    result = []
    for s in systems or []:
        s = dict(s)
        if "Version" in s:
            s["Versions"] = unique((s.get("Versions") or []) + [s.pop("Version")])
        result.append(s)
    return result or None


def systems_text(systems):
    return "; ".join(s["Name"] + (f"[{';'.join(s['Versions'])}]" if s.get("Versions") else "")
                     for s in systems or [])


# ---------------------------------------------------------------- Fields

def show(kind, value):
    if value in (None, [], ""):
        return Text("—", style="dim")
    if kind == "list":
        return Text("; ".join(value))
    if kind == "languages":
        return Text(language_names(value))
    if kind == "date":
        return Text(value[:10])
    if kind == "os":
        return Text(systems_text(value))
    if kind == "barcodes":
        return Text("; ".join(f"{b.get('Type')} {b.get('Value')}" for b in value))
    return Text(str(value))


def step_panel(number, total, label, body, help_text):
    content = Table.grid(padding=(0, 1))
    content.add_column()
    for item in body:
        content.add_row(item)
    content.add_row(Text(help_text, style="dim italic"))
    console.print(Panel(content, title=Text.assemble((f" {number}/{total} ", "bold black on cyan"), " ",
                                                    (label, "bold")),
                        title_align="left", border_style="cyan", padding=(0, 1)))


def labeled(label, value, style=""):
    return Text.assemble((f"{label}: ", "bold"), value if isinstance(value, Text) else Text(str(value), style=style))


def numbered(items, style="", prefix=""):
    return Columns([Text.assemble((f"{prefix}{i}", "bold cyan"), " ", (item, style)) for i, item in enumerate(items, 1)],
                   padding=(0, 3))


class Editor:
    """Asks every field of one metadata file."""

    def __init__(self, path, meta, folder, vocabulary, previous):
        self.path, self.meta, self.folder, self.vocabulary = path, meta, folder, vocabulary
        self.previous = previous or {}  # the answers for the sidecar before, suggested when this one has nothing
        self.before = copy.deepcopy(meta)
        self.values = {k: copy.deepcopy(meta.get(k)) for k in KEY_ORDER}
        self.values["RequiredOperatingSystems"] = normalize_systems(self.values["RequiredOperatingSystems"])
        self.parts, self.serials = {}, {}
        self.steps = (
            ("Name", "Name", "text", self.ask_name),
            ("Version", "Version", "text", self.ask_version),
            ("Release", "Release type", "text", self.ask_release),
            ("ReleaseDate", "Release date", "date", self.ask_date),
            ("PartNumber", "Part number", "text", self.ask_part_number),
            ("SerialNumber", "Serial number", "text", self.ask_serial_number),
            ("Developers", "Developers", "list", lambda n: self.ask_list(n, "Developers", "developer")),
            ("Publishers", "Publishers", "list", lambda n: self.ask_list(n, "Publishers", "publisher")),
            ("Authors", "Authors", "list", lambda n: self.ask_list(n, "Authors", "author")),
            ("Performers", "Performers", "list", lambda n: self.ask_list(n, "Performers", "performer")),
            ("Keywords", "Keywords", "list", lambda n: self.ask_list(n, "Keywords", "keyword", KEYWORDS)),
            ("Categories", "Categories", "list", lambda n: self.ask_list(n, "Categories", "category", CATEGORIES)),
            ("Languages", "Languages", "languages", self.ask_languages),
            ("RequiredOperatingSystems", "Operating systems", "os", self.ask_systems),
            ("Barcodes", "Barcodes", "barcodes", self.ask_barcodes),
        )

    @property
    def total(self):
        return len(self.steps) + bool(media_list(self.meta))

    def suggested(self, key, fallback=None):
        return self.values.get(key) or self.previous.get(key) or fallback

    def header(self, number, label, key, kind, extra=(), help_text=""):
        body = [labeled("Current", show(kind, self.before.get(key) if key != "RequiredOperatingSystems"
                                        else normalize_systems(self.before.get(key))))]
        body += list(extra)
        step_panel(number, self.total, label, body, help_text)

    # ---- one function per field

    def ask_text(self, number, key, label, suggestion, source, help_text):
        extra = [labeled("Suggested", f"{suggestion}  ({source})", "green")] if suggestion and source else []
        self.header(number, label, key, "text", extra, help_text)
        answer = ask(f"{label}: ", suggestion or "")
        self.values[key] = answer or None

    def ask_name(self, number):
        suggestion = self.suggested("Name", folder_title(self.folder.name))
        source = None if self.values.get("Name") else "folder name"
        self.ask_text(number, "Name", "Name", suggestion, source,
                      "The name of the product as on its box. Edit the suggestion and press Enter; clear the line for "
                      "none.")

    def ask_version(self, number):
        suggestion = self.suggested("Version", folder_version(self.folder.name))
        source = None if self.values.get("Version") else "folder name"
        self.ask_text(number, "Version", "Version", suggestion, source,
                      "The version of the product, e.g. 2.0 or 1.01. Clear the line for none.")

    def ask_release(self, number):
        current = self.suggested("Release", "Retail")
        self.header(number, "Release type", "Release", "text", [numbered(RELEASE_TYPES)],
                    f"A number or the name of the type. Enter keeps {current}.")
        while True:
            answer = ask(f"Release type [{current}]: ")
            if not answer:
                self.values["Release"] = current
                return
            if answer.isdigit() and 1 <= int(answer) <= len(RELEASE_TYPES):
                self.values["Release"] = RELEASE_TYPES[int(answer) - 1]
                return
            matches = [r for r in RELEASE_TYPES if r.casefold() == answer.casefold()]
            if matches:
                self.values["Release"] = matches[0]
                return
            console.print("[red]One of the numbers or names listed[/red]")

    def ask_date(self, number):
        newest = newest_file_date(self.meta)
        suggestion = self.suggested("ReleaseDate", iso_date(newest) if newest else None)
        extra = []
        if newest:
            extra.append(labeled("Newest file in the discs", newest.strftime("%Y-%m-%d"), "green"))
        self.header(number, "Release date", "ReleaseDate", "date", extra,
                    "YYYY-MM-DD (YYYY-MM or YYYY for the first day of the month or year). Clear the line for none.")
        while True:
            answer = ask("Release date: ", suggestion[:10] if suggestion else "")
            if not answer:
                self.values["ReleaseDate"] = None
                return
            for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                try:
                    date = datetime.strptime(answer, fmt)
                except ValueError:
                    continue
                if date > datetime.now():
                    console.print("[yellow]That date is in the future[/yellow]")
                self.values["ReleaseDate"] = iso_date(date)
                return
            console.print("[red]Use YYYY-MM-DD, YYYY-MM or YYYY[/red]")

    def ask_part_number(self, number):
        candidates = [("folder name", p) for p in part_numbers_in(self.folder.name)]
        current = self.values.get("PartNumber")
        self.header(number, "Part number", "PartNumber", "text", [],
                    "The part number of the product (on the box or the disc label). "
                    + ("A number picks a suggestion. " if candidates else "")
                    + ("Enter keeps the current one, - for none." if current else "Enter for none."))
        self.values["PartNumber"] = choose_part("Suggestions", candidates, current)

    def ask_serial_number(self, number):
        current = self.values.get("SerialNumber")
        self.header(number, "Serial number", "SerialNumber", "text", [],
                    "The serial number of this copy. " +
                    ("Enter keeps the current one, - for none." if current else "Enter for none."))
        answer = ask("Serial number: ")
        if answer == "-":
            self.values["SerialNumber"] = None
        elif answer:
            self.values["SerialNumber"] = answer

    def ask_list(self, number, key, noun, builtin=()):
        items = list(self.values.get(key) or self.previous.get(key) or [])
        offered = suggestions(self.vocabulary, key, builtin, 40 if builtin else 20)
        help_text = (f"Type a {noun} to add it (several separated by “;”)"
                     + (", or the number of a suggestion" if offered else "")
                     + "; -N removes item N, -- removes all; Enter when done.")
        body = [Text("Suggestions", style="bold"), numbered(offered, "dim")] if offered else []
        self.header(number, key, key, "list", body, help_text)
        while True:
            now = Text("   ").join(Text.assemble((f"-{i}", "bold red"), " ", item) for i, item in enumerate(items, 1))
            console.print(labeled("Now", now if items else Text("none", style="dim")))
            answer = ask(f"Add {noun}: ")
            if not answer:
                self.values[key] = items or None
                return
            if answer == "--":
                items = []
                continue
            if re.fullmatch(r"-\d+", answer):
                index = int(answer[1:]) - 1
                if 0 <= index < len(items):
                    items.pop(index)
                else:
                    console.print("[red]No such item[/red]")
                continue
            for part in filter(None, (p.strip() for p in answer.split(";"))):
                if part.isdigit() and offered and 1 <= int(part) <= len(offered):
                    part = offered[int(part) - 1]
                if all(part.casefold() != i.casefold() for i in items):
                    items.append(part)

    def ask_languages(self, number):
        current = self.suggested("Languages")
        self.header(number, "Languages", "Languages", "languages", [],
                    "Full English names separated by “;”: Spanish; English; French (Aaru codes such as spa also "
                    "work). Clear the line for none.")
        prefill = language_names(current) if current else ""
        while True:
            answer = ask("Languages: ", prefill)
            if not answer:
                self.values["Languages"] = None
                return
            codes, error = parse_languages(answer)
            if error:
                console.print(f"[red]{error}[/red]")
                prefill = answer
                continue
            self.values["Languages"] = codes
            return

    def ask_systems(self, number):
        current = self.suggested("RequiredOperatingSystems")
        labels = [label for label, _, _ in OPERATING_SYSTEMS]
        self.header(number, "Operating systems", "RequiredOperatingSystems", "os",
                    [Text("Known", style="bold"), numbered(labels, "dim")],
                    "None, or name[version;version] separated by “;”: Windows 95[4.00.950]; Windows NT[3.10;3.50]. "
                    "A known name or its number stores its usual name and version (Windows 98 → Windows[4.10.1998]); "
                    "versions in brackets replace it. Clear the line for none.")
        prefill = systems_text(current) if current else ""
        while True:
            answer = ask("Operating systems: ", prefill)
            if not answer:
                self.values["RequiredOperatingSystems"] = None
                return
            systems, error = parse_systems(answer)
            if error:
                console.print(f"[red]{error}[/red]")
                prefill = answer
                continue
            self.values["RequiredOperatingSystems"] = systems
            return

    def ask_barcodes(self, number):
        current = self.suggested("Barcodes")
        found = folder_barcodes(self.folder.name)
        typed = [f"{b['Type']} {b['Value']}" for b in current or []]
        extra = [labeled("From the folder name", "; ".join(found), "green")] if found else []
        self.header(number, "Barcodes", "Barcodes", "barcodes", extra,
                    "EAN-13, UPC-A, EAN-8 or ISBN separated by “;” or “,”: 8436011230154; 84-9738-024-X. The type is "
                    "told by length and check digit; others go with their type before them (QR …). Clear the line "
                    "for none.")
        prefill = "; ".join(unique(typed + [b for b in found if not any(b.split()[-1] in t for t in typed)]))
        while True:
            answer = ask("Barcodes: ", prefill)
            if not answer:
                self.values["Barcodes"] = None
                return
            barcodes, error = parse_barcodes(answer)
            if error:
                console.print(f"[red]{error}[/red]")
                prefill = answer
                continue
            self.values["Barcodes"] = barcodes or None
            return

    def ask_discs(self, number):
        media = media_list(self.meta)
        step_panel(number, self.total, "Discs", [disc_table(self.meta, self.parts, self.serials)],
                   "m sets up the part and serial number of each disc one by one; Enter skips.")
        if ask("Discs: ").lower() == "m":
            self.edit_discs(range(len(media)))

    def edit_discs(self, indexes):
        media = media_list(self.meta)
        for i in indexes:
            disc = media[i][1]
            console.print(Rule(Text(f"Disc {i + 1}/{len(media)}: {image_name(disc) or '?'}", style="bold"),
                               style="blue"))
            self.parts[i] = choose_part(disc_title(disc), part_candidates(disc),
                                        self.parts.get(i, disc.get("PartNumber")))
            current = self.serials.get(i, disc.get("SerialNumber"))
            hint = f"Enter keeps {current}, - for none" if current else "Enter for none"
            answer = ask(f"Serial number of the disc ({hint}): ")
            self.serials[i] = None if answer == "-" else answer or current

    # ---- flow

    def run_all(self):
        for number, (_, _, _, function) in enumerate(self.steps, 1):
            function(number)
        if media_list(self.meta):
            self.ask_discs(len(self.steps) + 1)

    def changes(self):
        changed = [key for key, _, _, _ in self.steps if self.result(key) != self.original(key)]
        media = media_list(self.meta)
        changed += [f"disc {i + 1} part" for i, v in self.parts.items() if v != media[i][1].get("PartNumber")]
        changed += [f"disc {i + 1} serial" for i, v in self.serials.items() if v != media[i][1].get("SerialNumber")]
        return changed

    def result(self, key):
        return self.values.get(key) or None

    def original(self, key):
        value = self.before.get(key)
        return value or None

    def summary(self, dry_run):
        """Returns True to save, False to skip."""
        while True:
            table = Table(box=box.ROUNDED, header_style="bold", expand=True, pad_edge=False)
            table.add_column("#", justify="right", style="bold cyan", no_wrap=True)
            table.add_column("Field", style="bold", no_wrap=True)
            table.add_column("Before", ratio=1)
            table.add_column("After", ratio=1)
            for i, (key, label, kind, _) in enumerate(self.steps, 1):
                before = show(kind, self.original(key))
                after = show(kind, self.result(key))
                if self.result(key) != self.original(key):
                    after.stylize("bold green")
                    label = Text(label, style="bold green")
                else:
                    after.stylize("dim")
                table.add_row(str(i), label, before, after)
            changed = self.changes()
            console.print(Panel(table, title=Text.assemble(("Summary  ", "bold"), (self.path.name, "magenta")),
                                title_align="left", subtitle=f"{len(changed)} change{'s' if len(changed) != 1 else ''}",
                                subtitle_align="right", border_style="magenta"))
            if media_list(self.meta):
                console.print(Panel(disc_table(self.meta, self.parts, self.serials), title="Discs",
                                    title_align="left", border_style="blue"))
            hints = [("Enter", "show only, dry run" if dry_run else "save"), ("1-n", "edit field")]
            if media_list(self.meta):
                count = len(media_list(self.meta))
                hints.append(("m / m1-" + str(count), "edit all discs / one") if count > 1 else ("m", "edit the disc"))
            console.print(keys(*hints, ("a", "ask everything again"), ("s", "skip"), ("q", "quit")))
            answer = ask("› ")
            if not answer:
                return True
            if answer.isdigit() and 1 <= int(answer) <= len(self.steps):
                self.steps[int(answer) - 1][3](int(answer))
            elif media_list(self.meta) and re.fullmatch(r"m\d*", answer):
                count = len(media_list(self.meta))
                if answer == "m":
                    self.edit_discs(range(count))
                elif 1 <= int(answer[1:]) <= count:
                    self.edit_discs([int(answer[1:]) - 1])
                else:
                    console.print("[red]No such disc[/red]")
            elif answer == "a":
                self.run_all()
            elif answer == "s":
                return False
            elif answer == "q":
                raise Quit
            else:
                console.print("[red]?[/red]")

    def apply(self):
        meta = self.meta
        for key, _, _, _ in self.steps:
            if self.result(key) is None:
                meta.pop(key, None)
            else:
                meta[key] = self.result(key)
        set_parts(meta, self.parts)
        media = media_list(meta)
        for i, value in self.serials.items():
            disc = media[i][1]
            if value is None:
                disc.pop("SerialNumber", None)
            elif "SerialNumber" in disc:
                disc["SerialNumber"] = value
            else:  # after the part number, where Aaru puts it
                items = list(disc.items())
                at = list(disc).index("PartNumber") + 1 if "PartNumber" in disc else len(items)
                disc.clear()
                disc.update(items[:at] + [("SerialNumber", value)] + items[at:])
        known = [k for k in KEY_ORDER if k in meta]
        return {**{k: meta[k] for k in known}, **{k: v for k, v in meta.items() if k not in known}}


def disc_table(meta, parts, serials):
    table = Table(box=box.SIMPLE, header_style="bold", expand=True, pad_edge=False)
    table.add_column("#", justify="right", style="bold cyan", no_wrap=True)
    for column in ("Image", "Type", "Part number", "Serial number", "Disc", "Size"):
        table.add_column(column, no_wrap=column != "Image")
    for i, (key, m) in enumerate(media_list(meta)):
        cells = []
        for pending, field in ((parts, "PartNumber"), (serials, "SerialNumber")):
            value = pending.get(i, m.get(field))
            text = Text(value or "—", style="" if value else "dim")
            if i in pending and value != m.get(field):
                text.stylize("bold green")
                text.append("  cleared" if value is None else "", style="green")
            cells.append(text)
        sequence = m.get("Sequence") or {}
        kind = " / ".join(str(m[k]) for k in ("DiscType", "DiscSubType") if m.get(k)) or key
        table.add_row(str(i + 1), image_name(m) or "?", kind, *cells,
                      f"{sequence.get('MediaSequence', '?')}/{sequence.get('TotalMedia', '?')}",
                      human_size(m.get("Size")))
    return table


# ---------------------------------------------------------------- Main

def process(folder, args, vocabulary):
    console.print(Rule(Text(folder.name, style="bold"), style="cyan"))
    paths = metadata_files(folder)
    if not paths[0].exists() and any(folder.glob("*.aif")):
        console.print("[yellow]This folder has images but no metadata: a new metadata.json without the discs would "
                      "make create_sidecars.sh skip the folder.[/yellow]")
        if not confirm("Create it anyway?"):
            return
    previous = None
    for path in paths:
        try:
            data = load(path)
        except (OSError, ValueError) as e:
            console.print(f"[red]✖ {path}: {e}[/red]")
            continue
        if len(paths) > 1:
            console.print(Text(f"▸ {path.name}", style="bold magenta"))
        editor = Editor(path, data["AaruMetadata"], folder, vocabulary, previous)
        editor.run_all()
        if not editor.summary(args.dry_run):
            console.print(f"[yellow]{path.name} not changed[/yellow]")
            continue
        previous = {key: editor.result(key) for key, _, _, _ in editor.steps}
        if not editor.changes():
            console.print(f"[dim]{path.name}: nothing changes[/dim]")
        elif args.dry_run:
            console.print(f"[yellow]Dry run: {path.name} not written[/yellow]")
        else:
            data["AaruMetadata"] = editor.apply()
            save(path, data)
            learn(vocabulary, data["AaruMetadata"])
            save_vocabulary(vocabulary)
            console.print(f"[bold green]✔ {path.name} written[/bold green]")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folders", nargs="*", type=Path,
                        help="Folders with the metadata (default: the current folder, or none with --learn)")
    parser.add_argument("-r", "--subfolders", action="store_true",
                        help="Process every subfolder of the given folders")
    parser.add_argument("--learn", type=Path, metavar="FOLDER",
                        help="Learn the keywords, categories and people used in the metadata below FOLDER "
                             "(then edit the folders given, if any)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Ask everything but do not write")
    args = parser.parse_args()

    folders = []
    for folder in args.folders or ([] if args.learn else [Path(".")]):
        if not folder.is_dir():
            fail(f"{folder} is not a folder")
        folders += sorted(p for p in folder.iterdir() if p.is_dir()) if args.subfolders else [folder]

    vocabulary = load_vocabulary()
    if args.learn:
        learn_folder(vocabulary, args.learn)
        save_vocabulary(vocabulary)
    try:
        for folder in folders:
            process(folder.resolve(), args, vocabulary)
    except Quit:
        console.print("[dim]Bye[/dim]")


if __name__ == "__main__":
    main()
