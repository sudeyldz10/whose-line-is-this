import base64
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import cache, llm, search, tmdb  # noqa: E402

app = FastAPI(title="Whose Line Is This?")

MIN_CONFIDENCE = 0.45


class GuessRequest(BaseModel):
    text: str
    search_query: str | None = None


class TranscribeRequest(BaseModel):
    audio: str
    mime: str = "audio/wav"


MAX_AUDIO_BYTES = 2_000_000
ALLOWED_AUDIO = {"audio/wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/flac", "audio/aac"}


def compute_confidence(analysis: dict, info: dict) -> float:
    try:
        conf = float(analysis.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(conf, 1.0))
    if len(analysis.get("supporting_indices") or []) >= 2:
        conf += 0.08
    if info["title_found"]:
        conf += 0.05
        if info["character_found"]:
            conf += 0.07
    else:
        conf *= 0.7
    return round(min(conf, 0.97), 2)


def label(conf: float) -> str:
    if conf >= 0.8:
        return "High"
    if conf >= 0.6:
        return "Medium"
    return "Low"


@app.post("/api/transcribe")
def transcribe(req: TranscribeRequest):
    if req.mime not in ALLOWED_AUDIO:
        raise HTTPException(400, "Unsupported audio format.")
    if len(req.audio) > MAX_AUDIO_BYTES * 4 // 3 + 8:
        raise HTTPException(413, "The recording is too long.")
    try:
        audio = base64.b64decode(req.audio, validate=True)
    except Exception:
        raise HTTPException(400, "The audio could not be read.")
    if not audio:
        raise HTTPException(400, "The audio could not be read.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "The recording is too long.")

    try:
        data = llm.transcribe(audio, req.mime)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(502, f"External service error: {type(e).__name__}")

    transcript = (data.get("transcript") or "").strip()
    if not transcript:
        return {"transcript": ""}
    quote = (data.get("cleaned_quote") or transcript).strip()
    return {
        "transcript": transcript[:400],
        "language": data.get("language") or "",
        "quote": quote[:400],
        "search_query": (data.get("search_query") or "").strip()[:200],
    }


@app.post("/api/guess")
def guess(req: GuessRequest):
    transcript = req.text.strip()
    if len(transcript) < 3:
        raise HTTPException(400, "The line is too short.")
    if len(transcript) > 400:
        transcript = transcript[:400]

    cached = cache.get(transcript)
    if cached:
        return {**cached, "from_cache": True}

    try:
        prep = llm.prepare_query(transcript)
        print("HEARD:", transcript, "| QUERY:", prep["search_query"])
        results = search.web_search(prep["search_query"])
        print("RESULTS:", [r["title"] for r in results])
        if not results:
            return {"found": False, "reason": "No search results."}

        analysis = llm.analyze_results(prep["cleaned_quote"], results)
        print("ANALYSIS:", analysis)
        if not analysis.get("found") or not analysis.get("character") or not analysis.get("title"):
            return {"found": False, "reason": "The line could not be matched to a reliable source."}

        info = tmdb.enrich(
            analysis["title"],
            str(analysis.get("year") or ""),
            analysis.get("media_type") or "",
            analysis["character"],
        )
    except RuntimeError as e:
        print("GUESS ERROR:", repr(e))
        raise HTTPException(500, str(e))
    except Exception as e:
        print("GUESS ERROR:", repr(e))
        raise HTTPException(502, f"External service error: {type(e).__name__}")

    conf = compute_confidence(analysis, info)
    if conf < MIN_CONFIDENCE:
        return {"found": False, "reason": "Not confident enough in the match."}

    idx = analysis.get("source_index")
    src = results[idx] if isinstance(idx, int) and 0 <= idx < len(results) else results[0]

    payload = {
        "found": True,
        "character": analysis["character"],
        "title": info["official_title"] or analysis["title"],
        "year": analysis.get("year") or "",
        "quote": prep["cleaned_quote"],
        "heard": transcript,
        "image": info["image"],
        "image_kind": info["image_kind"],
        "actor": info["actor"],
        "source_title": src["title"],
        "source_url": src["url"],
        "tmdb_url": info["tmdb_url"],
        "confidence": conf,
        "confidence_label": label(conf),
        "note": analysis.get("note", ""),
    }
    cache.set(transcript, payload)
    return {**payload, "from_cache": False}


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
