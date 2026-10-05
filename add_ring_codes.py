#!/usr/bin/env python3
"""Interactively add ring codes, mastering SIDs, toolstamps, mould SIDs and mould texts to the optical discs
described in the Aaru metadata.json of the current directory.

For every optical disc, the image name is shown and the five codes are asked in order:
  - Enter on an empty answer keeps the current value if there is one, otherwise leaves the field empty.
  - "-" clears the current value.
  - Anything else is stored as the new value; a literal \\n in it separates lines (e.g. "MADE IN USA\\nSONY DADC").

With --layers, the number of layers of each disc is asked first (defaulting to the layers the metadata knows of),
and then every code is asked once per layer (L0, L1...), stored with its layer number.

A backup (metadata.json.bak) is written before the file is modified for the first time.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

try:
    import readline  # noqa: F401  (line editing and history for input())
except ImportError:
    pass

FIELDS = (
    ("RingCode", "Ring code"),
    ("MasteringSid", "Mastering SID"),
    ("Toolstamp", "Toolstamp"),
    ("MouldSid", "Mould SID"),
    ("MouldText", "Mould text"),
)
LABEL_WIDTH = max(len(label) for _, label in FIELDS)

USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def style(text, *codes):
    if not USE_COLOR:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def bold(t):
    return style(t, "1")


def dim(t):
    return style(t, "2")


def red(t):
    return style(t, "1", "31")


def green(t):
    return style(t, "1", "32")


def yellow(t):
    return style(t, "1", "33")


def magenta(t):
    return style(t, "1", "35")


def cyan(t):
    return style(t, "36")


def prompt_style(t):
    # input() prompts need the escapes wrapped so readline computes the visible width correctly
    if not USE_COLOR:
        return t
    out = []
    i = 0
    while i < len(t):
        if t[i] == "\033":
            end = t.index("m", i) + 1
            out.append("\001" + t[i:end] + "\002")
            i = end
        else:
            out.append(t[i])
            i += 1
    return "".join(out)


def terminal_width():
    return min(shutil.get_terminal_size((80, 24)).columns, 100)


def banner(path, count):
    width = terminal_width() - 2
    title = " 💿  Disc mastering codes "
    discs = f"  ·  {count} optical disc{'s' if count != 1 else ''} "
    where = str(path)
    room = width - len(discs) - 1
    if len(where) > room:  # keep the end of the path, it names the dump
        where = "…" + where[-(room - 1):]
    info = " " + where + discs
    print(cyan("╭" + "─" * width + "╮"))
    print(cyan("│") + bold(title.ljust(width - 1)) + cyan("│"))
    print(cyan("│") + dim(info[:width].ljust(width)) + cyan("│"))
    print(cyan("╰" + "─" * width + "╯"))
    print(dim("  Enter keeps the current value (or leaves it empty) · ") + yellow("-") +
          dim(" clears it · Ctrl+C aborts without saving"))


def disc_header(index, count, disc):
    name = (disc.get("Image") or {}).get("Value") or f"Disc {index}"
    print()
    print(magenta(f"◆ Disc {index}/{count}") + dim("  ·  ") + bold(name))
    print(dim("─" * terminal_width()))


def shown(text):
    """Text as typed, with line separators back as \\n."""
    return text.replace("\n", "\\n")


def typed(answer):
    """Text to store from an answer, where a literal \\n separates lines."""
    return "\n".join(line.strip() for line in answer.split("\\n"))


def current_text(values):
    if not values:
        return None
    texts = [shown(v["Text"]) for v in values if v.get("Text")]
    return " / ".join(texts) if texts else None


def ask(label, current, width=LABEL_WIDTH):
    hint = f" [{current}]" if current else ""
    text = cyan("  › ") + bold(label.ljust(width)) + dim(hint) + cyan(" : ")
    return input(prompt_style(text)).strip()


def print_summary(summary, width=LABEL_WIDTH):
    print()
    for label, value in summary:
        mark = green("  ✔ ") if value else dim("  · ")
        print(mark + label.ljust(width) + "  " + (bold(value) if value else dim("none")))


def process_disc(disc):
    """Ask the codes of one disc, returning True if the disc was modified."""
    changed = False
    summary = []

    for key, label in FIELDS:
        old = disc.get(key)
        current = current_text(old)
        answer = ask(label, current)

        if answer == "-":
            if key in disc:
                del disc[key]
                changed = True
            summary.append((label, None))
        elif answer:
            new = [{"Text": typed(answer)}]
            if old != new:
                disc[key] = new
                changed = True
            summary.append((label, shown(typed(answer))))
        else:
            summary.append((label, current))

    print_summary(summary)

    return changed


def default_layer_count(disc):
    sectors = (disc.get("Layers") or {}).get("Sectors") or []
    known = [v.get("Layer") for key, _ in FIELDS for v in disc.get(key) or [] if v.get("Layer") is not None]
    return max(len(sectors), max(known, default=-1) + 1, 1)


def ask_layer_count(disc):
    default = default_layer_count(disc)
    while True:
        answer = ask("Layers", str(default))
        if not answer:
            return default
        if answer.isdigit() and int(answer) >= 1:
            return int(answer)
        print(red("    ✖ ") + "Enter a number of layers, 1 or more")


def process_disc_layers(disc):
    """Ask the codes of one disc layer by layer, returning True if the disc was modified."""
    count = ask_layer_count(disc)
    width = LABEL_WIDTH + len(f" L{count - 1}")
    changed = False
    summary = []

    for key, label in FIELDS:
        old = disc.get(key) or []
        new = [v for v in old if v.get("Layer") is not None and v["Layer"] >= count]  # beyond the asked layers

        for layer in range(count):
            # An entry without a layer applies to the whole disc, so it is offered as layer 0's value
            matches = [v for v in old if v.get("Layer") == layer or (layer == 0 and v.get("Layer") is None)]
            layer_label = f"{label} L{layer}"
            answer = ask(layer_label, current_text(matches), width)

            if answer == "-":
                summary.append((layer_label, None))
            elif answer:
                new.append({"Layer": layer, "Text": typed(answer)})
                summary.append((layer_label, shown(typed(answer))))
            else:
                # With several layers, a kept whole-disc value becomes explicitly layer 0's
                new.extend({"Layer": layer, "Text": v.get("Text")} if count > 1 else v for v in matches)
                summary.append((layer_label, current_text(matches)))

        new.sort(key=lambda v: v.get("Layer") or 0)

        if new != old:
            changed = True
            if new:
                disc[key] = new
            else:
                disc.pop(key, None)

    print_summary(summary, width)

    return changed


def save(path, data):
    backup = path.with_name(path.name + ".bak")
    if not backup.exists():  # never overwrite the original backup on re-runs
        shutil.copy2(path, backup)

    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def fail(message):
    print(red("✖ ") + message, file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--layers", action="store_true",
                        help="ask the number of layers of each disc, then every code once per layer")
    args = parser.parse_args()

    path = Path.cwd() / "metadata.json"

    if not path.is_file():
        fail(f"No metadata.json found in {Path.cwd()}")

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail(f"Cannot read {path}: {e}")

    meta = data.get("AaruMetadata") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        fail(f"{path} is not an Aaru metadata file (no AaruMetadata key)")

    discs = meta.get("OpticalDiscs") or []
    if not discs:
        fail(f"{path} does not describe any optical disc")

    banner(path, len(discs))

    changed = False
    try:
        for index, disc in enumerate(discs, 1):
            disc_header(index, len(discs), disc)
            changed |= process_disc_layers(disc) if args.layers else process_disc(disc)
    except (KeyboardInterrupt, EOFError):
        print()
        print(yellow("⚠ Aborted, nothing saved."))
        sys.exit(130)

    print()
    if not changed:
        print(yellow("● No changes, metadata.json left untouched."))
        return

    try:
        save(path, data)
    except OSError as e:
        fail(f"Cannot write {path}: {e}")

    print(green("✔ Saved ") + bold(str(path)))


if __name__ == "__main__":
    main()
