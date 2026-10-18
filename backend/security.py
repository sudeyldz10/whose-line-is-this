import json
import logging
import os
import re
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import config

log = logging.getLogger("app")

HEAVY_PATHS = ("/api/guess", "/api/transcribe")

_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"tvly-[0-9A-Za-z_\-]{10,}"),
    re.compile(r"eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{5,}"),
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]+"),
    re.compile(r"(?i)(api_key|apikey|key|token|password)=[^&\s\"']+"),
]


def mask(text: str) -> str:
    text = str(text)
    for name in config.REQUIRED_KEYS:
        value = os.getenv(name, "")
        if len(value) >= 8:
            text = text.replace(value, "***")
    for pattern in _PATTERNS:
        text = pattern.sub("***", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "msg": mask(record.getMessage()),
        }
        extra = getattr(record, "fields", None)
        if extra:
            data.update({k: mask(v) if isinstance(v, str) else v for k, v in extra.items()})
        if record.exc_info:
            data["error"] = mask(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app_log = logging.getLogger("app")
    app_log.handlers = [handler]
    app_log.setLevel(logging.INFO)
    app_log.propagate = False
    for noisy in ("httpx", "httpcore", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def client_ip(request) -> str:
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.last_cleanup = time.monotonic()

    def allow(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        if now - self.last_cleanup > 300:
            for k in [k for k, q in self.hits.items() if not q or now - q[-1] > window]:
                del self.hits[k]
            self.last_cleanup = now
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


limiter = RateLimiter()

CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob: https://image.tmdb.org; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "media-src 'self' blob:; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
}


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status)


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.monotonic()
        path = request.url.path
        ip = client_ip(request)
        response = None

        if request.method in ("POST", "PUT", "PATCH"):
            length = request.headers.get("content-length")
            if length is None:
                response = _error(411, "Content-Length is required.")
            elif not length.isdigit() or int(length) > config.MAX_BODY_BYTES:
                response = _error(413, "The request is too large.")

        if response is None and path.startswith("/api/"):
            heavy = path in HEAVY_PATHS
            limit = config.RATE_HEAVY if heavy else config.RATE_GENERAL
            if not limiter.allow(f"{ip}:{'heavy' if heavy else 'general'}", limit, config.RATE_WINDOW):
                response = _error(429, "Too many requests. Please wait a moment.")
                response.headers["Retry-After"] = str(config.RATE_WINDOW)

        if response is None:
            response = await call_next(request)

        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"

        log.info(
            "request",
            extra={"fields": {
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "ms": round((time.monotonic() - started) * 1000),
                "ip": ip,
            }},
        )
        return response
