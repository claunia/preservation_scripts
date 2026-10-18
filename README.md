# Preservation scripts

Scripts used to dump optical discs with [Aaru](https://github.com/aaru-dps/Aaru) and to
process the resulting dumps (compression, checking, metadata, scans, folder icons and
recovery files) before archiving them.

Most scripts work on the current folder and everything below it, unless a folder is given.
Scripts that change or delete files usually have a `-n` / `--dry-run` option to see what
they would do first.

Roughly in the order they are used:

## Dumping

| Script | What it does |
|---|---|
| `dump_disc.sh` | Dumps a disc with Aaru. Presets (`-t`) cover the usual cases: `plain`, `paranoia`, `pc`, `ring`, `safedisc`, `retry-safedisc`, `retry-errors`, `movie` and `ngcw`. Options select the drive (`-d sr0`/`sr1`/`sr2`/`morgay`/`khepri`), and turn on or off ProtectionScan, verify, DPM, hyper-speed and skipping the SafeDisc sectors, set the number of retry passes, the sectors never to retry, and retrying in reverse. The settings used are printed before dumping. Run it with `--help` for the full list. The Aaru binary can be changed with the `AARU` environment variable. |
| `scan_sr0.sh`, `scan_sr1.sh`, `scan_sr2.sh` | Mount the disc in that drive read-only, run ProtectionScan on it and save the result as `<name>.protectionscan.json`. |

## Checking and compressing dumps

| Script | What it does |
|---|---|
| `check_dumps.py` | Checks every dump found below a folder and prints `DUMP OK` or `DUMP FAILURE` with the reasons. A dump is OK when the dump log reports 0 unreadable sectors, the verify log (if any) reports 0 errors+unknowns, and the resume file has no bad blocks and reached the last block. Older dump logs do not report unreadable sectors, so the resume file alone decides for them. `-f` only shows failures. |
| `convert.sh` | Compresses every `.aif` in the subfolders (up to 3 levels deep) into `<name>.compressed.aif` and compares it with the original, skipping images that are already compressed. An image that was converted but never compared (no compare log) only gets the compare. Runs several images at once (`-j N`, default 4). |
| `finalize_compressed.py` | For each `<name>.compressed.aif` whose convert and compare (and verify, if present) logs show success, and that `aaru image info` shows as created by the same creator `convert.sh` stamps, replaces `<name>.aif` with it and removes the logs and other leftovers of the conversion. |
| `repair.sh` | One-off: upgrades the DDT of the `.aif` images in the subfolders to the AaruFormat alpha 21 layout using `aaruformattool`. |

## Metadata

| Script | What it does |
|---|---|
| `create_sidecars.sh` | Creates the Aaru `<name>.metadata.json` sidecar for each `.aif` that has none. Folders that already have a `metadata.json` are skipped. |
| `rename_metadata.py` | Renames the single `*.metadata.json` in each folder to `metadata.json`, and lists folders where that is not possible (several sidecars, or a `metadata.json` already there). |
| `merge_metadata.py` | Combines the discs of two or more metadata files into one multi-disc `metadata.json`, renumbering the disc sequence. |
| `add_magazine_metadata.py` | Fills in Name (from the folder name), Publishers, Release (`Coverdisc`) and ReleaseDate (from the month in the folder name, or from the filesystem dates) in the metadata of each subfolder. Meant for magazine coverdiscs. |
| `edit_metadata.py` | Interactively fills in or edits the metadata of each folder field by field, without any online database: name (suggested from the folder name), version (from "Versión 2.0" in the folder name), release type, release date (suggested from the newest file in the discs), part and serial numbers, developers, publishers, authors, performers, keywords and categories (offering common ones and those used before), languages by name (`Spanish; English`), operating systems (`Windows 95[4.00.950]; Windows NT[3.10;3.50]`) and barcodes, plus optionally the part and serial number of each disc. Part numbers, barcodes and ISBNs in parentheses in the folder and image names are suggested. Every prompt shows the format expected, and a summary of the changes allows editing any field again before saving. `--learn FOLDER` learns the vocabulary from existing metadata. |
| `igdb_metadata.py` | Interactively fills in the metadata of game folders from [IGDB](https://www.igdb.com): developers, publishers, name, release date (for the platform of the folder, preferring `--region`), franchises as keywords, genres as subcategories, languages and, for PC, the operating system, and asks for the barcodes of games that have none: EAN-13, UPC-A (stored as its EAN-13), EAN-8 or ISBN, told apart by length and check digit, several separated by `;` (an ISBN in the folder name is pre-filled). It also suggests the part number of the game from what is in parentheses in the folder name, and the part number of each disc from its image name, to pick from, type or leave empty; `d` in the review changes the disc part numbers. The folder name (without parentheses) is searched, and games sharing that name are listed to choose from by year, company or platform. Fields already in the metadata are kept, and every field is shown for confirmation and can be changed before writing. Works on `metadata.json`, or the `*.metadata.json` sidecars when there is none. Needs the `rich` module, `metadata_ui.py` (shared with `edit_metadata.py`) and IGDB credentials in `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` or `igdb_key.json`. `-r` processes every subfolder. |
| `add_ring_codes.py` | Interactively asks for the ring code, mastering SID, toolstamp, mould SID and mould text of each disc in `metadata.json` and stores them, optionally per layer (`--layers`). |

## Scans and presentation

| Script | What it does |
|---|---|
| `make_folder_icons.py` | Creates Windows (`desktop.ini` / `desktop.ico`) and Linux (`.directory` / `.directory.png`) folder icons from the JPEG-XL scans in each folder, preferring `cover.jxl`, then `front.jxl`, `media.jxl`, `media1.jxl` and `up.jxl`. Without a `cover.jxl`, a DVD or Blu-ray sized `inlay.jxl` has its front cover cut out (not kept) and used instead, and it also replaces existing icons that were taken from an `.exe` (no PNG image in `desktop.ico`). A folder with a single scan of another name gets it renamed to `media.jxl`. |
| `mkpdf.sh` | Joins the given images (e.g. manual scans) into an optimized `output.pdf`, encoding each page as whichever of PNG or JPEG 2000 is smaller. |

## Archiving

| Script | What it does |
|---|---|
| `par2_leaves.sh` | Creates PAR2 recovery files (10% redundancy) in every leaf folder, named after the folder, skipping folders that already have them. |
| `sync.sh` | Synchronizes `Dumps (antiguos)` with the copy on hades using unison. |
