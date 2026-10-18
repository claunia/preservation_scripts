"""Pieces shared by the interactive metadata scripts (igdb_metadata.py, edit_metadata.py): prompts, Aaru metadata
vocabularies, barcode and part number parsing, and reading and writing the metadata files."""

import json
import re
import shutil
import sys

try:
    import readline
except ImportError:
    readline = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("This script needs the 'rich' Python module: run it with /usr/bin/python3, install python-rich, "
             "or use 'uv run <script>'.")

console = Console(highlight=False)


# Order of the fields in the Aaru Metadata class, which is also the order Aaru writes them in
KEY_ORDER = ("Developers", "Publishers", "Authors", "Performers", "Name", "Version", "Release", "ReleaseDate",
             "Barcodes", "PartNumber", "SerialNumber", "Keywords", "Magazines", "Books", "Categories",
             "Subcategories", "Languages", "Systems", "Architectures", "RequiredOperatingSystems", "UserManuals",
             "OpticalDiscs", "Advertisements", "LinearMedias", "PciCards", "BlockMedias", "AudioMedias")


MEDIA_KEYS = ("OpticalDiscs", "BlockMedias", "LinearMedias", "AudioMedias")


RELEASE_TYPES = ("Retail", "Bundle", "Coverdisc", "Subscription", "Demo", "OEM", "Shareware", "FOSS", "Adware",
                 "Donationware", "DigitalDownload", "SaaS")


# Aaru.CommonTypes/AaruMetadata/Barcode.cs
BARCODE_TYPES = ("Aztec", "Codabar", "Code11", "Code128", "Code39", "Code93", "CPC_Binary", "EZcode", "FIM", "ITF",
                 "ITF14", "EAN13", "EAN8", "MaxiCode", "ISBN", "ISRC", "MSI", "ShotCode", "RM4SCC", "QR", "EAN5", "EAN2",
                 "POSTNET", "PostBar", "Plessey", "Pharmacode", "PDF417", "PatchCode")


# Every language Aaru knows, with its English name (Aaru.CommonTypes/AaruMetadata/Language.cs, Aaru.Localization/UI.resx)
LANGUAGES = {
    "aar": 'Afar', "abk": 'Abkhazian', "ace": 'Achinese', "ach": 'Acoli', "ada": 'Adangme', "ady": 'Adyghe',
    "afa": 'Afro-Asiatic languages', "afh": 'Afrihili', "afr": 'Afrikaans', "ain": 'Ainu', "aka": 'Akan',
    "akk": 'Akkadian', "alb": 'Albanian', "ale": 'Aleut', "alg": 'Algonquian languages', "alt": 'Southern Altai',
    "amh": 'Amharic', "ang": 'Old English', "anp": 'Angika', "apa": 'Apache languages', "ara": 'Arabic',
    "arc": 'Official Aramaic', "arg": 'Aragonese', "arm": 'Armenian', "arn": 'Mapudungun', "arp": 'Arapaho',
    "art": 'Artificial languages', "arw": 'Arawak', "asm": 'Assamese', "ast": 'Asturian',
    "ath": 'Athapascan languages', "aus": 'Australian languages', "ava": 'Avaric', "ave": 'Avestan', "awa": 'Awadhi',
    "aym": 'Aymara', "aze": 'Azerbaijani', "bad": 'Banda languages', "bai": 'Bamileke languages', "bak": 'Bashkir',
    "bal": 'Baluchi', "bam": 'Bambara', "ban": 'Balinese', "baq": 'Basque', "bas": 'Basa', "bat": 'Baltic languages',
    "bej": 'Beja', "bel": 'Belarusian', "bem": 'Bemba', "ben": 'Bengali', "ber": 'Berber languages',
    "bho": 'Bhojpuri', "bih": 'Bihari languages', "bik": 'Bikol', "bin": 'Bini', "bis": 'Bislama', "bla": 'Siksika',
    "bnt": 'Bantu languages', "bos": 'Bosnian', "bra": 'Braj', "bre": 'Breton', "btk": 'Batak languages',
    "bua": 'Buriat', "bug": 'Buginese', "bul": 'Bulgarian', "bur": 'Burmese', "byn": 'Blin', "cad": 'Caddo',
    "cai": 'Central American Indian languages', "car": 'Galibi Carib', "cat": 'Catalan',
    "cau": 'Caucasian languages', "ceb": 'Cebuano', "cel": 'Celtic languages', "cha": 'Chamorro', "chb": 'Chibcha',
    "che": 'Chechen', "chg": 'Chagatai', "chi": 'Chinese', "chk": 'Chuukese', "chm": 'Mari', "chn": 'Chinook jargon',
    "cho": 'Choctaw', "chp": 'Chipewyan', "chr": 'Cherokee', "chu": 'Church Slavic', "chv": 'Chuvash',
    "chy": 'Cheyenne', "cmc": 'Chamic languages', "cop": 'Coptic', "cor": 'Cornish', "cos": 'Corsican',
    "cpe": 'Creoles and pidgins, English based', "cpf": 'Creoles and pidgins, French-based',
    "cpp": 'Creoles and pidgins, Portuguese-based', "cre": 'Cree', "crh": 'Crimean Tatar',
    "crp": 'Creoles and pidgins', "csb": 'Kashubian', "cus": 'Cushitic languages', "cze": 'Czech', "dak": 'Dakota',
    "dan": 'Danish', "dar": 'Dargwa', "day": 'Land Dayak languages', "del": 'Delaware', "den": 'Slave',
    "dgr": 'Dogrib', "din": 'Dinka', "div": 'Dhivehi', "doi": 'Dogri', "dra": 'Dravidian languages',
    "dsb": 'Lower Sorbian', "dua": 'Duala', "dum": 'Dutch, Middle', "dut": 'Dutch', "dyu": 'Dyula',
    "dzo": 'Dzongkha', "efi": 'Efik', "egy": 'Egyptian', "eka": 'Ekajuk', "elx": 'Elamite', "eng": 'English',
    "enm": 'English, Middle', "epo": 'Esperanto', "est": 'Estonian', "ewe": 'Ewe', "ewo": 'Ewondo', "fan": 'Fang',
    "fao": 'Faroese', "fat": 'Fanti', "fij": 'Fijian', "fil": 'Filipino', "fin": 'Finnish',
    "fiu": 'Finno-Ugrian languages', "fon": 'Fon', "fre": 'French', "frm": 'French, Middle', "fro": 'French, Old',
    "frr": 'Northern Frisian', "frs": 'Eastern Frisian', "fry": 'Western Frisian', "ful": 'Fulah', "fur": 'Friulian',
    "gaa": 'Ga', "gay": 'Gayo', "gba": 'Gbaya', "gem": 'Germanic languages', "geo": 'Georgian', "ger": 'German',
    "gez": 'Geez', "gil": 'Gilbertese', "gla": 'Scottish Gaelic', "gle": 'Irish', "glg": 'Galician', "glv": 'Manx',
    "gmh": 'German, Middle High', "goh": 'German, Old High', "gon": 'Gondi', "gor": 'Gorontalo', "got": 'Gothic',
    "grb": 'Grebo', "grc": 'Greek, Ancient', "gre": 'Greek, Modern', "grn": 'Guarani', "gsw": 'Swiss German',
    "guj": 'Gujarati', "gwi": "Gwich'in", "hai": 'Haida', "hat": 'Haitian', "hau": 'Hausa', "haw": 'Hawaiian',
    "heb": 'Hebrew', "her": 'Herero', "hil": 'Hiligaynon', "him": 'Himachali languages', "hin": 'Hindi',
    "hit": 'Hittite', "hmn": 'Hmong', "hmo": 'Hiri Motu', "hrv": 'Croatian', "hsb": 'Upper Sorbian',
    "hun": 'Hungarian', "hup": 'Hupa', "iba": 'Iban', "ibo": 'Igbo', "ice": 'Icelandic', "ido": 'Ido',
    "iii": 'Sichuan Yi', "ijo": 'Ijo languages', "iku": 'Inuktitut', "ile": 'Interlingue', "ilo": 'Iloko',
    "ina": 'Interlingua', "inc": 'Indic languages', "ind": 'Indonesian', "ine": 'Indo-European languages',
    "inh": 'Ingush', "ipk": 'Inupiaq', "ira": 'Iranian languages', "iro": 'Iroquoian languages', "ita": 'Italian',
    "jav": 'Javanese', "jbo": 'Lojban', "jpn": 'Japanese', "jpr": 'Judeo-Persian', "jrb": 'Judeo-Arabic',
    "kaa": 'Kara-Kalpak', "kab": 'Kabyle', "kac": 'Kachin', "kal": 'Kalaallisut', "kam": 'Kamba', "kan": 'Kannada',
    "kar": 'Karen languages', "kas": 'Kashmiri', "kau": 'Kanuri', "kaw": 'Kawi', "kaz": 'Kazakh', "kbd": 'Kabardian',
    "kha": 'Khasi', "khi": 'Khoisan languages', "khm": 'Central Khmer', "kho": 'Khotanese', "kik": 'Kikuyu',
    "kin": 'Kinyarwanda', "kir": 'Kirghiz', "kmb": 'Kimbundu', "kok": 'Konkani', "kom": 'Komi', "kon": 'Kongo',
    "kor": 'Korean', "kos": 'Kosraean', "kpe": 'Kpelle', "krc": 'Karachay-Balkar', "krl": 'Karelian',
    "kro": 'Kru languages', "kru": 'Kurukh', "kua": 'Kuanyama', "kum": 'Kumyk', "kur": 'Kurdish', "kut": 'Kutenai',
    "lad": 'Ladino', "lah": 'Lahnda', "lam": 'Lamba', "lao": 'Lao', "lat": 'Latin', "lav": 'Latvian',
    "lez": 'Lezghian', "lim": 'Limburgan', "lin": 'Lingala', "lit": 'Lithuanian', "lol": 'Mongo', "loz": 'Lozi',
    "ltz": 'Luxembourgish', "lua": 'Luba-Lulua', "lub": 'Luba-Katanga', "lug": 'Ganda', "lui": 'Luiseno',
    "lun": 'Lunda', "luo": 'Luo', "lus": 'Lushai', "mac": 'Macedonian', "mad": 'Madurese', "mag": 'Magahi',
    "mah": 'Marshallese', "mai": 'Maithili', "mak": 'Makasar', "mal": 'Malayalam', "man": 'Mandingo', "mao": 'Maori',
    "map": 'Austronesian languages', "mar": 'Marathi', "mas": 'Masai', "may": 'Malay', "mdf": 'Moksha',
    "mdr": 'Mandar', "men": 'Mende', "mga": 'Irish, Middle', "mic": "Mi'kmaq", "min": 'Minangkabau',
    "mis": 'Uncoded languages', "mkh": 'Mon-Khmer languages', "mlg": 'Malagasy', "mlt": 'Maltese', "mnc": 'Manchu',
    "mni": 'Manipuri', "mno": 'Manobo languages', "moh": 'Mohawk', "mon": 'Mongolian', "mos": 'Mossi',
    "mul": 'Multiple languages', "mun": 'Munda languages', "mus": 'Creek', "mwl": 'Mirandese', "mwr": 'Marwari',
    "myn": 'Mayan languages', "myv": 'Erzya', "nah": 'Nahuatl languages', "nai": 'North American Indian languages',
    "nap": 'Neapolitan', "nau": 'Nauru', "nav": 'Navajo', "nbl": 'Ndebele, South', "nde": 'Ndebele, North',
    "ndo": 'Ndonga', "nds": 'Low German', "nep": 'Nepali', "nia": 'Nias', "nic": 'Niger-Kordofanian languages',
    "niu": 'Niuean', "nno": 'Norwegian Nynorsk', "nob": 'Norwegian Bokmål', "nog": 'Nogai', "non": 'Norse, Old',
    "nor": 'Norwegian', "nqo": "N'Ko", "nso": 'Pedi', "nub": 'Nubian languages', "nwc": 'Classical Newari',
    "nya": 'Chichewa', "nym": 'Nyamwezi', "nyn": 'Nyankole', "nyo": 'Nyoro', "nzi": 'Nzima', "oci": 'Occitan',
    "oji": 'Ojibwa', "ori": 'Oriya', "orm": 'Oromo', "osa": 'Osage', "oss": 'Ossetian', "ota": 'Turkish, Ottoman',
    "oto": 'Otomian languages', "paa": 'Papuan languages', "pag": 'Pangasinan', "pal": 'Pahlavi', "pam": 'Pampanga',
    "pan": 'Panjabi', "pap": 'Papiamento', "pau": 'Palauan', "peo": 'Persian, Old', "per": 'Persian',
    "phi": 'Philippine languages', "phn": 'Phoenician', "pli": 'Pali', "pol": 'Polish', "pon": 'Pohnpeian',
    "por": 'Portuguese', "pra": 'Prakrit languages', "pro": 'Provençal, Old', "pus": 'Pushto', "que": 'Quechua',
    "raj": 'Rajasthani', "rap": 'Rapanui', "rar": 'Rarotongan', "roa": 'Romance languages', "roh": 'Romansh',
    "rom": 'Romany', "rum": 'Romanian', "run": 'Rundi', "rup": 'Aromanian', "rus": 'Russian', "sad": 'Sandawe',
    "sag": 'Sango', "sah": 'Yakut', "sai": 'South American Indian languages', "sal": 'Salishan languages',
    "sam": 'Samaritan Aramaic', "san": 'Sanskrit', "sas": 'Sasak', "sat": 'Santali', "scn": 'Sicilian',
    "sco": 'Scots', "sel": 'Selkup', "sem": 'Semitic languages', "sga": 'Irish, Old', "sgn": 'Sign Languages',
    "shn": 'Shan', "sid": 'Sidamo', "sin": 'Sinhala', "sio": 'Siouan languages', "sit": 'Sino-Tibetan languages',
    "sla": 'Slavic languages', "slo": 'Slovak', "slv": 'Slovenian', "sma": 'Southern Sami', "sme": 'Northern Sami',
    "smi": 'Sami languages', "smj": 'Lule Sami', "smn": 'Inari Sami', "smo": 'Samoan', "sms": 'Skolt Sami',
    "sna": 'Shona', "snd": 'Sindhi', "snk": 'Soninke', "sog": 'Sogdian', "som": 'Somali', "son": 'Songhai languages',
    "sot": 'Sotho, Southern', "spa": 'Spanish', "srd": 'Sardinian', "srn": 'Sranan Tongo', "srp": 'Serbian',
    "srr": 'Serer', "ssa": 'Nilo-Saharan languages', "ssw": 'Swati', "suk": 'Sukuma', "sun": 'Sundanese',
    "sus": 'Susu', "sux": 'Sumerian', "swa": 'Swahili', "swe": 'Swedish', "syc": 'Classical Syriac', "syr": 'Syriac',
    "tah": 'Tahitian', "tai": 'Tai languages', "tam": 'Tamil', "tat": 'Tatar', "tel": 'Telugu', "tem": 'Timne',
    "ter": 'Tereno', "tet": 'Tetum', "tgk": 'Tajik', "tgl": 'Tagalog', "tha": 'Thai', "tib": 'Tibetan',
    "tig": 'Tigre', "tir": 'Tigrinya', "tiv": 'Tiv', "tkl": 'Tokelau', "tlh": 'Klingon', "tli": 'Tlingit',
    "tmh": 'Tamashek', "tog": 'Tonga (Nyasa)', "ton": 'Tonga (Tonga Islands)', "tpi": 'Tok Pisin',
    "tsi": 'Tsimshian', "tsn": 'Tswana', "tso": 'Tsonga', "tuk": 'Turkmen', "tum": 'Tumbuka',
    "tup": 'Tupi languages', "tur": 'Turkish', "tut": 'Altaic languages', "tvl": 'Tuvalu', "twi": 'Twi',
    "tyv": 'Tuvinian', "udm": 'Udmurt', "uga": 'Ugaritic', "uig": 'Uighur', "ukr": 'Ukrainian', "umb": 'Umbundu',
    "und": 'Undetermined', "urd": 'Urdu', "uzb": 'Uzbek', "vai": 'Vai', "ven": 'Venda', "vie": 'Vietnamese',
    "vol": 'Volapük', "vot": 'Votic', "wak": 'Wakashan languages', "wal": 'Wolaitta', "war": 'Waray', "was": 'Washo',
    "wel": 'Welsh', "wen": 'Sorbian languages', "wln": 'Walloon', "wol": 'Wolof', "xal": 'Kalmyk', "xho": 'Xhosa',
    "yao": 'Yao', "yap": 'Yapese', "yid": 'Yiddish', "yor": 'Yoruba', "ypk": 'Yupik languages', "zap": 'Zapotec',
    "zbl": 'Blissymbols', "zen": 'Zenaga', "zgh": 'Standard Moroccan Tamazight', "zha": 'Zhuang',
    "znd": 'Zande languages', "zul": 'Zulu', "zun": 'Zuni', "zxx": 'No linguistic content', "zza": 'Zaza',
}
AARU_LANGUAGES = set(LANGUAGES)


class Quit(Exception):
    pass


def unique(items):
    seen, result = set(), []
    for item in items:
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result


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
    """"EAN13 8436...; ISBN 84-..." or bare codes (spaces and dashes allowed), several separated by ";" or ",". Bare codes
    are told apart by length: 13 digits are an EAN-13, 12 an UPC-A, 8 an EAN-8 and 10 (the last may be X) an ISBN-10.
    Aaru has no UPC-A type, but an UPC-A is the EAN-13 with a leading 0 (same check digit), so it is stored as that.
    A 978/979 EAN-13 is also the ISBN-13 of the product, but it stays an EAN-13 unless written as "ISBN ...", so the
    printed barcode and the ISBN (often the ISBN-10) can both be stored. ISBNs keep their dashes as written.
    Returns (barcodes, error)."""
    barcodes = []
    for part in filter(None, (p.strip() for p in re.split(r"[;,]", text))):
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


def barcode_in(group):
    """The barcode a part of a name is, as it would be typed ("ISBN 84-...", or the EAN-13/UPC-A digits), or None.
    EAN-8 are left out: too short to tell from a part number."""
    group = group.strip().upper()
    digits = group.replace("-", "").replace(" ", "")
    if re.fullmatch(r"[\d -]+X?", group) and len(digits) == 10 and isbn_valid(digits):
        return f"ISBN {group}"
    if re.fullmatch(r"[\d -]+", group) and len(digits) in (12, 13) and ean_valid(digits):
        return f"ISBN {group}" if len(digits) == 13 and digits.startswith(("978", "979")) and "-" in group \
            else digits
    return None


def folder_barcodes(folder_name):
    """Barcodes and ISBNs used as the product code in a folder name, e.g. "Aquanox (84-9738-024-X)"."""
    return unique(b for b in map(barcode_in, re.findall(r"[(\[]([^)\]]*)[)\]]", folder_name)) if b)


def iso_date(date):
    return date.strftime("%Y-%m-%dT00:00:00")


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


def media_list(meta):
    return [(key, m) for key in MEDIA_KEYS for m in meta.get(key) or []]


def image_name(media):
    image = media.get("Image")
    return (image.get("Value") if isinstance(image, dict) else image) or ""


def part_numbers_in(name):
    """What is in parentheses or brackets in a name and looks like a part number: it has a digit (unlike "Codegame"
    or "PC Plus"), is not a disc number ("CD 1", "Disc 2") and is not a barcode or ISBN."""
    found = []
    for group in re.findall(r"[(\[]([^)\]]*)[)\]]", name):
        group = group.strip()
        if (not re.search(r"\d", group)
                or re.fullmatch(r"(?i)(cd|dvd|bd|gd|disc|disco|disk|disque|cara|side)[\s-]*\w{1,2}|\d{1,2}", group)
                or barcode_in(group)):
            continue
        if group not in found:
            found.append(group)
    return found


def part_candidates(media):
    """Possible part numbers of a disc, from its image name. Returns (where, value) pairs."""
    stem = re.sub(r"(\.compressed)?\.aif$", "", image_name(media), flags=re.IGNORECASE)
    return [("image name", p) for p in part_numbers_in(stem)]


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


def human_size(size):
    if not size:
        return ""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def load(path):
    if not path.exists():
        return {"AaruMetadata": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("AaruMetadata"), dict):
        raise ValueError("not an Aaru metadata file (no AaruMetadata)")
    return data


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


def fail(message):
    console.print(f"[bold red]✖[/bold red] {message}", style="red")
    sys.exit(1)
