import os
import re
from difflib import SequenceMatcher

import httpx

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"


def _request(path: str, params: dict | None = None) -> dict:
    key = os.getenv("TMDB_API_KEY")
    if not key:
        raise RuntimeError("TMDB_API_KEY is missing in the .env file.")
    params = dict(params or {})
    headers = {}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
    resp = httpx.get(f"{BASE}{path}", params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _name_score(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(overlap, SequenceMatcher(None, a, b).ratio())


def find_titles(title: str, year: str, media_type: str) -> list[dict]:
    data = _request("/search/multi", {"query": title, "include_adult": "false"})
    candidates = [r for r in data.get("results", []) if r.get("media_type") in ("movie", "tv")]

    def score(r):
        name = r.get("title") or r.get("name") or ""
        s = _name_score(title, name)
        date = r.get("release_date") or r.get("first_air_date") or ""
        if year and date[:4] == str(year):
            s += 0.1
        if media_type and r.get("media_type") == media_type:
            s += 0.1
        s += min(float(r.get("popularity") or 0) / 500, 0.2)
        return s

    ranked = sorted(candidates, key=score, reverse=True)
    return [r for r in ranked if _name_score(title, r.get("title") or r.get("name") or "") >= 0.7][:4]


def find_actor(media: dict, character: str) -> dict | None:
    mid, mtype = media["id"], media["media_type"]
    if mtype == "tv":
        data = _request(f"/tv/{mid}/aggregate_credits")
        entries = []
        for person in data.get("cast", []):
            for role in person.get("roles", []):
                entries.append((role.get("character", ""), person))
    else:
        data = _request(f"/movie/{mid}/credits")
        entries = [(p.get("character", ""), p) for p in data.get("cast", [])]

    best, best_score = None, 0.0
    for char_name, person in entries:
        s = _name_score(character, char_name)
        if s > best_score:
            best, best_score = person, s
    if best and best_score >= 0.7:
        return best
    return None


def enrich(title: str, year: str, media_type: str, character: str) -> dict:
    out = {"title_found": False, "character_found": False, "image": None,
           "image_kind": None, "actor": None, "tmdb_url": None, "official_title": None}
    candidates = find_titles(title, year, media_type)
    if not candidates:
        return out
    media, actor = candidates[0], None
    for cand in candidates:
        found = find_actor(cand, character)
        if found:
            media, actor = cand, found
            break
    out["title_found"] = True
    out["official_title"] = media.get("title") or media.get("name")
    out["tmdb_url"] = f"https://www.themoviedb.org/{media['media_type']}/{media['id']}"

    if actor and actor.get("profile_path"):
        out["character_found"] = True
        out["actor"] = actor.get("name")
        out["image"] = f"{IMG}/w780{actor['profile_path']}"
        out["image_kind"] = "actor"
    elif actor:
        out["character_found"] = True
        out["actor"] = actor.get("name")

    if not out["image"] and media.get("poster_path"):
        out["image"] = f"{IMG}/w780{media['poster_path']}"
        out["image_kind"] = "poster"
    return out
