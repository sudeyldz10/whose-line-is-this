import json

import pytest
from fastapi.testclient import TestClient

from backend import config, security
from backend.main import app


@pytest.fixture()
def client():
    security.limiter.hits.clear()
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_fails_when_key_missing(client, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY")
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["checks"]["env"] is False


def test_startup_fails_fast_without_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        with TestClient(app):
            pass


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_body_too_large(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 100)
    r = client.post("/api/guess", content=json.dumps({"text": "x" * 500}), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_text_validation(client):
    r = client.post("/api/guess", json={"text": "ab"})
    assert r.status_code == 400
    r = client.post("/api/guess", json={"text": "x" * 2500})
    assert r.status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_HEAVY", 3)
    codes = [client.post("/api/guess", json={"text": "ab"}).status_code for _ in range(5)]
    assert codes[:3] == [400, 400, 400]
    assert codes[3:] == [429, 429]


def test_game_flow(client):
    data = client.get("/api/game/new").json()
    assert len(data["questions"]) == data["total"] == 5
    q = data["questions"][0]
    assert len(set(q["options"])) == 4
    r = client.post("/api/game/check", json={"id": q["id"], "choice": q["options"][0]})
    assert r.status_code == 200 and "correct" in r.json()
    assert client.post("/api/game/check", json={"id": 99999, "choice": "x"}).status_code == 404


def test_game_avoids_seen_questions(client):
    first = [q["id"] for q in client.get("/api/game/new").json()["questions"]]
    second = [q["id"] for q in client.get("/api/game/new", params={"seen": ",".join(map(str, first))}).json()["questions"]]
    assert not set(first) & set(second)


def test_internal_errors_are_hidden(client, monkeypatch):
    from backend import llm

    def boom(*a, **k):
        raise ValueError("secret table users at /srv/app/db.py")

    monkeypatch.setattr(llm, "prepare_query", boom)
    r = client.post("/api/guess", json={"text": "some unknown line here"})
    assert r.status_code == 502
    assert "secret" not in r.text and "/srv" not in r.text


def test_log_masking():
    masked = security.mask("key=AIzaSyA1234567890123456789012345 Bearer abc.def.ghi test-gemini-key-000000")
    assert "AIza" not in masked and "abc.def" not in masked and "test-gemini-key" not in masked


def test_fix_speaker():
    from backend import lookup

    fixed = lookup.fix_speaker({"character": "Rachel Green", "title": "Friends"}, "We were on a break!")
    assert fixed["character"] == "Ross Geller"


def test_quota_error_is_friendly(client, monkeypatch):
    import httpx

    from backend import llm

    def quota(*a, **k):
        req = httpx.Request("POST", "https://api.tavily.com/search")
        raise httpx.HTTPStatusError("limit", request=req, response=httpx.Response(432, request=req))

    monkeypatch.setattr(llm, "prepare_query", lambda t: {"cleaned_quote": t, "search_query": t})
    from backend import search

    monkeypatch.setattr(search, "web_search", quota)
    r = client.post("/api/guess", json={"text": "some unknown line here"})
    assert r.status_code == 503
    assert "busy" in r.json()["detail"]


def test_search_budget(client, monkeypatch):
    from backend import budget, cache

    monkeypatch.setattr(config, "BUDGETS", {"search": (2, 100), "transcribe": (2, 100)})
    monkeypatch.setattr(cache, "DB_PATH", cache.DB_PATH.parent / "budget-test.db")
    cache.DB_PATH.unlink(missing_ok=True)
    assert budget.take("search", "1.1.1.1")
    assert budget.take("search", "1.1.1.1")
    assert not budget.take("search", "1.1.1.1")
    assert budget.take("search", "2.2.2.2")
    cache.DB_PATH.unlink(missing_ok=True)
