import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/game")

from .game_data import DECOYS, LINES

TOTAL = 5
WIN_SCORE = 5
SECONDS = 30


class CheckRequest(BaseModel):
    id: int
    choice: str | None = None


def parse_seen(raw: str) -> set[int]:
    seen = set()
    for part in raw.split(",")[:200]:
        if part.strip().isdigit():
            seen.add(int(part))
    return seen


def pick_questions(total: int = TOTAL, seen: set[int] | None = None) -> list[dict]:
    seen = seen or set()
    order = [i for i in range(len(LINES)) if i not in seen]
    if len(order) < total * 2:
        order = list(range(len(LINES)))
    random.shuffle(order)

    chosen, groups = [], set()
    for i in order:
        if LINES[i]["group"] in groups:
            continue
        groups.add(LINES[i]["group"])
        chosen.append(i)
        if len(chosen) == total:
            break

    people = [(d["character"], d["group"]) for d in LINES] + [(d["name"], d["group"]) for d in DECOYS]
    questions = []
    for i in chosen:
        item = LINES[i]
        pool = sorted({name for name, group in people if group != item["group"] and name != item["character"]})
        names = random.sample(pool, 3) + [item["character"]]
        random.shuffle(names)
        questions.append({"id": i, "line": item["line"], "options": names})
    return questions


@router.get("/new")
def new_game(seen: str = ""):
    return {"total": TOTAL, "win_score": WIN_SCORE, "seconds": SECONDS, "questions": pick_questions(TOTAL, parse_seen(seen))}


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
