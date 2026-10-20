import os

REQUIRED_KEYS = ()

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(3 * 1024 * 1024)))
RATE_HEAVY = int(os.getenv("RATE_LIMIT_HEAVY", "120"))
RATE_GENERAL = int(os.getenv("RATE_LIMIT_GENERAL", "240"))
RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
TRUST_PROXY = os.getenv("TRUST_PROXY", "") == "1" or bool(os.getenv("VERCEL"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]


def missing_keys() -> list[str]:
    return [k for k in REQUIRED_KEYS if not os.getenv(k, "").strip()]


def check_env() -> None:
    missing = missing_keys()
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

MEDIA_SRC_EXTRA = [h.strip() for h in os.getenv("MEDIA_SRC_EXTRA", "https://audio-ssl.itunes.apple.com https://*.mzstatic.com").split() if h.strip()]
