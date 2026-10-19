import base64
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging  # noqa: E402

import httpx  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import budget, cache, config, game, llm, lookup, search, security, song, tmdb  # noqa: E402

security.setup_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.check_env()
    yield


app = FastAPI(title="Whose Line Is This?", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(security.GuardMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(game.router)
app.include_router(song.router)

GENERIC_ERROR = "Something went wrong on our side. Please try again."
QUOTA_ERROR = "Find the line is very busy right now. Try Guess the line, or come back a bit later!"
SERVICE_ERROR = "A service we depend on is not responding. Please try again in a moment."


def is_quota_error(e: Exception) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (429, 432, 433)
    return getattr(e, "code", None) == 429


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled error", exc_info=exc, extra={"fields": {"path": request.url.path}})
    return JSONResponse({"detail": GENERIC_ERROR}, status_code=500)


@app.get("/health")
def health():
    checks = {"env": not config.missing_keys(), "database": cache.healthy()}
    ok = all(checks.values())
    return JSONResponse({"status": "ok" if ok else "unhealthy", "checks": checks}, status_code=200 if ok else 503)

MIN_CONFIDENCE = 0.45


class GuessRequest(BaseModel):
    text: str = Field(max_length=2000)
    search_query: str | None = Field(default=None, max_length=500)


class TranscribeRequest(BaseModel):
    audio: str = Field(max_length=4_000_000)
    mime: str = Field(default="audio/wav", max_length=40)


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


def _norm(text: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in text.lower().replace("'", "")).split())


def pick_quote(analysis: dict, results: list[dict], fallback: str) -> tuple[str, bool]:
    official = str(analysis.get("official_quote") or "").strip()
    if len(official.split()) >= 3:
        needle = _norm(official)
        for r in results:
            if needle and needle in _norm(f"{r['title']} {r['content']}"):
                return official, True
    return fallback, False


def label(conf: float) -> str:
    if conf >= 0.8:
        return "High"
    if conf >= 0.6:
        return "Medium"
    return "Low"


@app.post("/api/transcribe")
def transcribe(req: TranscribeRequest, request: Request):
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

    if not budget.take("transcribe", security.client_ip(request)):
        raise HTTPException(503, QUOTA_ERROR)

    try:
        data = llm.transcribe(audio, req.mime)
    except RuntimeError as e:
        log.error("transcribe configuration error", exc_info=e)
        raise HTTPException(500, GENERIC_ERROR)
    except Exception as e:
        log.error("transcribe service error", exc_info=e)
        raise HTTPException(503 if is_quota_error(e) else 502, QUOTA_ERROR if is_quota_error(e) else SERVICE_ERROR)

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
def guess(req: GuessRequest, request: Request):
    transcript = req.text.strip()
    if len(transcript) < 3:
        raise HTTPException(400, "The line is too short.")
    if len(transcript) > 400:
        transcript = transcript[:400]

    cached = cache.get(transcript)
    if cached:
        return {**cached, "from_cache": True}

    if not budget.take("search", security.client_ip(request)):
        raise HTTPException(503, QUOTA_ERROR)

    try:
        query = (req.search_query or "").strip()[:200]
        if len(query) >= 3:
            prep = {"cleaned_quote": transcript, "search_query": query}
        else:
            prep = llm.prepare_query(transcript)
        results = search.web_search(prep["search_query"])
        if not results:
            return {"found": False, "reason": "No search results."}

        analysis = llm.analyze_results(prep["cleaned_quote"], results)
        if not analysis.get("found") or not analysis.get("character") or not analysis.get("title"):
            return {"found": False, "reason": "The line could not be matched to a reliable source."}

        analysis = lookup.fix_speaker(analysis, prep["cleaned_quote"], transcript)

        info = tmdb.enrich(
            analysis["title"],
            str(analysis.get("year") or ""),
            analysis.get("media_type") or "",
            analysis["character"],
        )
    except RuntimeError as e:
        log.error("guess configuration error", exc_info=e)
        raise HTTPException(500, GENERIC_ERROR)
    except Exception as e:
        log.error("guess service error", exc_info=e)
        raise HTTPException(503 if is_quota_error(e) else 502, QUOTA_ERROR if is_quota_error(e) else SERVICE_ERROR)

    conf = compute_confidence(analysis, info)
    if conf < MIN_CONFIDENCE:
        return {"found": False, "reason": "Not confident enough in the match."}

    idx = analysis.get("source_index")
    src = results[idx] if isinstance(idx, int) and 0 <= idx < len(results) else results[0]

    quote, official = pick_quote(analysis, results, prep["cleaned_quote"])

    payload = {
        "found": True,
        "character": analysis["character"],
        "title": info["official_title"] or analysis["title"],
        "year": analysis.get("year") or "",
        "quote": quote,
        "official_quote": official,
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
