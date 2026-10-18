#!/usr/bin/python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["rich"]
# ///
"""Fill in the Aaru metadata.json of game folders with information from IGDB, interactively.

The folder name, without anything in parentheses or brackets, is searched in IGDB. When there is a
single game with that name for the platform of the folder (taken from the path: PC, Nintendo Wii,
Sony PlayStation 2...), it is picked; when several games share the name, they are listed with their
year, type, companies and platforms to choose from, and can be narrowed by year ("y 1998") or by
company ("c bioware"). When nothing matches exactly, the closest results are listed.

From the chosen game, the developers, publishers, name, release date (for the folder platform,
preferring the --region release), franchises and collections (as keywords), genres (as
subcategories), languages and, for PC, the required operating system are proposed. Fields already
in the metadata (languages, part numbers, barcodes, optical discs...) are kept: IGDB only fills the
empty ones. Every field, current and proposed, is shown for confirmation and any of them can be
switched to the current value, the IGDB value, both merged, another IGDB choice (localized names,
other release dates), edited by hand or cleared before writing.

The metadata used is metadata.json in the folder, otherwise each *.metadata.json sidecar in it,
otherwise a new metadata.json is created. A backup (<file>.bak) is written before a file is modified
for the first time.

The IGDB (Twitch) credentials are read from the IGDB_CLIENT_ID and IGDB_CLIENT_SECRET environment
variables or, when not set, from igdb_key.json next to this script:
  {"Igdb": {"ClientId": "...", "ClientSecret": "..."}}
The access token is cached in ~/.cache/igdb_metadata/token.json.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import readline
except ImportError:
    readline = None

try:
    from rich import box
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("This script needs the 'rich' Python module: run it with /usr/bin/python3, install python-rich, "
             "or use 'uv run igdb_metadata.py'.")

SCRIPT_DIR = Path(__file__).resolve().parent
KEY_FILE = SCRIPT_DIR / "igdb_key.json"
TOKEN_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "igdb_metadata" / "token.json"
API = "https://api.igdb.com/v4/"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"

console = Console(highlight=False)

# Order of the fields in the Aaru Metadata class, which is also the order Aaru writes them in
KEY_ORDER = ("Developers", "Publishers", "Authors", "Performers", "Name", "Version", "Release", "ReleaseDate",
             "Barcodes", "PartNumber", "SerialNumber", "Keywords", "Magazines", "Books", "Categories",
             "Subcategories", "Languages", "Systems", "Architectures", "RequiredOperatingSystems", "UserManuals",
             "OpticalDiscs", "Advertisements", "LinearMedias", "PciCards", "BlockMedias", "AudioMedias")
MEDIA_KEYS = ("OpticalDiscs", "BlockMedias", "LinearMedias", "AudioMedias")

RELEASE_TYPES = ("Retail", "Bundle", "Coverdisc", "Subscription", "Demo", "OEM", "Shareware", "FOSS", "Adware",
                 "Donationware", "DigitalDownload", "SaaS")
DEFAULT_CATEGORIES = ["Videogame"]
# Aaru.CommonTypes/AaruMetadata/Barcode.cs
BARCODE_TYPES = ("Aztec", "Codabar", "Code11", "Code128", "Code39", "Code93", "CPC_Binary", "EZcode", "FIM", "ITF",
                 "ITF14", "EAN13", "EAN8", "MaxiCode", "ISBN", "ISRC", "MSI", "ShotCode", "RM4SCC", "QR", "EAN5", "EAN2",
                 "POSTNET", "PostBar", "Plessey", "Pharmacode", "PDF417", "PatchCode")

# Folder names (anywhere in the path, the deepest one wins) to the IGDB platform names they stand for
PLATFORMS = {
    "PC": ("PC (Microsoft Windows)", "DOS"),
    "Linux": ("Linux",),
    "Macintosh": ("Mac",),
    "Nintendo Wii": ("Wii",),
    "Nintendo Wii U": ("Wii U",),
    "Nintendo GameCube": ("Nintendo GameCube",),
    "Microsoft Xbox": ("Xbox",),
    "Microsoft Xbox 360": ("Xbox 360",),
    "Microsoft Xbox One": ("Xbox One",),
    "Microsoft Xbox Series": ("Xbox Series X|S",),
    "Sony PlayStation": ("PlayStation",),
    "Sony PlayStation 2": ("PlayStation 2",),
    "Sony PlayStation 3": ("PlayStation 3",),
    "Sony PlayStation 4": ("PlayStation 4",),
    "Sega Saturn": ("Sega Saturn",),
    "Sega Mega CD": ("Sega CD",),
    "Sega Dreamcast": ("Dreamcast",),
    "3DO": ("3DO Interactive Multiplayer",),
    "Atari Jaguar CD": ("Atari Jaguar CD", "Atari Jaguar"),
    "NEC PC Engine CD": ("Turbografx-16/PC Engine CD", "TurboGrafx-16/PC Engine"),
    "NEC PC-FX": ("PC-FX",),
    "Fujitsu FM-Towns": ("FM Towns",),
    "Philips CD-i": ("Philips CD-i",),
    "SNK Neo Geo CD": ("Neo Geo CD",),
    "Acorn": ("Acorn Archimedes",),
}
# IGDB platforms that are a required operating system for the Aaru metadata
PLATFORM_OS = {"PC (Microsoft Windows)": "Windows", "DOS": "DOS", "Linux": "Linux"}

REGIONS = ("europe", "north_america", "australia", "new_zealand", "japan", "china", "asia", "worldwide", "korea",
           "brazil")
# Old IGDB release date "region" enum, used when "release_region" is missing
OLD_REGIONS = {i + 1: name for i, name in enumerate(REGIONS)}

# ISO 639-1 (IGDB locales) to the ISO 639-2/B codes Aaru uses
ISO639_1 = {
    "ar": "ara", "bg": "bul", "ca": "cat", "cs": "cze", "cy": "wel", "da": "dan", "de": "ger", "el": "gre",
    "en": "eng", "es": "spa", "et": "est", "eu": "baq", "fa": "per", "fi": "fin", "fil": "fil", "fr": "fre",
    "ga": "gle", "gl": "glg", "he": "heb", "hi": "hin", "hr": "hrv", "hu": "hun", "id": "ind", "is": "ice",
    "it": "ita", "ja": "jpn", "ko": "kor", "lt": "lit", "lv": "lav", "ms": "may", "nb": "nob", "nl": "dut",
    "no": "nor", "pl": "pol", "pt": "por", "ro": "rum", "ru": "rus", "sk": "slo", "sl": "slv", "sr": "srp",
    "sv": "swe", "th": "tha", "tl": "tgl", "tr": "tur", "uk": "ukr", "vi": "vie", "zh": "chi",
}
# Every language code Aaru knows (Aaru.CommonTypes/AaruMetadata/Language.cs)
AARU_LANGUAGES = set("""
aar abk ace ach ada ady afa afh afr ain aka akk alb ale alg alt amh ang anp apa ara arc arg arm arn arp art arw asm
ast ath aus ava ave awa aym aze bad bai bak bal bam ban baq bas bat bej bel bem ben ber bho bih bik bin bis bla bnt
bos bra bre btk bua bug bul bur byn cad cai car cat cau ceb cel cha chb che chg chi chk chm chn cho chp chr chu chv
chy cmc cop cor cos cpe cpf cpp cre crh crp csb cus cze dak dan dar day del den dgr din div doi dra dsb dua dum dut
dyu dzo efi egy eka elx eng enm epo est ewe ewo fan fao fat fij fil fin fiu fon fre frm fro frr frs fry ful fur gaa
gay gba gem geo ger gez gil gla gle glg glv gmh goh gon gor got grb grc gre grn gsw guj gwi hai hat hau haw heb her
hil him hin hit hmn hmo hrv hsb hun hup iba ibo ice ido iii ijo iku ile ilo ina inc ind ine inh ipk ira iro ita jav
jbo jpn jpr jrb kaa kab kac kal kam kan kar kas kau kaw kaz kbd kha khi khm kho kik kin kir kmb kok kom kon kor kos
kpe krc krl kro kru kua kum kur kut lad lah lam lao lat lav lez lim lin lit lol loz ltz lua lub lug lui lun luo lus
mac mad mag mah mai mak mal man mao map mar mas may mdf mdr men mga mic min mis mkh mlg mlt mnc mni mno moh mon mos
mul mun mus mwl mwr myn myv nah nai nap nau nav nbl nde ndo nds nep nia nic niu nno nob nog non nor nqo nso nub nwc
nya nym nyn nyo nzi oci oji ori orm osa oss ota oto paa pag pal pam pan pap pau peo per phi phn pli pol pon por pra
pro pus que raj rap rar roa roh rom rum run rup rus sad sag sah sai sal sam san sas sat scn sco sel sem sga sgn shn
sid sin sio sit sla slo slv sma sme smi smj smn smo sms sna snd snk sog som son sot spa srd srn srp srr ssa ssw suk
sun sus sux swa swe syc syr tah tai tam tat tel tem ter tet tgk tgl tha tib tig tir tiv tkl tlh tli tmh tog ton tpi
tsi tsn tso tuk tum tup tur tut tvl twi tyv udm uga uig ukr umb und urd uzb vai ven vie vol vot wak wal war was wel
wen wln wol xal xho yao yap yid yor ypk zap zbl zen zgh zha znd zul zun zxx zza
""".split())

# IGDB genres to the subcategory names used in the existing metadata; others lose their "(ABBR)" suffix
GENRES = {
    "Real Time Strategy (RTS)": "Real time strategy",
    "Turn-based strategy (TBS)": "Turn-based strategy",
    "Role-playing (RPG)": "Role-playing game",
    "Hack and slash/Beat 'em up": "Hack and slash",
    "Simulator": "Simulation",
    "Sport": "Sports",
    "Card & Board Game": "Card and board game",
    "Quiz/Trivia": "Quiz",
    "Point-and-click": "Point-and-click adventure",
    "Indie": None,
}

GAME_FIELDS = ("name", "slug", "url", "first_release_date", "game_type.type", "platforms.name", "version_title",
               "version_parent.name", "parent_game.name", "alternative_names.name", "alternative_names.comment",
               "involved_companies.company.name", "involved_companies.developer", "involved_companies.publisher")
DETAIL_FIELDS = GAME_FIELDS + (
    "summary", "game_localizations.name", "game_localizations.region.name", "franchise.name", "franchises.name",
    "collections.name", "genres.name", "themes.name", "player_perspectives.name", "game_modes.name",
    "release_dates.date", "release_dates.date_format", "release_dates.human", "release_dates.platform.name",
    "release_dates.region", "release_dates.release_region.region", "language_supports.language.locale",
    "language_supports.language.name", "language_supports.language_support_type.name")
# Types that are rarely what a dump is, listed after the others
MINOR_TYPES = ("Mod", "Update", "Fork", "Season", "Episode", "Pack", "DLC")


class Quit(Exception):
    pass


# ---------------------------------------------------------------- IGDB

def load_credentials():
    client_id = os.environ.get("IGDB_CLIENT_ID")
    client_secret = os.environ.get("IGDB_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret
    if not KEY_FILE.exists():
        fail(f"No IGDB credentials: set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET or create {KEY_FILE}")
    try:
        # Tolerate trailing commas, an easy mistake when editing the file by hand
        data = json.loads(re.sub(r",\s*([}\]])", r"\1", KEY_FILE.read_text(encoding="utf-8")))
        data = data.get("Igdb", data)
        client_id = data.get("ClientId") or data.get("client_id")
        client_secret = data.get("ClientSecret") or data.get("client_secret")
    except (ValueError, AttributeError) as e:
        fail(f"{KEY_FILE}: cannot be read ({e})")
    if not client_id or not client_secret:
        fail(f"{KEY_FILE}: needs Igdb.ClientId and Igdb.ClientSecret")
    return client_id, client_secret


class Igdb:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.last_call = 0.0

    def get_token(self, refresh=False):
        if not refresh:
            try:
                cached = json.loads(TOKEN_CACHE.read_text())
                if cached["client_id"] == self.client_id and cached["expires_at"] > time.time() + 60:
                    return cached["access_token"]
            except (OSError, ValueError, KeyError):
                pass
        query = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self.client_secret,
                                        "grant_type": "client_credentials"})
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{TOKEN_URL}?{query}", method="POST"),
                                        timeout=30) as r:
                answer = json.load(r)
        except urllib.error.HTTPError as e:
            fail(f"IGDB authentication failed: HTTP {e.code} {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            fail(f"Cannot reach Twitch to authenticate: {e.reason}")
        TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE.write_text(json.dumps({"client_id": self.client_id, "access_token": answer["access_token"],
                                           "expires_at": time.time() + answer["expires_in"]}))
        TOKEN_CACHE.chmod(0o600)
        return answer["access_token"]

    def query(self, endpoint, body):
        if self.token is None:
            self.token = self.get_token()
        for attempt in range(4):
            wait = self.last_call + 0.26 - time.monotonic()  # IGDB allows 4 requests per second
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.monotonic()
            request = urllib.request.Request(API + endpoint, data=body.encode(), method="POST",
                                             headers={"Client-ID": self.client_id,
                                                      "Authorization": f"Bearer {self.token}",
                                                      "Accept": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=30) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    self.token = self.get_token(refresh=True)
                elif e.code == 429:
                    time.sleep(1 + attempt)
                else:
                    raise RuntimeError(f"IGDB {endpoint}: HTTP {e.code} {e.read().decode(errors='replace')}")
            except urllib.error.URLError as e:
                raise RuntimeError(f"Cannot reach IGDB: {e.reason}")
        raise RuntimeError(f"IGDB {endpoint}: too many retries")

    def games(self, condition, fields=GAME_FIELDS, limit=50):
        return self.query("games", f"fields {','.join(fields)}; {condition} limit {limit};")

    def search(self, term):
        quoted = apicalypse_string(term)
        found = {g["id"]: g for g in self.games(f"search {quoted};")}
        # The search ranks poorly and can miss an exact title, so ask for those too
        for game in self.games(f"where name ~ {quoted} | alternative_names.name ~ {quoted};"):
            found.setdefault(game["id"], game)
        return list(found.values())

    def details(self, game_id):
        games = self.games(f"where id = {int(game_id)};", DETAIL_FIELDS, 1)
        return games[0] if games else None

    def lookup(self, reference):
        """A game by IGDB id or URL/slug."""
        reference = reference.strip().rstrip("/")
        if reference.isdigit():
            return self.games(f"where id = {reference};")
        slug = reference.rsplit("/", 1)[-1]
        return self.games(f"where slug = {apicalypse_string(slug)};")


def find(igdb, term, platforms):
    """Search IGDB, dropping words from the end of the name until something is found (IGDB finds nothing for
    "Act of War High Treason Expansion Pack"). Returns the ranked games and the name that found them."""
    words = term.split()
    while True:
        searched = " ".join(words)
        with console.status(f"Searching IGDB for “{searched}”…"):
            games = igdb.search(searched)
        if games or len(words) <= 1:
            return rank(games, term, platforms), searched
        words.pop()


def apicalypse_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------------------------------------------------------- Game data helpers

def normalize(name):
    name = name.lower().replace("&", " and ")
    name = re.sub(r"[^\w\s]", " ", name)
    return " ".join(name.split())


def search_name(folder_name):
    return " ".join(re.sub(r"[(\[][^)\]]*[)\]]", " ", folder_name).split())


def folder_year(folder_name):
    for group in re.findall(r"[(\[]([^)\]]*)[)\]]", folder_name):
        if re.fullmatch(r"(19[7-9]\d|20[0-4]\d)", group.strip()):
            return int(group)
    return None


def platform_hint(folder):
    hint = None
    for part in folder.resolve().parts:
        hint = PLATFORMS.get(part, hint)
    return hint


def year_of(game):
    stamp = game.get("first_release_date")
    return datetime.fromtimestamp(stamp, timezone.utc).year if stamp else None


def game_type(game):
    return (game.get("game_type") or {}).get("type") or ""


def platform_names(game):
    return [p["name"] for p in game.get("platforms") or [] if "name" in p]


def companies(game, role):
    return unique(c["company"]["name"] for c in game.get("involved_companies") or []
                  if c.get(role) and "name" in c.get("company", {}))


def all_names(game):
    return [game.get("name", "")] + [a["name"] for a in game.get("alternative_names") or [] if "name" in a]


def unique(items):
    seen, result = set(), []
    for item in items:
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result


def on_platform(game, platforms):
    return bool(platforms) and any(p in platforms for p in platform_names(game))


def rank(games, term, platforms):
    wanted = normalize(term)

    def key(game):
        exact = any(normalize(n) == wanted for n in all_names(game))
        ratio = max(difflib.SequenceMatcher(None, wanted, normalize(n)).ratio() for n in all_names(game))
        return (not exact, not on_platform(game, platforms), game_type(game) in MINOR_TYPES, -ratio,
                year_of(game) or 9999)

    return sorted(games, key=key)


def is_exact(game, term):
    return any(normalize(n) == normalize(term) for n in all_names(game))


def filter_games(games, year=None, company=None, platforms=None):
    if year:
        low, high = year
        games = [g for g in games if year_of(g) and low <= year_of(g) <= high]
    if company:
        needle = company.casefold()
        games = [g for g in games if any(needle in c["company"].get("name", "").casefold()
                                         for c in g.get("involved_companies") or [] if "company" in c)]
    if platforms:
        games = [g for g in games if on_platform(g, platforms)]
    return games


def release_dates(game, platforms):
    """Release dates on the folder platform (all of them if there are none), best guess first."""
    dates = []
    for r in game.get("release_dates") or []:
        if "date" not in r or r.get("date_format", 0) > 2:  # quarters and TBD are not a date
            continue
        region = (r.get("release_region") or {}).get("region") or OLD_REGIONS.get(r.get("region"), "")
        dates.append({"date": datetime.fromtimestamp(r["date"], timezone.utc), "precise": r.get("date_format", 0) == 0,
                      "human": r.get("human", ""), "platform": (r.get("platform") or {}).get("name", ""),
                      "region": region})
    matching = [d for d in dates if platforms and d["platform"] in platforms]
    return matching or dates


def best_date(dates, region):
    def key(d):
        preference = (region, "worldwide")
        return (d["region"] not in preference, preference.index(d["region"]) if d["region"] in preference else 0,
                not d["precise"], d["date"])

    return sorted(dates, key=key)[0] if dates else None


def subcategories(game):
    genres = [g["name"] for g in game.get("genres") or [] if "name" in g]
    perspectives = {p.get("name") for p in game.get("player_perspectives") or []}
    modes = {m.get("name") for m in game.get("game_modes") or []}
    result = []
    for genre in genres:
        if genre == "Shooter" and "First person" in perspectives:
            name = "First person shooter"
        elif genre == "Role-playing (RPG)" and "Massively Multiplayer Online (MMO)" in modes:
            name = "MMORPG"
        elif genre in GENRES:
            name = GENRES[genre]
        else:
            name = re.sub(r"\s*\([^)]*\)", "", genre)
        if name:
            result.append(name)
    if any("strategy" in s.lower() and s != "Strategy" for s in result):
        result = [s for s in result if s != "Strategy"]
    return unique(result)


def languages(game):
    codes = []
    for support in game.get("language_supports") or []:
        locale = (support.get("language") or {}).get("locale", "")
        code = ISO639_1.get(locale.split("-")[0].lower())
        if code:
            codes.append(code)
    return unique(codes)


def operating_systems(game, platforms):
    """The one operating system the game most likely came on, for computer platforms."""
    systems = [p for p in platform_names(game) if p in PLATFORM_OS and platforms and p in platforms]
    if not systems:
        return None
    if len(systems) > 1:
        # DOS games were often rereleased for Windows: the platform released first is the original one
        first = {}
        for r in game.get("release_dates") or []:
            name = (r.get("platform") or {}).get("name")
            if name in systems and "date" in r:
                first[name] = min(first.get(name, r["date"]), r["date"])
        systems.sort(key=lambda p: first.get(p, float("inf")))
    return [{"Name": PLATFORM_OS[systems[0]]}]


def keywords(game):
    names = [game["franchise"].get("name")] if game.get("franchise") else []
    names += [f.get("name") for f in game.get("franchises") or []]
    names += [c.get("name") for c in game.get("collections") or []]
    return unique(names)


# ---------------------------------------------------------------- Fields

class Field:
    """One metadata field: what the file has, what IGDB proposes and what will be written."""

    def __init__(self, key, label, kind, current, igdb=None, default=None, choices=None, editable=True):
        self.key, self.label, self.kind = key, label, kind
        self.current = current if current not in ("", [], {}) else None
        self.igdb = igdb if igdb not in ("", [], {}) else None
        self.choices = choices or []  # (description, value) alternatives from IGDB
        self.editable = editable
        if self.current is not None:
            self.set(self.current, "kept")
        elif self.igdb is not None:
            self.set(self.igdb, "igdb")
        elif default is not None:
            self.set(default, "default")
        else:
            self.set(None, "empty")

    def set(self, value, source):
        self.value, self.source = value, source

    def changed(self):
        return self.value != self.current


def build_fields(meta, game, folder, platforms, region):
    dates = release_dates(game, platforms) if game else []
    chosen = best_date(dates, region)
    igdb = game or {}

    names = unique([igdb.get("name")] +
                   [loc.get("name") for loc in igdb.get("game_localizations") or []] +
                   [a.get("name") for a in igdb.get("alternative_names") or []
                    if "title" in (a.get("comment") or "").lower()] +
                   [search_name(folder.name)])
    name_choices = [(name_source(igdb, n, folder), n) for n in names if n]
    date_choices = [(f"{d['platform'] or '?'} · {d['region'] or '?'}" + ("" if d["precise"] else " · imprecise"),
                     iso_date(d["date"])) for d in sorted(dates, key=lambda d: d["date"])]

    def proposal(value):
        return value if game else None

    return [
        Field("Name", "Name", "text", meta.get("Name"), proposal(igdb.get("name")), choices=name_choices),
        Field("Developers", "Developers", "list", meta.get("Developers"), proposal(companies(igdb, "developer"))),
        Field("Publishers", "Publishers", "list", meta.get("Publishers"), proposal(companies(igdb, "publisher"))),
        Field("Release", "Release type", "release", meta.get("Release"), default="Retail"),
        Field("ReleaseDate", "Release date", "date", meta.get("ReleaseDate"),
              proposal(iso_date(chosen["date"]) if chosen else None), choices=date_choices),
        Field("Version", "Version", "text", meta.get("Version")),
        Field("PartNumber", "Part number", "text", meta.get("PartNumber"),
              choices=[(f"from the {where}", value) for where, value in part_numbers_choices(folder.name)]),
        Field("SerialNumber", "Serial number", "text", meta.get("SerialNumber")),
        Field("Barcodes", "Barcodes", "barcodes", meta.get("Barcodes")),
        Field("Keywords", "Keywords", "list", meta.get("Keywords"), proposal(keywords(igdb))),
        Field("Categories", "Categories", "list", meta.get("Categories"), default=DEFAULT_CATEGORIES),
        Field("Subcategories", "Subcategories", "list", meta.get("Subcategories"), proposal(subcategories(igdb))),
        Field("Languages", "Languages", "languages", meta.get("Languages"), proposal(languages(igdb))),
        Field("RequiredOperatingSystems", "Operating system", "os", meta.get("RequiredOperatingSystems"),
              proposal(operating_systems(igdb, platforms))),
    ]


def name_source(game, name, folder):
    if name == game.get("name"):
        return "IGDB name"
    for loc in game.get("game_localizations") or []:
        if loc.get("name") == name:
            return f"IGDB {(loc.get('region') or {}).get('name', 'localized')} title"
    for alt in game.get("alternative_names") or []:
        if alt.get("name") == name:
            return f"IGDB {alt.get('comment') or 'alternative name'}"
    return "folder name"


def ean_valid(digits):
    """GS1 check digit (EAN-13, EAN-8, ITF-14)."""
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def isbn_valid(digits):
    """ISBN-10 (mod 11, X is 10) or ISBN-13 (an EAN-13 in the 978/979 Bookland prefixes)."""
    if re.fullmatch(r"\d{9}[\dX]", digits):
        return sum((10 - i) * (10 if d == "X" else int(d)) for i, d in enumerate(digits)) % 11 == 0
    return bool(re.fullmatch(r"97[89]\d{10}", digits)) and ean_valid(digits)


def parse_barcodes(text):
    """"EAN13 8436...; ISBN 84-..." or bare codes (spaces and dashes allowed), several separated by ";". Bare codes
    are told apart by length: 13 digits are an EAN-13, 12 an UPC-A, 8 an EAN-8 and 10 (the last may be X) an ISBN-10.
    Aaru has no UPC-A type, but an UPC-A is the EAN-13 with a leading 0 (same check digit), so it is stored as that.
    A 978/979 EAN-13 is also the ISBN-13 of the product, but it stays an EAN-13 unless written as "ISBN ...", so the
    printed barcode and the ISBN (often the ISBN-10) can both be stored. ISBNs keep their dashes as written.
    Returns (barcodes, error)."""
    barcodes = []
    for part in filter(None, (p.strip() for p in text.split(";"))):
        if re.fullmatch(r"[\d\s-]+[xX]?", part):
            kind, value = "", part
        else:
            kind, _, value = part.partition(" ")
        value = value.strip().upper() if kind.upper() == "ISBN" or not kind else value.strip()
        if kind.lower().replace("-", "") in ("upc", "upca"):
            kind = "EAN13"
        if kind:
            matches = [t for t in BARCODE_TYPES if t.lower() == kind.lower()]
            if not matches:
                return None, f"Unknown barcode type “{kind}”, one of: {', '.join(BARCODE_TYPES)}"
            kind = matches[0]
        digits = re.sub(r"[\s-]", "", value)
        if not kind:
            if len(digits) == 10:
                kind = "ISBN"
            elif digits.isdigit() and len(digits) in (8, 12, 13):
                if len(digits) == 12:
                    if not ean_valid(digits):
                        return None, f"Wrong check digit in UPC-A {digits} (mistyped, or an EAN-13 missing a digit?)"
                    digits = "0" + digits
                kind = "EAN8" if len(digits) == 8 else "EAN13"
            else:
                return None, (f"“{value}” is not an EAN-13, UPC-A, EAN-8 or ISBN-10: check it, or give its type "
                              f"before it (e.g. ISBN {value})")
        if kind == "EAN13" and len(digits) == 12 and digits.isdigit():
            digits = "0" + digits  # an UPC-A
        if kind in ("EAN13", "EAN8", "ITF14"):
            length = {"EAN13": 13, "EAN8": 8, "ITF14": 14}[kind]
            if not digits.isdigit() or len(digits) != length:
                return None, f"An {kind} has {length} digits, “{value}” does not"
            if not ean_valid(digits):
                return None, f"Wrong check digit in {kind} {digits} (mistyped?)"
            value = digits
        elif kind == "ISBN":
            if len(digits) not in (10, 13):
                return None, f"An ISBN has 10 or 13 digits, “{value}” does not"
            if not isbn_valid(digits):
                return None, f"Wrong check digit in ISBN {value} (mistyped?)"
            value = value.replace(" ", "-")
        barcode = {"Type": kind, "Value": value}
        if barcode not in barcodes:
            barcodes.append(barcode)
    return barcodes, None


def folder_isbn(folder_name):
    """An ISBN used as the product code in the folder name, e.g. "Aquanox (84-9738-024-X)"."""
    for group in re.findall(r"[(\[]([^)\]]*)[)\]]", folder_name):
        group = group.strip().upper()
        if re.fullmatch(r"[\d-]+X?", group) and isbn_valid(group.replace("-", "")):
            return group
    return None


def ask_barcode(field, folder_name):
    """Asks for the barcodes of a product that has none, setting them on the field."""
    isbn = folder_isbn(folder_name)
    if isbn:
        console.print(f"[dim]The folder name has the ISBN {isbn}; add the EAN-13 after it if there is one[/dim]")
    prefill = f"ISBN {isbn}; " if isbn else ""
    while True:
        answer = ask("Barcode: EAN-13, UPC-A or ISBN, several separated by “;” (Enter for none): ", prefill)
        if not answer:
            return
        barcodes, error = parse_barcodes(answer)
        if error:
            console.print(f"[red]{error}[/red]")
            prefill = answer
            continue
        field.set(barcodes, "edited")
        return


def iso_date(date):
    return date.strftime("%Y-%m-%dT00:00:00")


def show(field, value):
    if value is None:
        return Text("—", style="dim")
    if field.kind in ("list", "languages"):
        return Text("; ".join(value))
    if field.kind == "date":
        return Text(value[:10])
    if field.kind == "os":
        return Text("; ".join(" ".join([os_["Name"]] + (os_.get("Versions") or [])) for os_ in value))
    if field.kind == "barcodes":
        return Text("; ".join(f"{b.get('Type')} {b.get('Value')}" for b in value))
    return Text(str(value))


SOURCES = {
    "kept": ("kept", "cyan"),
    "igdb": ("IGDB", "green"),
    "merged": ("merged", "green"),
    "choice": ("IGDB", "green"),
    "edited": ("edited", "magenta"),
    "default": ("default", "yellow"),
    "cleared": ("cleared", "red"),
    "empty": ("", "dim"),
}


# ---------------------------------------------------------------- Prompts

def ask(prompt, prefill=""):
    """input() with a colored prompt and, when readline is there, an editable pre-filled answer."""
    if console.no_color or not sys.stdout.isatty():
        text = prompt
    else:  # \001 \002 tell readline that the escape codes take no room
        text = f"\001\033[1;36m\002{prompt}\001\033[0m\002"
    if readline and prefill:
        readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        raise Quit
    finally:
        if readline and prefill:
            readline.set_startup_hook()


def confirm(prompt, default=False):
    answer = ask(f"{prompt} [{'Y/n' if default else 'y/N'}] ").lower()
    return default if not answer else answer.startswith(("y", "s"))


def keys(*pairs):
    """A line of [key] action hints."""
    text = Text()
    for key, action in pairs:
        text.append(f" {key} ", style="bold black on cyan")
        text.append(f" {action}   ")
    return text


# ---------------------------------------------------------------- Choosing the game

def game_table(games, term, platforms, start=1):
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold", expand=True, pad_edge=False)
    table.add_column("#", justify="right", style="bold cyan", no_wrap=True)
    table.add_column("Name", ratio=3)
    table.add_column("Year", no_wrap=True)
    table.add_column("Type", style="dim", no_wrap=True)
    table.add_column("Developers", ratio=2)
    table.add_column("Publishers", ratio=2)
    table.add_column("Platforms", ratio=2)
    for i, game in enumerate(games, start):
        name = Text(game.get("name", "?"), style="bold" if is_exact(game, term) else "")
        if game.get("version_parent"):
            name.append(f"\n  edition of {game['version_parent'].get('name')}", style="dim")
        elif game.get("parent_game"):
            name.append(f"\n  for {game['parent_game'].get('name')}", style="dim")
        # The folder platforms in full, the rest only counted unless there are few
        matching = [p for p in platform_names(game) if platforms and p in platforms]
        others = [p for p in platform_names(game) if p not in matching]
        shown = Text(", ".join(matching), style="green")
        if others:
            shown.append(("\n" if matching else "") +
                         (", ".join(others) if len(others) <= 2 or not matching else f"+{len(others)} more"),
                         style="dim")
        table.add_row(str(i), name, str(year_of(game) or "?"), game_type(game),
                      ", ".join(companies(game, "developer")) or "—", ", ".join(companies(game, "publisher")) or "—",
                      shown)
    return table


def parse_years(text):
    m = re.fullmatch(r"(\d{4})(?:\s*-\s*(\d{4}))?", text.strip())
    if not m:
        return None
    return int(m[1]), int(m[2] or m[1])


def choose_game(igdb, term, platforms, year=None, company=None, auto=True):
    """Returns the chosen IGDB game (list entry, not details), or None to skip the folder."""
    results, searched = find(igdb, term, platforms)
    platform_only = bool(platforms)
    everything = False
    page = 0
    while True:
        games = filter_games(results, year, company)
        shown = filter_games(games, platforms=platforms if platform_only else None) or games
        exact = [g for g in shown if is_exact(g, term)]
        others = len(shown) - len(exact)
        if exact and not everything:
            shown = exact
        if auto and len(exact) == 1 and (not platforms or on_platform(exact[0], platforms)):
            return exact[0]
        auto = False

        title = Text()
        if len(exact) > 1:
            title.append(f"{len(exact)} games are called “{term}”", style="bold yellow")
            title.append(" — choose by year, company or platform")
        elif exact:
            title.append(f"“{term}”", style="bold")
            title.append(" exists, but not for this platform" if platforms and not on_platform(exact[0], platforms)
                         else " was found")
        elif shown:
            title.append(f"No game is called exactly “{term}”", style="bold yellow")
            title.append(", closest results")
        else:
            title.append(f"Nothing found for “{term}”", style="bold red")
        if searched != term:
            title.append(f"   searched as “{searched}”", style="dim")
        filters = []
        if year:
            filters.append(f"year {year[0]}" + (f"-{year[1]}" if year[1] != year[0] else ""))
        if company:
            filters.append(f"company “{company}”")
        if platform_only and platforms:
            filters.append("platform " + " / ".join(platforms))
        if filters:
            title.append("   filtered by " + ", ".join(filters), style="dim")

        per_page = 15
        page = min(page, max(0, (len(shown) - 1) // per_page))
        visible = shown[page * per_page:(page + 1) * per_page]
        body = [game_table(visible, term, platforms, page * per_page + 1)] if visible else []
        if len(shown) > per_page:
            body.append(Text(f"page {page + 1}/{(len(shown) - 1) // per_page + 1}", style="dim", justify="right"))
        console.print(Panel(Group(*body) if body else Text("—", style="dim"), title=title, title_align="left",
                            border_style="yellow" if len(exact) != 1 else "cyan"))
        hints = [("1-n", "choose"), ("y 1998", "year"), ("c name", "company"),
                 ("p", "all platforms" if platform_only else "only this platform"), ("a", "clear filters")]
        if exact and others:
            hints.append(("o", "same name only" if everything else f"{others} other results"))
        hints += [("/text", "search"), ("#id", "IGDB id/url")]
        if len(shown) > per_page:
            hints.append(("n/b", "next/back page"))
        console.print(keys(*hints, ("s", "skip"), ("q", "quit")))
        answer = ask("› ")
        if answer.isdigit() and 1 <= int(answer) <= len(shown):
            return shown[int(answer) - 1]
        command, _, rest = answer.partition(" ")
        if answer.startswith("/") and answer[1:].strip():
            term = answer[1:].strip()
            results, searched = find(igdb, term, platforms)
            page = 0
        elif answer.startswith("#") and answer[1:].strip():
            found = igdb.lookup(answer[1:])
            if found:
                return found[0]
            console.print("[red]No game with that id or URL[/red]")
        elif command == "y" and parse_years(rest):
            year = parse_years(rest)
        elif command == "c" and rest.strip():
            company = rest.strip()
        elif answer == "p":
            platform_only = not platform_only
        elif answer == "a":
            year = company = None
        elif answer == "o":
            everything = not everything
            page = 0
        elif answer == "n":
            page += 1
        elif answer == "b":
            page = max(0, page - 1)
        elif answer == "s":
            return None
        elif answer == "q":
            raise Quit
        elif answer:
            console.print("[red]?[/red]")


# ---------------------------------------------------------------- Review

def media_list(meta):
    return [(key, m) for key in MEDIA_KEYS for m in meta.get(key) or []]


def image_name(media):
    image = media.get("Image")
    return (image.get("Value") if isinstance(image, dict) else image) or ""


def part_numbers_in(name):
    """What is in parentheses or brackets in a name and looks like a part number: it has a digit (unlike "Codegame"
    or "PC Plus"), is not a disc number ("CD 1", "Disc 2") and is not an ISBN (that is a barcode)."""
    found = []
    for group in re.findall(r"[(\[]([^)\]]*)[)\]]", name):
        group = group.strip()
        if (not re.search(r"\d", group)
                or re.fullmatch(r"(?i)(cd|dvd|bd|gd|disc|disco|disk|disque|cara|side)[\s-]*\w{1,2}|\d{1,2}", group)
                or (re.fullmatch(r"[\d-]+[xX]?", group) and isbn_valid(group.replace("-", "").upper()))):
            continue
        if group not in found:
            found.append(group)
    return found


def part_numbers_choices(folder_name):
    return [("folder name", p) for p in part_numbers_in(folder_name)]


def part_candidates(media):
    """Possible part numbers of a disc, from its image name. Returns (where, value) pairs."""
    stem = re.sub(r"(\.compressed)?\.aif$", "", image_name(media), flags=re.IGNORECASE)
    return [("image name", p) for p in part_numbers_in(stem)]


def media_table(meta, parts):
    media = media_list(meta)
    if not media:
        return None
    table = Table(box=box.SIMPLE, header_style="bold", expand=True, pad_edge=False)
    table.add_column("#", justify="right", style="bold cyan", no_wrap=True)
    for column in ("Image", "Type", "Part number", "Disc", "Size"):
        table.add_column(column, no_wrap=column != "Image")
    for i, (key, m) in enumerate(media):
        sequence = m.get("Sequence") or {}
        kind = " / ".join(str(m[k]) for k in ("DiscType", "DiscSubType") if m.get(k)) or key
        part = parts.get(i, m.get("PartNumber"))
        if part is None:
            shown = Text("—", style="dim")
        else:
            shown = Text(part, style="bold magenta" if part != m.get("PartNumber") else "")
        if i in parts and parts[i] != m.get("PartNumber"):
            shown.append("  edited" if part is not None else "  cleared", style="magenta")
        table.add_row(f"d{i + 1}" if len(media) > 1 else "d", image_name(m) or "?", kind, shown,
                      f"{sequence.get('MediaSequence', '?')}/{sequence.get('TotalMedia', '?')}",
                      human_size(m.get("Size")))
    return table


def part_changes(meta, parts):
    media = media_list(meta)
    return sum(parts[i] != media[i][1].get("PartNumber") for i in parts)


def choose_part(title, candidates, current):
    """Asks for a part number. Returns the new value (None for none); Enter keeps the current one."""
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_column(style="dim")
    for i, (where, value) in enumerate(candidates, 1):
        table.add_row(str(i), value, f"from the {where}")
    console.print(Panel(table if candidates else Text("No suggestions", style="dim"),
                        title=title, title_align="left",
                        border_style="blue"))
    hint = ("1 or " if len(candidates) == 1 else f"1-{len(candidates)} or ") if candidates else ""
    if current:
        answer = ask(f"Part number ({hint}type it, Enter keeps {current}, - for none): ")
    else:
        answer = ask(f"Part number ({hint}type it, Enter for none): ")
    if answer.isdigit() and 1 <= int(answer) <= len(candidates):
        return candidates[int(answer) - 1][1]
    if answer == "-":
        return None
    return answer or current


def disc_title(media):
    return f"Part number of the disc {image_name(media) or '?'}"


def ask_part_numbers(meta, parts):
    """Suggests a part number for every disc that has none and something in parentheses to take it from."""
    for i, (_, media) in enumerate(media_list(meta)):
        if i not in parts and not media.get("PartNumber") and part_candidates(media):
            parts[i] = choose_part(disc_title(media), part_candidates(media), None)


def edit_part(meta, parts, answer):
    media = media_list(meta)
    index = 0 if answer == "d" else int(answer[1:]) - 1
    if not 0 <= index < len(media):
        console.print("[red]?[/red]")
        return
    disc = media[index][1]
    parts[index] = choose_part(disc_title(disc), part_candidates(disc), parts.get(index, disc.get("PartNumber")))


def human_size(size):
    if not size:
        return ""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def game_panel(game):
    if not game:
        return Panel(Text("No IGDB game chosen: only the current values and defaults", style="yellow"),
                     border_style="yellow")
    text = Text()
    text.append(game.get("name", "?"), style="bold")
    text.append(f"  {year_of(game) or '?'}  {game_type(game)}", style="dim")
    if game.get("url"):
        text.append(f"\n{game['url']}", style="blue underline")
    if platform_names(game):
        text.append("\n" + ", ".join(platform_names(game)), style="dim")
    if game.get("summary"):
        summary = " ".join(game["summary"].split())
        text.append("\n\n" + (summary[:400] + "…" if len(summary) > 400 else summary), style="italic")
    return Panel(text, title="IGDB", title_align="left", border_style="green")


def fields_table(fields):
    table = Table(box=box.ROUNDED, header_style="bold", expand=True, pad_edge=False)
    table.add_column("#", justify="right", style="bold cyan", no_wrap=True)
    table.add_column("Field", style="bold", no_wrap=True)
    table.add_column("Current", ratio=3)
    table.add_column("IGDB", ratio=3)
    table.add_column("→ Result", ratio=3)
    table.add_column("", no_wrap=True, min_width=7)
    for i, field in enumerate(fields, 1):
        label, color = SOURCES[field.source]
        result = show(field, field.value)
        result.stylize("bold " + color if field.changed() else "")
        igdb = show(field, field.igdb)
        if field.igdb is not None and field.igdb == field.value:
            igdb.stylize("green")
        else:
            igdb.stylize("dim")
        table.add_row(str(i), field.label, show(field, field.current), igdb, result, Text(label, style=color))
    return table


def edit_field(field):
    options = []
    if field.current is not None:
        options.append(("current value", field.current, "kept"))
    if field.igdb is not None:
        options.append(("IGDB value", field.igdb, "igdb"))
    if field.kind in ("list", "languages") and field.current and field.igdb:
        merged = unique(field.current + field.igdb)
        if merged not in (field.current, field.igdb):
            options.append(("current + IGDB", merged, "merged"))
    for description, value in field.choices:
        if all(value != o[1] for o in options):
            options.append((description, value, "choice"))
    if field.kind == "release":
        options += [(r, r, "edited") for r in RELEASE_TYPES if all(r != o[1] for o in options)]

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_column(style="dim")
    for i, (description, value, _) in enumerate(options, 1):
        table.add_row(str(i), show(field, value), description)
    console.print(Panel(table, title=f"{field.label}", title_align="left", border_style="cyan"))
    hints = [("1-n", "use"), ("e", "edit"), ("x", "clear"), ("Enter", "back")]
    console.print(keys(*hints) if options else keys(*hints[1:]))
    if field.kind in ("list", "languages"):
        console.print("[dim]Lists are edited separated by “;”[/dim]" +
                      ("[dim], languages as ISO 639-2/B codes (eng; spa; fre…)[/dim]" if field.kind == "languages"
                       else ""))
    elif field.kind == "barcodes":
        console.print("[dim]Barcodes are edited as “TYPE value” separated by “;” (EAN13 8436...; ISBN 84-...); "
                      "bare codes are told apart by length: EAN-13, UPC-A, EAN-8 or ISBN-10[/dim]")

    answer = ask("› ")
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        _, value, source = options[int(answer) - 1]
        field.set(value, source)
    elif answer == "x":
        field.set(None, "cleared")
    elif answer == "e":
        manual_edit(field)
    elif answer:
        console.print("[red]?[/red]")


def manual_edit(field):
    while True:
        prefill = show(field, field.value).plain if field.value is not None else ""
        if field.kind == "release" and not prefill:
            prefill = "Retail"
        answer = ask(f"{field.label}: ", prefill if prefill != "—" else "")
        if not answer:
            field.set(None, "cleared")
            return
        if field.kind in ("list", "languages"):
            value = unique(part.strip() for part in answer.split(";"))
            if field.kind == "languages":
                value = [v.lower() for v in value]
                bad = [v for v in value if v not in AARU_LANGUAGES]
                if bad:
                    console.print(f"[red]Unknown language codes: {', '.join(bad)}[/red]")
                    continue
        elif field.kind == "date":
            try:
                value = iso_date(datetime.strptime(answer[:10], "%Y-%m-%d"))
            except ValueError:
                console.print("[red]Use YYYY-MM-DD[/red]")
                continue
        elif field.kind == "release":
            matches = [r for r in RELEASE_TYPES if r.lower() == answer.lower()]
            if not matches:
                console.print(f"[red]One of: {', '.join(RELEASE_TYPES)}[/red]")
                continue
            value = matches[0]
        elif field.kind == "barcodes":
            value, error = parse_barcodes(answer)
            if error:
                console.print(f"[red]{error}[/red]")
                continue
        elif field.kind == "os":
            value = []
            for part in answer.split(";"):
                name, *versions = part.split()
                value.append({"Name": name, **({"Versions": versions} if versions else {})})
        else:
            value = answer
        field.set(value, "kept" if value == field.current else "edited")
        return


def review(path, meta, game, fields, parts, exists, dry_run):
    """Returns "write", "game" (choose another game) or "skip"."""
    while True:
        console.print(game_panel(game))
        media = media_table(meta, parts)
        if media:
            console.print(Panel(media, title="Media (only their part numbers can be changed)", title_align="left",
                                border_style="blue"))
        changes = sum(f.changed() for f in fields) + part_changes(meta, parts)
        console.print(Panel(fields_table(fields), title=path.name + ("" if exists else "  (new file)"),
                            title_align="left", subtitle=f"{changes} change{'s' if changes != 1 else ''}",
                            subtitle_align="right", border_style="magenta"))
        hints = [("Enter", "show only, dry run" if dry_run else "write"), ("1-n", "change field")]
        if media:
            hints.append(("d1-n" if len(media_list(meta)) > 1 else "d", "disc part number"))
        console.print(keys(*hints, ("g", "choose another game"), ("s", "skip"), ("q", "quit")))
        answer = ask("› ")
        if not answer:
            return "write"
        if answer.isdigit() and 1 <= int(answer) <= len(fields):
            field = fields[int(answer) - 1]
            if field.editable:
                edit_field(field)
            else:
                console.print(f"[yellow]{field.label} is shown but not changed by this script[/yellow]")
        elif media and re.fullmatch(r"d\d*", answer):
            edit_part(meta, parts, answer)
        elif answer == "g":
            return "game"
        elif answer == "s":
            return "skip"
        elif answer == "q":
            raise Quit
        else:
            console.print("[red]?[/red]")


# ---------------------------------------------------------------- Files

def load(path):
    if not path.exists():
        return {"AaruMetadata": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("AaruMetadata"), dict):
        raise ValueError("not an Aaru metadata file (no AaruMetadata)")
    return data


def apply(meta, fields):
    for field in fields:
        if field.value is None:
            meta.pop(field.key, None)
        else:
            meta[field.key] = field.value
    known = [k for k in KEY_ORDER if k in meta]
    return {**{k: meta[k] for k in known}, **{k: v for k, v in meta.items() if k not in known}}


def set_parts(meta, parts):
    media = media_list(meta)
    for i, value in parts.items():
        if value is None:
            media[i][1].pop("PartNumber", None)
        elif "PartNumber" in media[i][1]:
            media[i][1]["PartNumber"] = value
        else:
            # Where Aaru puts it: after the checksums of the whole disc
            disc = media[i][1]
            before = [k for k in disc if k in ("Image", "Size", "Sequence", "Layers", "Checksums")]
            at = list(disc).index(before[-1]) + 1 if before else 0
            items = list(disc.items())
            disc.clear()
            disc.update(items[:at] + [("PartNumber", value)] + items[at:])


def save(path, data):
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        if not backup.exists():  # never overwrite the original backup on re-runs
            shutil.copy2(path, backup)

    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def metadata_files(folder):
    if (folder / "metadata.json").exists():
        return [folder / "metadata.json"]
    return sorted(folder.glob("*.metadata.json")) or [folder / "metadata.json"]


def complete(meta):
    return all(meta.get(k) for k in ("Name", "Developers", "Publishers", "ReleaseDate"))


# ---------------------------------------------------------------- Main

def process(igdb, folder, args):
    console.print(Rule(Text(folder.name, style="bold"), style="cyan"))
    paths = metadata_files(folder)
    loaded = []
    for path in paths:
        try:
            data = load(path)
        except (OSError, ValueError) as e:
            console.print(f"[red]✖ {path}: {e}[/red]")
            return False
        if args.skip_complete and complete(data["AaruMetadata"]):
            console.print(f"[dim]{path.name} already has name, companies and release date, skipping[/dim]")
            continue
        loaded.append((path, data))
    if not loaded:
        return True

    if not paths[0].exists() and any(folder.glob("*.aif")):
        console.print("[yellow]This folder has images but no metadata: a new metadata.json without the discs would "
                      "make create_sidecars.sh skip the folder.[/yellow]")
        if not confirm("Create it anyway?"):
            return True

    platforms = tuple(p.strip() for p in args.platform.split(",")) if args.platform else platform_hint(folder)
    term = args.name or search_name(folder.name)
    year = args.year or ((folder_year(folder.name),) * 2 if folder_year(folder.name) else None)
    auto = not args.choose
    game = None
    barcodes = None  # asked once for the folder: the sidecars of a set share the box
    folder_part = None  # asked once for the folder, like the barcodes
    parts = {path: {} for path, _ in loaded}  # disc index -> new part number, asked once per file
    while True:
        if game is None:
            chosen = choose_game(igdb, term, platforms, year, args.company, auto)
            if chosen is None:
                console.print("[yellow]Skipped[/yellow]")
                return True
            with console.status("Fetching game details…"):
                game = igdb.details(chosen["id"])
        auto = False

        for path, data in loaded:
            meta = data["AaruMetadata"]
            fields = build_fields(meta, game, folder, platforms, args.region)
            barcode = next(f for f in fields if f.key == "Barcodes")
            if barcode.current is None and not args.no_barcode:
                if barcodes is None:
                    if game:
                        console.print(Text.assemble(("▸ ", "green"), (game.get("name", "?"), "bold"),
                                                    (f"  {year_of(game) or '?'}  {game_type(game)}", "dim")))
                    ask_barcode(barcode, folder.name)
                    barcodes = barcode.value or []
                elif barcodes:
                    barcode.set(barcodes, "edited")
            if not args.no_part_numbers:
                part = next(f for f in fields if f.key == "PartNumber")
                if part.current is None and part.choices:
                    if folder_part is None:
                        folder_part = choose_part(f"Part number of {folder.name}", part_numbers_choices(folder.name),
                                                  None) or ""
                    if folder_part:
                        part.set(folder_part, "edited")
                ask_part_numbers(meta, parts[path])
            action = review(path, meta, game, fields, parts[path], path.exists(), args.dry_run)
            if action == "game":
                game = None
                break
            if action == "skip":
                console.print(f"[yellow]{path.name} not changed[/yellow]")
                continue
            if not any(f.changed() for f in fields) and not part_changes(meta, parts[path]):
                console.print(f"[dim]{path.name}: nothing changes[/dim]")
            elif args.dry_run:
                console.print(f"[yellow]Dry run: {path.name} not written[/yellow]")
            else:
                set_parts(meta, parts[path])
                data["AaruMetadata"] = apply(meta, fields)
                save(path, data)
                console.print(f"[bold green]✔ {path.name} written[/bold green]")
        else:
            return True


def fail(message):
    console.print(f"[bold red]✖[/bold red] {message}", style="red")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folders", nargs="*", type=Path, default=[Path(".")],
                        help="Game folders (default: the current folder)")
    parser.add_argument("-r", "--subfolders", action="store_true",
                        help="Process every subfolder of the given folders as a game folder")
    parser.add_argument("--name", help="Search for this name instead of the folder name")
    parser.add_argument("--year", type=parse_years, metavar="YEAR[-YEAR]",
                        help="Only consider games first released in that year or range")
    parser.add_argument("--company", help="Only consider games by a developer or publisher containing this text")
    parser.add_argument("--platform", help="IGDB platform names, comma separated, instead of the one of the path")
    parser.add_argument("--region", choices=REGIONS, default="europe",
                        help="Preferred release date region (default: europe)")
    parser.add_argument("--choose", action="store_true",
                        help="Always show the list of games, even when only one has the folder name")
    parser.add_argument("--no-barcode", action="store_true",
                        help="Do not ask for the EAN-13 barcode of games that have none")
    parser.add_argument("--no-part-numbers", action="store_true",
                        help="Do not suggest part numbers for the discs that have none")
    parser.add_argument("--skip-complete", action="store_true",
                        help="Skip metadata that already has name, developers, publishers and release date")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Show everything but do not write")
    args = parser.parse_args()

    folders = []
    for folder in args.folders:
        if not folder.is_dir():
            fail(f"{folder} is not a folder")
        folders += sorted(p for p in folder.iterdir() if p.is_dir()) if args.subfolders else [folder.resolve()]
    if args.name and len(folders) > 1:
        fail("--name only makes sense with a single folder")

    igdb = Igdb(*load_credentials())
    errors = 0
    try:
        for folder in folders:
            try:
                process(igdb, folder.resolve(), args)
            except RuntimeError as e:
                errors += 1
                console.print(f"[bold red]✖[/bold red] {folder}: {e}")
    except Quit:
        console.print("[dim]Bye[/dim]")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
