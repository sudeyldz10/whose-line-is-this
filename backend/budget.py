import sqlite3
import time
from contextlib import closing

from . import cache, config


def _day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _conn():
    conn = sqlite3.connect(cache.DB_PATH, timeout=5)
    conn.execute("CREATE TABLE IF NOT EXISTS budget (k TEXT PRIMARY KEY, n INTEGER)")
    return conn


def _bump(conn, key: str) -> int:
    conn.execute("INSERT OR IGNORE INTO budget (k, n) VALUES (?, 0)", (key,))
    conn.execute("UPDATE budget SET n = n + 1 WHERE k = ?", (key,))
    return conn.execute("SELECT n FROM budget WHERE k = ?", (key,)).fetchone()[0]


def take(kind: str, ip: str) -> bool:
    limits = config.BUDGETS.get(kind)
    if not limits:
        return True
    per_ip, total = limits
    day = _day()
    try:
        with closing(_conn()) as conn, conn:
            conn.execute("DELETE FROM budget WHERE k NOT LIKE ?", (day + "|%",))
            if _bump(conn, f"{day}|{kind}|all") > total:
                return False
            if _bump(conn, f"{day}|{kind}|{ip}") > per_ip:
                return False
    except sqlite3.Error:
        return True
    return True
