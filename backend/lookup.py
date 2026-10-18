import re
from difflib import SequenceMatcher

from .game_data import LINES

MIN_WORDS = 3
MIN_RATIO = 0.9


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("'", "")).strip()


_INDEX = [(_norm(item["line"]), item) for item in LINES if len(_norm(item["line"]).split()) >= MIN_WORDS]


def find_line(text: str) -> dict | None:
    heard = _norm(text)
    if not heard:
        return None
    best, best_score = None, 0.0
    for line, item in _INDEX:
        if line in heard and len(line) >= len(heard) * 0.6:
            score = 1.0
        else:
            score = SequenceMatcher(None, heard, line).ratio()
        if score > best_score:
            best, best_score = item, score
    return best if best and best_score >= MIN_RATIO else None


def same_title(a: str, b: str) -> bool:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= 0.8


def fix_speaker(analysis: dict, *texts: str) -> dict:
    for text in texts:
        item = find_line(text)
        if item and same_title(item["title"], str(analysis.get("title") or "")):
            return {**analysis, "character": item["character"]}
    return analysis
