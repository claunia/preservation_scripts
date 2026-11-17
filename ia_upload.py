#!/usr/bin/python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["rich"]
# ///
"""Upload dump folders to the Internet Archive, one item per folder, with the item metadata taken from the
Aaru metadata.

Login: the first time (or with --login) the archive.org keys are taken from an existing ~/.config/ia.ini, or
obtained by logging in with the archive.org email and password, and stored in
~/.config/ia_upload/credentials.json (readable only by the user). --logout removes them. The IA_ACCESS_KEY
and IA_SECRET_KEY environment variables, when set, are used instead.

Item: the identifier is made from the folder name (accents removed, other characters as "_") and checked to
be free on archive.org, or to be an item of ours, which is then completed. It is shown for confirmation
together with the metadata, and both can be edited.

Metadata: the title is the folder name, as it is. metadata.json in the folder, otherwise its *.metadata.json
sidecars, is converted: Developers/Authors/Performers to creator, Publishers to publisher, ReleaseDate to date, Languages to
language, Keywords/Categories/Subcategories/Systems/required operating systems to subject, plus version,
release type, part and serial numbers and barcodes, and a description listing each disc (type, size, part
number, ring codes, track checksums, drive used). Audio CDs go to opensource_audio (audio), folders under
"Movies..." to opensource_movies (movies), anything else to open_source_software (software), unless
--collection/--mediatype are given. --test uploads to test_collection, which archive.org removes after 30
days.

Files: every file in the folder except the folder icons (desktop.ini, desktop.ico, .directory,
.directory.png), info.txt, PAR2 recovery files, backups (*.bak, *.tmp), *.sidecar.log and
*.compressed.aif pending finalization.
Before uploading, front.png is made from front.jxl, and __ia_thumb.jpg, so that the cover is the item
thumbnail, from front.png, otherwise from cover.jxl, the front cover of a CD, DVD or Blu-ray inlay.jxl or
the folder icon. A cover.png made by earlier versions is removed.
Subfolders are not uploaded.

Resume: files bigger than --part-size are sent in parts (S3 multipart upload), and the parts sent are
recorded in ~/.local/state/ia_upload/<identifier>.json, so after an interruption (Ctrl+C, network errors)
running the script again continues where it stopped, also inside a file. Files already on the item with the
same size and MD5 are skipped. On an item that already existed, the metadata is then updated to the one
reviewed (except the collection).

When archive.org asks to slow down (too many tasks queued for the item or the account), all the uploads
pause together, longer each time (30 s, 1 min, 2 min... up to 15 min), and go on by themselves.

Speed: archive.org is often slow on each connection, so --jobs (default 4) files, or parts of a big file,
are sent at once, each over its own connection. The memory used is up to --jobs times --part-size."""

import argparse
import configparser
import base64
import getpass
import hashlib
import io
import json
import os
import re
import queue
import random
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from metadata_ui import (Quit, ask, confirm, console, fail, human_size, image_name, load, media_list,
                         metadata_files, unique)

from make_folder_icons import inlay_cover_crop
from rich.progress import (BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn,
                           TransferSpeedColumn)
from rich.table import Table

S3 = "https://s3.us.archive.org"
ARCHIVE = "https://archive.org"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ia_upload"
CREDENTIALS = CONFIG_DIR / "credentials.json"
IA_INI = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ia.ini"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "ia_upload"

SKIP_NAMES = {"desktop.ini", "desktop.ico", ".directory", ".directory.png", "info.txt"}
SKIP_SUFFIXES = (".bak", ".tmp", ".sidecar.log", ".compressed.aif", ".par2")
THUMBNAIL = "__ia_thumb.jpg"
MAX_PARTS = 10000
RETRIES = 10


class IAError(Exception):
    pass


# ---------------------------------------------------------------- HTTP


class Body(io.RawIOBase):
    """Request body that reports the bytes sent, for the progress bars."""

    def __init__(self, data, sent):
        self.data = memoryview(data)
        self.pos = 0
        self.sent = sent

    def readable(self):
        return True

    def read(self, size=-1):
        end = len(self.data) if size < 0 else min(len(self.data), self.pos + size)
        chunk = self.data[self.pos:end].tobytes()
        self.pos = end
        if chunk:
            self.sent(len(chunk))
        return chunk


class Throttle:
    """Pause shared by all the uploads when archive.org asks to slow down (too many tasks queued for the
    item or the account): they all wait, longer each time it happens again, instead of retrying together."""

    def __init__(self):
        self.lock = threading.Lock()
        self.until = 0.0
        self.level = 0

    def wait(self):
        while (remaining := self.until - time.monotonic()) > 0:
            time.sleep(min(remaining, 5))

    def slow_down(self, wait=None):
        with self.lock:
            if time.monotonic() < self.until:
                return  # already paused by another upload
            self.level += 1
            delay = int(wait) if wait and wait.isdigit() else min(900, 30 * 2 ** (self.level - 1))
            delay = round(delay * random.uniform(1, 1.25))
            self.until = time.monotonic() + delay
        console.print(f"[yellow]⚠ archive.org asks to slow down (too many tasks queued), pausing the uploads "
                      f"{delay} s[/yellow]")

    def success(self):
        if self.level:
            with self.lock:
                self.level = max(0, self.level - 1)


THROTTLE = Throttle()


def request(method, url, headers=None, data=None, sent=None, ok=(200,)):
    """Send a request, retrying on server overload and network errors. Returns (status, headers, body).
    sent(n) is called as the body goes out, with a negative n to undo an attempt that failed. Requests to
    slow down pause all of them (see Throttle) and do not count as failed attempts."""
    attempt = 0
    while attempt < RETRIES:
        THROTTLE.wait()
        body = None
        progress = [0]

        def count(n):
            progress[0] += n
            if sent:
                sent(n)

        if data is not None:
            body = Body(data, count)
        req = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
        if data is not None:
            req.add_header("Content-Length", str(len(data)))
        wait = None
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                reply = resp.status, resp.headers, resp.read()
            THROTTLE.success()
            return reply
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code in ok:
                return e.code, e.headers, text.encode()
            if e.code in (429, 503) and ("slowdown" in text.lower() or "reduce your request rate" in text.lower()):
                if sent and progress[0]:
                    sent(-progress[0])
                THROTTLE.slow_down(e.headers.get("Retry-After"))
                continue
            if e.code not in (408, 429, 500, 502, 503, 504):
                raise IAError(f"{method} {url}: HTTP {e.code} {s3_message(text) or e.reason}") from None
            wait = e.headers.get("Retry-After")
            problem = f"HTTP {e.code} {s3_message(text) or e.reason}"
        except (urllib.error.URLError, OSError) as e:
            problem = str(getattr(e, "reason", e))
        if sent and progress[0]:
            sent(-progress[0])
        delay = int(wait) if wait and wait.isdigit() else min(300, 5 * 2 ** attempt)
        attempt += 1
        console.print(f"[yellow]⚠ {problem}, retrying in {delay} s ({attempt}/{RETRIES})[/yellow]")
        time.sleep(delay)
    raise IAError(f"{method} {url}: gave up after {RETRIES} attempts")


def s3_message(text):
    match = re.search(r"<Message>(.*?)</Message>", text or "", re.S)
    return match.group(1).strip() if match else ""


def run_parallel(jobs, tasks, stop):
    """Run the callables in tasks with up to jobs threads, stopping at the first error, which is raised
    again. The threads are daemons, so Ctrl+C does not have to wait for the uploads in progress."""
    tasks = list(tasks)
    if jobs <= 1 or len(tasks) <= 1:
        for task in tasks:
            if stop.is_set():
                raise IAError("stopped")
            task()
        return
    todo, errors = queue.Queue(), []
    for task in tasks:
        todo.put(task)

    def worker():
        while not stop.is_set() and not errors:
            try:
                task = todo.get_nowait()
            except queue.Empty:
                return
            try:
                task()
            except BaseException as e:  # noqa: BLE001 - raised again in the main thread
                errors.append(e)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(jobs, len(tasks)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        while thread.is_alive():
            thread.join(0.5)
    if errors:
        raise errors[0]
    if stop.is_set():
        raise IAError("stopped")


def get_json(url, headers=None):
    _, _, body = request("GET", url, headers)
    return json.loads(body or b"{}")


# ---------------------------------------------------------------- Login


def write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def auth_header(keys):
    return {"Authorization": f"LOW {keys['access']}:{keys['secret']}"}


def check_keys(keys):
    """True if archive.org accepts the keys, False if it rejects them, None if it cannot be asked. When
    accepted, the email and screen name of the account are added to keys if archive.org gives them."""
    try:
        info = get_json(f"{S3}/?check_auth=1", auth_header(keys))
    except (IAError, ValueError):
        return None
    if not info.get("authorized"):
        return False
    for field, key in (("email", "username"), ("screenname", "screenname")):
        if info.get(key):
            keys[field] = info[key]
    return True


def login():
    if IA_INI.exists():
        ini = configparser.ConfigParser(interpolation=None)
        ini.read(IA_INI, encoding="utf-8")
        access, secret = ini.get("s3", "access", fallback=""), ini.get("s3", "secret", fallback="")
        if access and secret and confirm(f"Use the archive.org keys in {IA_INI}?", True):
            # The ia tool keeps the email only in the login cookie, as "email; path=..."
            user = urllib.parse.unquote(ini.get("cookies", "logged-in-user", fallback="")).split(";")[0].strip()
            keys = {"access": access, "secret": secret, "email": user}
            if check_keys(keys) is not False:
                return keys
            console.print(f"[yellow]⚠ archive.org does not accept the keys in {IA_INI} any more[/yellow]")

    console.print("Log in to archive.org (the password is only used to obtain the upload keys, it is not stored).")
    email = ask("Email: ")
    password = getpass.getpass("Password: ")
    data = urllib.parse.urlencode({"email": email, "password": password}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{ARCHIVE}/services/xauthn/?op=login", data=data),
                                    timeout=60) as resp:
            reply = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            reply = json.loads(e.read())
        except ValueError:
            fail(f"Login failed: HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        fail(f"Login failed: {e.reason}")
    if not reply.get("success"):
        reason = (reply.get("values") or {}).get("reason") or reply.get("error") or "unknown error"
        reason = {"account_not_found": "no account with that email",
                  "account_bad_password": "wrong password"}.get(reason, reason)
        fail(f"Login failed: {reason}")
    values = reply["values"]
    return {"access": values["s3"]["access"], "secret": values["s3"]["secret"],
            "screenname": values.get("screenname", ""), "email": values.get("email") or email}


def credentials(force=False):
    if not force and os.environ.get("IA_ACCESS_KEY") and os.environ.get("IA_SECRET_KEY"):
        keys = {"access": os.environ["IA_ACCESS_KEY"], "secret": os.environ["IA_SECRET_KEY"]}
        if check_keys(keys) is False:
            fail("archive.org does not accept the keys in IA_ACCESS_KEY and IA_SECRET_KEY")
        return keys
    if not force and CREDENTIALS.exists():
        try:
            keys = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
        except ValueError:
            keys = {}
        if not (keys.get("access") and keys.get("secret")):
            console.print(f"[yellow]⚠ {CREDENTIALS} cannot be read, logging in again[/yellow]")
        elif check_keys(keys) is False:
            console.print("[yellow]⚠ archive.org does not accept the stored keys any more, logging in again[/yellow]")
        else:
            return keys
    keys = login()
    write_private(CREDENTIALS, keys)
    who = keys.get("screenname") or keys.get("email") or "unknown account"
    console.print(f"[green]✔[/green] Logged in as {who}, keys stored in {CREDENTIALS}")
    return keys


# ---------------------------------------------------------------- Folder, identifier and metadata


def folder_files(folder):
    files, skipped = [], []
    for p in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if p.is_dir():
            console.print(f"[yellow]⚠ subfolder {p.name} is not uploaded[/yellow]")
        elif not p.is_file():
            continue
        elif p.name.lower() in SKIP_NAMES or p.name.lower().endswith(SKIP_SUFFIXES):
            skipped.append(p)
        else:
            files.append(p)
    if any(p.name.lower().endswith(".compressed.aif") for p in skipped):
        console.print("[yellow]⚠ there are *.compressed.aif images pending finalization, they are not uploaded[/yellow]")
    # Small files first, so the item is created by a simple upload, and metadata.json last, so the item is
    # derived once, when everything is there
    files.sort(key=lambda p: (p.name == "metadata.json", p.stat().st_size > 64 * 1024 * 1024, p.name.lower()))
    return files


def convert_image(source, target, options, what, dry_run):
    """Write target from source with magick, unless it is already there and newer than source."""
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return
    if dry_run:
        console.print(f"[dim]dry run: would create {target.name} from {what}[/dim]")
        return
    tmp = target.with_name(target.name + ".tmp")
    kind = "JPEG" if target.suffix.lower() == ".jpg" else "PNG"
    try:
        subprocess.run(("magick", str(source), *options, f"{kind}:{tmp}"), check=True, capture_output=True)
        tmp.replace(target)
    except (OSError, subprocess.CalledProcessError) as e:
        tmp.unlink(missing_ok=True)
        detail = e.stderr.decode(errors="replace").strip() if isinstance(e, subprocess.CalledProcessError) else e
        console.print(f"[yellow]⚠ cannot create {target.name} from {what}: {detail}[/yellow]")
        return
    console.print(f"[green]✔[/green] created {target.name} from {what}")


def make_covers(folder, dry_run):
    """Create front.png from front.jxl, and __ia_thumb.jpg, which archive.org uses as the item thumbnail
    instead of picking one of the images itself (often a .graph.png), from front.png, otherwise from
    cover.jxl, the front cover cut out of a CD, DVD or Blu-ray inlay.jxl or the folder icon (.directory.png).
    A cover.png left by earlier versions, made from one of those, is removed."""
    by_name = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    crop = None
    if "front.jxl" in by_name:
        front = by_name.get("front.png") or folder / "front.png"
        convert_image(by_name["front.jxl"], front, (), "front.jxl", dry_run)
        source = front if front.exists() else by_name["front.jxl"]
    elif "cover.jxl" in by_name:
        source = by_name["cover.jxl"]
    elif "inlay.jxl" in by_name and (crop := inlay_cover_crop(by_name["inlay.jxl"])):
        source = by_name["inlay.jxl"]
    elif ".directory.png" in by_name:
        source = by_name[".directory.png"]
    else:
        return
    old = by_name.get("cover.png")
    if old and source.name.lower() != "front.png" and old.stat().st_mtime >= source.stat().st_mtime:
        if dry_run:
            console.print(f"[dim]dry run: would remove {old.name}, made from {source.name}[/dim]")
        else:
            old.unlink()
            console.print(f"[green]✔[/green] removed {old.name}, made from {source.name}")
    options = ("-gravity", "East", "-crop", crop, "+repage") if crop else ()
    what = f"the front cover of {source.name}" if crop else source.name
    convert_image(source, folder / THUMBNAIL, (*options, "-flatten", "-resize", "600x600>", "-quality", "90"),
                  what, dry_run)


def make_identifier(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text[:100].rstrip("._-")


UNAVAILABLE = "\0unavailable"


def item_owner(identifier):
    """None when the identifier is free, otherwise the uploader of the item ("" if not known), or
    UNAVAILABLE when archive.org does not allow it although there is no item to see (deleted or hidden
    items, or one differing only in case)."""
    info = get_json(f"{ARCHIVE}/metadata/{identifier}")
    if info:
        return (info.get("metadata") or {}).get("uploader", "")
    try:
        check = get_json(f"{ARCHIVE}/services/check_identifier.php?output=json&identifier="
                         f"{urllib.parse.quote(identifier, safe='')}")
    except (IAError, ValueError):
        return None
    return UNAVAILABLE if check.get("code") == "not_available" else None


def choose_identifier(folder, wanted, keys, yes):
    """Free identifier, or one of our items to complete. Returns (identifier, exists)."""
    base = wanted or make_identifier(folder.resolve().name)
    email = (keys or {}).get("email", "").lower()
    candidate, n = base, 1
    while True:
        if not candidate:
            candidate = make_identifier(ask("Identifier: "))
            continue
        owner = item_owner(candidate)
        if owner is None:
            return candidate, False
        if owner == UNAVAILABLE:
            if wanted:
                raise IAError(f"identifier {candidate} is not available on archive.org")
            console.print(f"[cyan]ℹ {candidate} is not available on archive.org[/cyan]")
        elif owner and email and owner.lower() == email:
            console.print(f"[cyan]ℹ {candidate} is already one of our items, it will be completed[/cyan]")
            return candidate, True
        if not owner and keys and not yes and confirm(f"{candidate} exists, upload into it?"):
            return candidate, True
        if wanted:
            raise IAError(f"identifier {candidate} is already used by another item")
        n += 1
        candidate = f"{base[:96]}_{n}"


def aaru_metadata(folder):
    """Top level metadata and list of media of the folder, from metadata.json or its sidecars."""
    top, media = {}, []
    for path in metadata_files(folder):
        if not path.exists():
            continue
        try:
            meta = load(path)["AaruMetadata"]
        except ValueError as e:
            console.print(f"[yellow]⚠ {path.name}: {e}[/yellow]")
            continue
        for key, value in meta.items():
            if key not in ("OpticalDiscs", "BlockMedias", "LinearMedias", "AudioMedias") and value \
                    and not top.get(key):
                top[key] = value
        media += media_list(meta)
    return top, media


TRACK_CHECKSUMS = (("CRC32", "CRC32"), ("MD5", "Md5"), ("SHA-1", "Sha1"))


def checksum(media, kind):
    return next((c.get("Value") for c in media.get("Checksums") or [] if c.get("Type") == kind), "")


def texts(items):
    return [i.get("Text", "") if isinstance(i, dict) else str(i) for i in items or [] if i]


def disc_description(media, number, total):
    title = (media.get("Sequence") or {}).get("Title") or re.sub(r"\.aif$", "", image_name(media), flags=re.I)
    head = f"Disc {number} of {total}"
    lines = [f"<b>{head}{': ' + title if title else ''}</b>"]
    kind = " / ".join(x for x in (media.get("DiscType"), media.get("DiscSubType")) if x)
    if kind or media.get("Size"):
        lines.append(", ".join(x for x in (kind, human_size(media.get("Size"))) if x))
    for label, key in (("Part number", "PartNumber"), ("Serial number", "SerialNumber")):
        if media.get(key):
            lines.append(f"{label}: {media[key]}")
    for label, key in (("Ring code", "RingCode"), ("Mastering SID", "MasteringSid"), ("Toolstamp", "Toolstamp"),
                       ("Mould SID", "MouldSid"), ("Mould text", "MouldText")):
        values = texts(media.get(key))
        if values:
            lines.append(f"{label}: {'; '.join(values)}")
    # The checksums of the tracks, not of the image: they only depend on the contents of the disc, so they
    # can be compared with other dumps of it
    for track in media.get("Track") or []:
        sums = ", ".join(f"{label} {checksum(track, kind)}" for label, kind in TRACK_CHECKSUMS
                         if checksum(track, kind))
        if sums:
            number = (track.get("Sequence") or {}).get("Number")
            about = ", ".join(x for x in (track.get("Type"), human_size(track.get("Size"))) if x)
            lines.append(f"Track {number if number is not None else '?'}{' (' + about + ')' if about else ''}: {sums}")
    dumped = []
    for hw in media.get("DumpHardware") or []:
        drive = " ".join(x for x in (hw.get("Manufacturer"), hw.get("Model"), hw.get("Firmware")) if x)
        soft = hw.get("Software") or {}
        tool = " ".join(x for x in (soft.get("Name"), soft.get("Version")) if x)
        dumped.append(f"Dumped with {tool or 'unknown software'}{' on ' + drive if drive else ''}")
    return "<br />".join(lines + unique(dumped))


def convert_metadata(folder, top, media):
    """IA metadata (dict of str or list of str) from the Aaru metadata."""
    md = {"title": folder.resolve().name}
    creators = unique((top.get("Developers") or []) + (top.get("Authors") or []) + (top.get("Performers") or []))
    if creators:
        md["creator"] = creators
    if top.get("Publishers"):
        md["publisher"] = unique(top["Publishers"])
    if top.get("ReleaseDate"):
        md["date"] = top["ReleaseDate"][:10]
    if top.get("Languages"):
        md["language"] = unique(top["Languages"])
    subjects = (top.get("Keywords") or []) + (top.get("Categories") or []) + (top.get("Subcategories") or []) \
        + [s if isinstance(s, str) else s.get("Name", "") for s in top.get("Systems") or []] \
        + [o.get("Name", "") for o in top.get("RequiredOperatingSystems") or [] if isinstance(o, dict)]
    if unique(s for s in subjects if s):
        md["subject"] = unique(s for s in subjects if s)
    for key, field in (("Version", "version"), ("Release", "release_type"), ("PartNumber", "partnumber"),
                       ("SerialNumber", "serial_number")):
        if top.get(key):
            md[field] = str(top[key])
    barcodes = [b for b in top.get("Barcodes") or [] if b.get("Value")]
    isbns = [b["Value"] for b in barcodes if b.get("Type") == "ISBN"]
    others = [f"{b.get('Type')}:{b['Value']}" for b in barcodes if b.get("Type") != "ISBN"]
    if isbns:
        md["isbn"] = isbns
    if others:
        md["barcode"] = others

    discs = [m for key, m in media]
    if discs and all("audio" in (m.get("DiscSubType") or "").lower() for m in discs):
        md["mediatype"], md["collection"] = "audio", "opensource_audio"
    elif any(part.lower().startswith("movies") for part in folder.resolve().parts):
        md["mediatype"], md["collection"] = "movies", "opensource_movies"
    else:
        md["mediatype"], md["collection"] = "software", "open_source_software"

    intro = []
    for label, field in (("Version", "version"), ("Release", "release_type"), ("Part number", "partnumber"),
                         ("Serial number", "serial_number")):
        if md.get(field):
            intro.append(f"{label}: {md[field]}")
    for b in barcodes:
        intro.append(f"{b.get('Type') or 'Barcode'}: {b['Value']}")
    paragraphs = ["<br />".join(intro)] if intro else []
    # Separate sidecars all say disc 1 of 1, then they are numbered in order
    sequences = [(m.get("Sequence") or {}).get("MediaSequence", 0) for m in discs]
    if len(set(sequences)) == len(discs):
        discs = [m for _, m in sorted(zip(sequences, discs), key=lambda x: x[0])]
    paragraphs += [disc_description(m, i, len(discs)) for i, m in enumerate(discs, 1)]
    md["description"] = "<p>" + "</p><p>".join(paragraphs) + "</p>"
    md["scanner"] = "ia_upload.py"
    return md


def show_metadata(identifier, md, files):
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(overflow="fold")
    table.add_row("identifier", identifier)
    for key, value in md.items():
        table.add_row(key, "; ".join(value) if isinstance(value, list) else str(value))
    total = sum(p.stat().st_size for p in files)
    table.add_row("files", f"{len(files)} ({human_size(total)}): " + ", ".join(p.name for p in files))
    console.print(table)


def review(identifier, md, files):
    """Let the identifier and metadata be edited. Returns (identifier, metadata), or None to skip the folder."""
    while True:
        show_metadata(identifier, md, files)
        answer = ask("Upload? [y]es / [e]dit a field / [s]kip folder / [q]uit: ").lower()
        if answer.startswith("y"):
            return identifier, md
        if answer.startswith("s"):
            return None
        if answer.startswith("q"):
            raise Quit
        if answer.startswith("e"):
            field = ask("Field (identifier or metadata name, new ones allowed): ").strip().lower()
            if not field:
                continue
            if field == "identifier":
                new = make_identifier(ask("identifier: ", identifier))
                if new and item_owner(new) is not None:
                    console.print(f"[red]✖ {new} is already used[/red]")
                elif new:
                    identifier = new
                continue
            current = md.get(field, "")
            value = ask(f"{field} (; separates several values, empty removes it): ",
                        "; ".join(current) if isinstance(current, list) else current)
            values = [v.strip() for v in value.split(";") if v.strip()] if field != "description" else [value]
            if not value:
                md.pop(field, None)
            else:
                md[field] = values if len(values) > 1 or isinstance(current, list) else values[0]


# ---------------------------------------------------------------- Upload


def header_value(value):
    value = str(value)
    if value.isascii() and value.isprintable():
        return value
    return f"uri({urllib.parse.quote(value, safe='')})"


def meta_headers(md, size_hint):
    headers = {"x-archive-auto-make-bucket": "1", "x-archive-size-hint": str(size_hint)}
    for key, value in md.items():
        name = key.replace("_", "--")
        values = value if isinstance(value, list) else [value]
        if len(values) == 1:
            headers[f"x-archive-meta-{name}"] = header_value(values[0])
        else:
            for i, v in enumerate(values):
                headers[f"x-archive-meta{i:02d}-{name}"] = header_value(v)
    return headers


def as_list(value):
    values = value if isinstance(value, list) else [value]
    return [str(v).strip() for v in values if str(v).strip()]


def metadata_changes(identifier, md):
    """JSON Patch turning the metadata of the item into md, for the fields md has. The collection is left
    alone: moving an item to another collection needs its curators."""
    remote = (get_json(f"{ARCHIVE}/metadata/{identifier}").get("metadata") or {})
    patch = []
    for key, value in md.items():
        if key == "collection" or as_list(remote.get(key, [])) == as_list(value):
            continue
        path = "/" + key.replace("~", "~0").replace("/", "~1")
        patch.append({"op": "replace" if key in remote else "add", "path": path, "value": value})
    return patch


def update_metadata(identifier, keys, md, dry_run):
    """Bring the metadata of an existing item up to date with md."""
    patch = metadata_changes(identifier, md)
    if not patch:
        console.print("[green]✔[/green] the metadata is up to date")
        return
    fields = ", ".join(op["path"][1:] for op in patch)
    if dry_run:
        console.print(f"[dim]dry run: would update the metadata: {fields}[/dim]")
        return
    data = urllib.parse.urlencode({"-target": "metadata", "-patch": json.dumps(patch)}).encode()
    headers = dict(auth_header(keys))
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    _, _, body = request("POST", f"{ARCHIVE}/metadata/{identifier}", headers, data, ok=(200, 400))
    try:
        reply = json.loads(body or b"{}")
    except ValueError:
        reply = {}
    if not reply.get("success"):
        raise IAError(f"cannot update the metadata: {reply.get('error') or body[:200].decode(errors='replace')}")
    console.print(f"[green]✔[/green] updated the metadata: {fields}")


def file_md5(path, entry):
    stat = path.stat()
    if entry.get("md5") and entry.get("md5_of") == [stat.st_size, stat.st_mtime_ns]:
        return entry["md5"]
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(16 * 1024 * 1024):
            h.update(chunk)
    entry["md5"], entry["md5_of"] = h.hexdigest(), [stat.st_size, stat.st_mtime_ns]
    return entry["md5"]


class Uploader:
    def __init__(self, identifier, keys, md, part_size, derive, progress, jobs):
        self.identifier = identifier
        self.jobs = jobs
        # At most jobs requests sending data at once, whether parts of one file or several files
        self.slots = threading.BoundedSemaphore(jobs)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.auth = auth_header(keys)
        self.access = keys["access"]
        self.md = md
        self.part_size = part_size
        self.derive = derive
        self.progress = progress
        self.state_path = STATE_DIR / f"{identifier}.json"
        try:
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("files", {})

    def save(self):
        with self.lock:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_name(self.state_path.name + ".tmp")
            tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)

    def url(self, path, query=""):
        return f"{S3}/{self.identifier}/{urllib.parse.quote(path.name, safe='')}{query}"

    def entry(self, path):
        """State of a file, started again if the file changed since."""
        stat = path.stat()
        with self.lock:
            entry = self.state["files"].get(path.name)
            if not entry or entry.get("size") != stat.st_size or entry.get("mtime") != stat.st_mtime_ns:
                entry = {"size": stat.st_size, "mtime": stat.st_mtime_ns}
                self.state["files"][path.name] = entry
            return entry

    def wait_for_slot(self):
        """Wait while archive.org asks uploaders to slow down."""
        while True:
            try:
                info = get_json(f"{S3}/?check_limit=1&accesskey={urllib.parse.quote(self.access)}"
                                f"&bucket={self.identifier}")
            except (IAError, ValueError):
                return
            if not info.get("over_limit"):
                return
            console.print("[yellow]⚠ archive.org is over its upload limit, waiting 60 s[/yellow]")
            time.sleep(60)

    def pending(self, files, remote):
        """Files still to upload, skipping those already done or already on the item."""
        todo = []
        for path in files:
            entry = self.entry(path)
            if entry.get("done"):
                continue
            # archive.org renames an uploaded __ia_thumb.jpg to ___ia_thumb.jpg and makes its own from it
            names = (path.name, "_" + path.name) if path.name == THUMBNAIL else (path.name,)
            if any(int(remote[name].get("size", -1)) == entry["size"] and remote[name].get("md5") == file_md5(path, entry)
                   for name in names if name in remote):
                entry["done"] = True
                continue
            todo.append(path)
        self.save()
        return todo

    def headers(self, path, last, size_hint):
        headers = dict(self.auth)
        headers.update(meta_headers(self.md, size_hint))
        headers["x-archive-queue-derive"] = "1" if self.derive and last else "0"
        return headers

    def upload_all(self, todo, size_hint, overall):
        """Upload the files, the first one alone (it creates the item) and the last one (it starts the
        derive) once all the others are there; the rest, and the parts of big files, jobs at a time."""
        def one(path, last=False):
            return lambda: (self.upload(path, last, size_hint, overall),
                            self.progress.console.print(f"[green]✔[/green] {path.name}"))

        if todo:
            one(todo[0], len(todo) == 1)()
        run_parallel(self.jobs, [one(path) for path in todo[1:-1]], self.stop)
        if len(todo) > 1:
            one(todo[-1], True)()

    def upload(self, path, last, size_hint, overall):
        entry = self.entry(path)
        task = self.progress.add_task(path.name, total=entry["size"])

        def sent(n):
            self.progress.advance(task, n)
            self.progress.advance(overall, n)

        self.wait_for_slot()
        try:
            if entry["size"] <= self.part_size:
                self.single(path, entry, self.headers(path, last, size_hint), sent)
            else:
                self.multipart(path, entry, self.headers(path, last, size_hint), sent)
        finally:
            self.progress.remove_task(task)
        with self.lock:
            entry["done"] = True
            entry.pop("upload_id", None)
            entry.pop("parts", None)
            self.save()

    def single(self, path, entry, headers, sent):
        with self.slots:
            if self.stop.is_set():
                raise IAError("stopped")
            data = path.read_bytes()
            headers["Content-MD5"] = base64.b64encode(hashlib.md5(data).digest()).decode()
            request("PUT", self.url(path), headers, data, sent)

    def multipart(self, path, entry, headers, sent):
        part_size = max(self.part_size, -(-entry["size"] // MAX_PARTS))
        if entry.get("upload_id") and entry.get("part_size") != part_size:
            self.abort(path, entry)
        if entry.get("upload_id"):
            parts = self.uploaded_parts(path, entry)
            if parts is None:
                console.print(f"[yellow]⚠ the interrupted upload of {path.name} expired, starting again[/yellow]")
                self.abort(path, entry)
            else:
                entry["parts"] = parts
        if not entry.get("upload_id"):
            _, _, body = request("POST", self.url(path, "?uploads"), headers)
            entry["upload_id"] = xml_text(body, "UploadId")
            entry["part_size"] = part_size
            entry["parts"] = {}
            self.save()
        parts = entry["parts"]
        count = -(-entry["size"] // part_size)
        query = urllib.parse.quote(entry["upload_id"], safe="")

        def send(number, length):
            with self.slots:
                if self.stop.is_set():
                    raise IAError("stopped")
                with open(path, "rb") as f:
                    f.seek((number - 1) * part_size)
                    data = f.read(length)
                digest = hashlib.md5(data).digest()
                part_headers = dict(self.auth)
                part_headers["Content-MD5"] = base64.b64encode(digest).decode()
                _, reply, _ = request("PUT", self.url(path, f"?partNumber={number}&uploadId={query}"),
                                      part_headers, data, sent)
                del data
            with self.lock:
                parts[str(number)] = reply.get("ETag") or f'"{digest.hex()}"'
                self.save()

        tasks = []
        for number in range(1, count + 1):
            length = min(part_size, entry["size"] - (number - 1) * part_size)
            if str(number) in parts:
                sent(length)
            else:
                tasks.append(lambda number=number, length=length: send(number, length))
        run_parallel(self.jobs, tasks, self.stop)
        xml = "<CompleteMultipartUpload>" + "".join(
            f"<Part><PartNumber>{n}</PartNumber><ETag>{parts[str(n)]}</ETag></Part>"
            for n in range(1, count + 1)) + "</CompleteMultipartUpload>"
        complete = {k: v for k, v in headers.items() if k.lower().startswith(("authorization", "x-archive-queue"))}
        complete["Content-Type"] = "application/xml"
        request("POST", self.url(path, f"?uploadId={query}"), complete, xml.encode())

    def uploaded_parts(self, path, entry):
        """Parts archive.org has of the interrupted upload, None if it no longer exists. When the parts cannot
        be listed, the ones recorded are trusted."""
        parts, marker = {}, 0
        query = urllib.parse.quote(entry["upload_id"], safe="")
        while True:
            try:
                status, _, body = request("GET", self.url(path, f"?uploadId={query}&part-number-marker={marker}"),
                                          self.auth, ok=(200, 404))
            except IAError as e:
                console.print(f"[yellow]⚠ cannot list the parts already sent ({e}), using the recorded ones[/yellow]")
                return entry.get("parts", {})
            if status == 404:
                return None
            root = ET.fromstring(body)
            for part in root.findall(".//{*}Part"):
                parts[part.findtext("{*}PartNumber")] = part.findtext("{*}ETag")
            if root.findtext("{*}IsTruncated") != "true":
                return parts
            marker = root.findtext("{*}NextPartNumberMarker")

    def abort(self, path, entry):
        if entry.get("upload_id"):
            try:
                request("DELETE", self.url(path, f"?uploadId={urllib.parse.quote(entry['upload_id'], safe='')}"),
                        self.auth, ok=(200, 204, 404))
            except IAError:
                pass
        for key in ("upload_id", "parts", "part_size"):
            entry.pop(key, None)


def xml_text(body, tag):
    value = ET.fromstring(body).findtext(f"{{*}}{tag}")
    if not value:
        raise IAError(f"archive.org did not return {tag}")
    return value


def remote_files(identifier):
    try:
        files = get_json(f"{ARCHIVE}/metadata/{identifier}/files").get("result") or []
    except (IAError, ValueError):
        return {}
    return {f["name"]: f for f in files if f.get("source") == "original"}


# ---------------------------------------------------------------- Main


def process(folder, args, keys):
    console.rule(f"[bold]{folder.resolve().name}")
    make_covers(folder, args.dry_run)
    files = folder_files(folder)
    if not files:
        console.print("[yellow]⚠ nothing to upload[/yellow]")
        return True
    top, media = aaru_metadata(folder)
    if not media:
        console.print("[yellow]⚠ no Aaru metadata found, only the folder name is used[/yellow]")
    md = convert_metadata(folder, top, media)
    if args.test:
        md["collection"] = "test_collection"
    if args.collection:
        md["collection"] = args.collection
    if args.mediatype:
        md["mediatype"] = args.mediatype

    identifier, exists = choose_identifier(folder, args.identifier, keys, args.yes)
    if args.dry_run:
        show_metadata(identifier, md, files)
        console.print(f"[dim]dry run: would upload to {ARCHIVE}/details/{identifier}"
                      f"{' (existing item)' if exists else ''}[/dim]")
        if exists:
            update_metadata(identifier, keys, md, True)
        return True
    if not args.yes:
        reviewed = review(identifier, md, files)
        if reviewed is None:
            return True
        if reviewed[0] != identifier:
            identifier, exists = reviewed[0], False
        md = reviewed[1]

    columns = (TextColumn("{task.description}", markup=False), BarColumn(), DownloadColumn(),
               TransferSpeedColumn(), TimeRemainingColumn())
    with Progress(*columns, console=console) as progress:
        uploader = Uploader(identifier, keys, md, args.part_size * 1024 * 1024, not args.no_derive, progress,
                            args.jobs)
        todo = uploader.pending(files, remote_files(identifier) if exists else {})
        if not todo:
            console.print("[green]✔[/green] everything is already uploaded")
        total = sum(p.stat().st_size for p in todo)
        size_hint = sum(p.stat().st_size for p in files)
        overall = progress.add_task("total", total=total, visible=bool(todo))
        try:
            uploader.upload_all(todo, size_hint, overall)
        except KeyboardInterrupt:
            uploader.stop.set()
            uploader.save()
            raise
    if exists:
        # The metadata sent with the files only counts when they create the item
        update_metadata(identifier, keys, md, False)
    console.print(f"[green]✔[/green] {ARCHIVE}/details/{identifier}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folders", nargs="*", type=Path, help="folders to upload (default: the current one)")
    parser.add_argument("--login", action="store_true", help="log in again, replacing the stored keys")
    parser.add_argument("--logout", action="store_true", help="remove the stored keys")
    parser.add_argument("-i", "--identifier", help="item identifier (only with a single folder)")
    parser.add_argument("-c", "--collection", help="collection, instead of the one chosen by disc type")
    parser.add_argument("-m", "--mediatype", help="mediatype, instead of the one chosen by disc type")
    parser.add_argument("--test", action="store_true", help="upload to test_collection (removed after 30 days)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show what would be uploaded, upload nothing")
    parser.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--part-size", type=int, default=100, metavar="MiB",
                        help="files bigger than this are sent in parts of this size (default 100)")
    parser.add_argument("-j", "--jobs", type=int, default=4, metavar="N",
                        help="files or parts of a file sent at once, each over its own connection (default 4)")
    parser.add_argument("--no-derive", action="store_true", help="do not let archive.org derive the item")
    args = parser.parse_args()

    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if args.part_size < 5:
        parser.error("--part-size must be at least 5 MiB")
    if args.identifier and len(args.folders) > 1:
        parser.error("--identifier can only be used with a single folder")
    if args.logout:
        CREDENTIALS.unlink(missing_ok=True)
        console.print(f"[green]✔[/green] Removed {CREDENTIALS}")
    folders = args.folders or ([] if args.login or args.logout else [Path(".")])
    for folder in folders:
        if not folder.is_dir():
            parser.error(f"{folder} is not a folder")

    try:
        keys = None
        if args.login or not args.dry_run and folders:
            keys = credentials(force=args.login)
        elif CREDENTIALS.exists():
            keys = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
        failed = 0
        for folder in folders:
            try:
                process(folder, args, keys)
            except IAError as e:
                failed += 1
                console.print(f"[bold red]✖[/bold red] {folder}: {e}", style="red")
    except (Quit, KeyboardInterrupt):
        console.print("\n[yellow]Stopped. Run the script again to continue the upload where it was.[/yellow]")
        sys.exit(130)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
