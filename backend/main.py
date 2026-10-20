from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging  # noqa: E402

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import cache, config, game, security, song  # noqa: E402

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


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled error", exc_info=exc, extra={"fields": {"path": request.url.path}})
    return JSONResponse({"detail": GENERIC_ERROR}, status_code=500)


@app.get("/health")
def health():
    checks = {"env": not config.missing_keys(), "database": cache.healthy()}
    ok = all(checks.values())
    return JSONResponse({"status": "ok" if ok else "unhealthy", "checks": checks}, status_code=200 if ok else 503)


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
