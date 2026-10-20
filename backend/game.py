import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/game")

from .game_data import DECOYS, LINES

TOTAL = 5
WIN_SCORE = 5
SECONDS = 10
MIX = (("easy", 2), ("medium", 2), ("hard", 1))


class CheckRequest(BaseModel):
    id: int
    choice: str | None = None


def parse_seen(raw: str) -> set[int]:
    seen = set()
    for part in raw.split(",")[:1500]:
        if part.strip().isdigit():
            seen.add(int(part))
    return seen


TURKISH_PER_GAME = 2


def pick_questions(total: int = TOTAL, seen: set[int] | None = None, info: dict | None = None) -> list[dict]:
    seen = seen or set()
    levels = [level for level, count in MIX for _ in range(count)][:total]
    tr_slots = set(random.sample(range(total), min(TURKISH_PER_GAME, total)))

    def pool(lang: str) -> list[int]:
        every = [i for i in range(len(LINES)) if (LINES[i].get("lang", "en") == "tr") == (lang == "tr")]
        fresh = [i for i in every if i not in seen]
        if len(fresh) < (total - TURKISH_PER_GAME if lang == "en" else TURKISH_PER_GAME) * 2:
            if lang == "en" and info is not None:
                info["reset"] = True
            fresh = every
        random.shuffle(fresh)
        return fresh

    pools = {"tr": pool("tr"), "en": pool("en")}
    chosen: list[int | None] = [None] * total
    groups: set[str] = set()
    for slot in sorted(range(total), key=lambda k: k not in tr_slots):
        lang = "tr" if slot in tr_slots else "en"
        for level_match in (True, False):
            for i in pools[lang]:
                if i in chosen or LINES[i]["group"] in groups:
                    continue
                if level_match and LINES[i]["level"] != levels[slot]:
                    continue
                groups.add(LINES[i]["group"])
                chosen[slot] = i
                break
            if chosen[slot] is not None:
                break
    chosen = [i for i in chosen if i is not None]
    random.shuffle(chosen)

    people = [(d["character"], d["group"], d.get("lang", "en")) for d in LINES] + [(d["name"], d["group"], d.get("lang", "en")) for d in DECOYS]
    questions = []
    for i in chosen:
        item = LINES[i]
        lang = item.get("lang", "en")
        pool = sorted({name for name, group, lg in people if lg == lang and group != item["group"] and name != item["character"]})
        names = random.sample(pool, 3) + [item["character"]]
        random.shuffle(names)
        questions.append({"id": i, "line": item["line"], "options": names})
    return questions


@router.get("/new")
def new_game(seen: str = ""):
    info: dict = {}
    questions = pick_questions(TOTAL, parse_seen(seen), info)
    return {"total": TOTAL, "win_score": WIN_SCORE, "seconds": SECONDS, "questions": questions, "reset": bool(info.get("reset"))}


@router.post("/check")
def check(req: CheckRequest):
    if not 0 <= req.id < len(LINES):
        raise HTTPException(404, "Unknown question.")
    item = LINES[req.id]
    return {
        "correct": req.choice == item["character"],
        "character": item["character"],
        "title": item["title"],
        "year": item["year"],
    }
