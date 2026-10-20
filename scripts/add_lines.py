import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import game_data  # noqa: E402

LEVELS = {"e": "easy", "m": "medium", "h": "hard"}
LANGS = {"tr": "tr", "en": "en"}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text)


def main(path: str, lang: str) -> None:
    lines = list(game_data.LINES)
    decoys = list(game_data.DECOYS)
    have = {d["line"].strip().lower() for d in lines}
    added = 0
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 5 or parts[4].lower() not in LEVELS or not all(parts):
            print(f"line {number} skipped (format: line | character | title | year | e/m/h): {raw[:60]}")
            continue
        line, character, title, year, level = parts
        if line.lower() in have:
            print(f"line {number} already exists: {line[:50]}")
            continue
        have.add(line.lower())
        lines.append({"line": line, "character": character, "title": title, "year": year,
                      "group": slug(title), "level": LEVELS[level.lower()], "lang": LANGS[lang]})
        added += 1
    with open(ROOT / "backend" / "game_data.py", "w", encoding="utf-8") as f:
        f.write("LINES = [\n")
        for d in lines:
            f.write("    " + repr(d) + ",\n")
        f.write("]\n\nDECOYS = [\n")
        for d in decoys:
            f.write("    " + repr(d) + ",\n")
        f.write("]\n")
    print(f"{added} lines added, {len(lines)} in total")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/add_lines.py lines.txt [tr|en]")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "tr")
