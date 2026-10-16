import json
import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "cache.db"
TTL_SECONDS = 30 * 24 * 3600


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, ts REAL)"
    )
    return conn


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get(text: str):
    key = normalize(text)
    with _conn() as conn:
        row = conn.execute("SELECT v, ts FROM cache WHERE k = ?", (key,)).fetchone()
    if not row:
        return None
    if time.time() - row[1] > TTL_SECONDS:
        return None
    return json.loads(row[0])


def set(text: str, value: dict) -> None:
    key = normalize(text)
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (k, v, ts) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )
