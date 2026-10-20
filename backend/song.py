import random
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .song_data import SONGS

try:
    from .song_clips import CLIPS
except ImportError:
    CLIPS = {}

router = APIRouter(prefix="/api/song")

TOTAL = 5
WIN_SCORE = 5
LISTEN_MS = 3000
THINK_SECONDS = 7
PREVIEW_SECONDS = 30
MIX = (("easy", 2), ("medium", 2), ("hard", 1))

CLIP_DIR = Path(__file__).resolve().parent.parent / "frontend" / "clips"
EXTENSIONS = (".mp3", ".m4a", ".ogg")


class CheckRequest(BaseModel):
    id: int
    choice: str | None = Field(default=None, max_length=200)


def slug(title: str, artist: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{title} {artist}".lower()).strip("-")


def label(song: dict) -> str:
    return f"{song['title']} — {song['artist']}"


def local_clip(song: dict) -> str | None:
    base = slug(song["title"], song["artist"])
    for ext in EXTENSIONS:
        if (CLIP_DIR / (base + ext)).is_file():
            return f"/clips/{base}{ext}"
    return None


def clip_for(song: dict) -> str | None:
    return local_clip(song) or CLIPS.get(slug(song["title"], song["artist"]))


def playable() -> list[int]:
    return [i for i, s in enumerate(SONGS) if clip_for(s)]


def parse_seen(raw: str) -> set[int]:
    seen = set()
    for part in raw.split(",")[:1500]:
        if part.strip().isdigit():
            seen.add(int(part))
    return seen


TURKISH_ARTISTS = {
    "Duman", "Gripin", "Gülşen", "Hadise", "Hande Yener", "Kayahan", "Kenan Doğulu", "Mabel Matiz",
    "Mor ve Ötesi", "Murat Boz", "Mustafa Sandal", "Sertab Erener", "Sezen Aksu", "Tarkan", "Teoman",
}
TURKISH_PER_GAME = 2


def lang_of(song: dict) -> str:
    return "tr" if song["artist"] in TURKISH_ARTISTS else "en"


def pick_songs(total: int, seen: set[int], info: dict | None = None) -> list[int]:
    pool = playable()
    pools = {}
    for lang in ("tr", "en"):
        full = [i for i in pool if lang_of(SONGS[i]) == lang]
        fresh = [i for i in full if i not in seen]
        need = TURKISH_PER_GAME * 2 if lang == "tr" else (total - TURKISH_PER_GAME) * 2
        if len(fresh) < need:
            fresh = full
            if info is not None:
                info["reset"] = True
        random.shuffle(fresh)
        pools[lang] = (fresh, full)

    slots = [level for level, count in MIX for _ in range(count)]
    random.shuffle(slots)
    langs = ["tr"] * min(TURKISH_PER_GAME, len(pools["tr"][1])) + ["en"] * total
    langs = langs[:total]
    chosen, artists = [], set()
    for level, lang in zip(slots, langs):
        fresh, full = pools[lang]
        for source in (
            [i for i in fresh if SONGS[i]["level"] == level],
            fresh,
            [i for i in full if SONGS[i]["level"] == level],
            full,
        ):
            pick = next((i for i in source if i not in chosen and SONGS[i]["artist"] not in artists), None)
            if pick is not None:
                chosen.append(pick)
                artists.add(SONGS[pick]["artist"])
                break
    random.shuffle(chosen)
    return chosen


def options_for(index: int) -> list[str]:
    item = SONGS[index]
    right = label(item)
    lang = lang_of(item)
    others = [s for s in SONGS if s["artist"] != item["artist"] and label(s) != right and lang_of(s) == lang]
    same = [label(s) for s in others if s["level"] == item["level"]]
    rest = [label(s) for s in others if s["level"] != item["level"]]
    names = random.sample(same, 2) if len(same) >= 2 else same[:]
    extra = [n for n in rest + same if n not in names]
    names += random.sample(extra, min(3 - len(names), len(extra)))
    names.append(right)
    random.shuffle(names)
    return names


@router.get("/ready")
def ready():
    return {"ready": len(playable()) >= TOTAL * 2}


@router.get("/new")
def new_game(seen: str = ""):
    if len(playable()) < TOTAL:
        raise HTTPException(503, "Song Edition is not ready yet. Try Guess the line!")
    info: dict = {}
    picked = pick_songs(TOTAL, parse_seen(seen), info)
    questions = []
    for i in picked:
        latest = PREVIEW_SECONDS - LISTEN_MS / 1000 - 1
        start = round(random.uniform(1.5, latest), 1)
        questions.append({"id": i, "clip": clip_for(SONGS[i]), "start": start, "options": options_for(i)})
    return {
        "total": TOTAL,
        "win_score": WIN_SCORE,
        "listen_ms": LISTEN_MS,
        "think_seconds": THINK_SECONDS,
        "questions": questions,
        "reset": bool(info.get("reset")),
    }


@router.post("/check")
def check(req: CheckRequest):
    if not 0 <= req.id < len(SONGS):
        raise HTTPException(404, "Unknown question.")
    item = SONGS[req.id]
    return {"correct": req.choice == label(item), "answer": label(item), "year": item["year"]}
