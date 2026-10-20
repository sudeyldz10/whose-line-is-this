import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.song import slug  # noqa: E402
from backend.song_data import SONGS  # noqa: E402

OUT = ROOT / "backend" / "song_clips.py"
PAUSE = 3.2


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def search(song: dict) -> str | None:
    term = urllib.parse.quote_plus(f"{song['title']} {song['artist']}")
    url = f"https://itunes.apple.com/search?term={term}&media=music&entity=song&limit=10"
    with urllib.request.urlopen(url, timeout=20) as resp:
        results = json.load(resp).get("results", [])
    want_title = norm(song["title"])
    want_artist = norm(song["artist"]).split()
    for item in results:
        title = norm(item.get("trackName", ""))
        artist = norm(item.get("artistName", ""))
        if not item.get("previewUrl"):
            continue
        if want_title.split()[0] not in title.split():
            continue
        if any(word in artist for word in want_artist if len(word) > 3):
            return item["previewUrl"]
    return None


def load_existing() -> dict:
    if not OUT.exists():
        return {}
    scope: dict = {}
    exec(OUT.read_text(encoding="utf-8"), scope)
    return dict(scope.get("CLIPS", {}))


def save(clips: dict) -> None:
    lines = ["CLIPS = {"]
    for key in sorted(clips):
        lines.append(f"    {key!r}: {clips[key]!r},")
    lines.append("}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    clips = load_existing()
    missing = []
    for n, song in enumerate(SONGS, 1):
        key = slug(song["title"], song["artist"])
        if key in clips:
            continue
        try:
            url = search(song)
        except Exception as e:
            print(f"[{n}/{len(SONGS)}] error {song['title']}: {e}")
            url = None
            time.sleep(10)
        if url:
            clips[key] = url
            save(clips)
            print(f"[{n}/{len(SONGS)}] ok   {song['title']} - {song['artist']}")
        else:
            missing.append(f"{song['title']} - {song['artist']}")
            print(f"[{n}/{len(SONGS)}] none {song['title']} - {song['artist']}")
        time.sleep(PAUSE)
    save(clips)
    print(f"\nDone: {len(clips)} clips, {len(missing)} not found")


if __name__ == "__main__":
    main()
