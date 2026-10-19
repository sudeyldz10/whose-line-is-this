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


def pick_questions(total: int = TOTAL, seen: set[int] | None = None, info: dict | None = None) -> list[dict]:
    seen = seen or set()
    order = [i for i in range(len(LINES)) if i not in seen]
    if len(order) < total * 2:
        order = list(range(len(LINES)))
        if info is not None:
            info["reset"] = True
    random.shuffle(order)

    chosen, groups = [], set()
    done = 0
    for level, count in MIX:
        done += count
        for i in order:
            if len(chosen) >= done:
                break
            if LINES[i]["level"] != level or LINES[i]["group"] in groups or i in chosen:
                continue
            groups.add(LINES[i]["group"])
            chosen.append(i)
    for i in order:
        if len(chosen) >= total:
            break
        if i in chosen or LINES[i]["group"] in groups:
            continue
        groups.add(LINES[i]["group"])
        chosen.append(i)
    random.shuffle(chosen)

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
