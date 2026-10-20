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


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_body_too_large(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 100)
    r = client.post("/api/game/check", content=json.dumps({"id": 1, "choice": "x" * 500}), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_GENERAL", 3)
    codes = [client.get("/api/game/new").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
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


def test_log_masking():
    masked = security.mask("key=AIzaSyA1234567890123456789012345 Bearer abc.def.ghi")
    assert "AIza" not in masked and "abc.def" not in masked


def test_song_not_ready_without_clips(client, monkeypatch):
    from backend import song

    monkeypatch.setattr(song, "CLIPS", {})
    monkeypatch.setattr(song, "local_clip", lambda s: None)
    assert client.get("/api/song/ready").json() == {"ready": False}
    assert client.get("/api/song/new").status_code == 503


def test_song_flow(client, monkeypatch):
    from backend import song

    monkeypatch.setattr(song, "CLIPS", {song.slug(s["title"], s["artist"]): "https://example.com/c.mp3" for s in song.SONGS})
    monkeypatch.setattr(song, "local_clip", lambda s: None)
    assert client.get("/api/song/ready").json() == {"ready": True}
    data = client.get("/api/song/new").json()
    assert len(data["questions"]) == 5
    assert len({q["id"] for q in data["questions"]}) == 5
    assert len({song.SONGS[q["id"]]["artist"] for q in data["questions"]}) == 5
    for q in data["questions"]:
        assert len(set(q["options"])) == 4
        right = song.label(song.SONGS[q["id"]])
        assert right in q["options"]
        assert 0 < q["start"] < 27
        ok = client.post("/api/song/check", json={"id": q["id"], "choice": right}).json()
        assert ok["correct"] is True and ok["answer"] == right
        bad = client.post("/api/song/check", json={"id": q["id"], "choice": None}).json()
        assert bad["correct"] is False


def test_song_seen_avoidance(client, monkeypatch):
    from backend import song

    monkeypatch.setattr(song, "CLIPS", {song.slug(s["title"], s["artist"]): "https://example.com/c.mp3" for s in song.SONGS})
    monkeypatch.setattr(song, "local_clip", lambda s: None)
    first = [q["id"] for q in client.get("/api/song/new").json()["questions"]]
    second = [q["id"] for q in client.get("/api/song/new?seen=" + ",".join(map(str, first))).json()["questions"]]
    assert not set(first) & set(second)


def test_two_turkish_three_english_per_game():
    from backend import game

    for _ in range(50):
        questions = game.pick_questions()
        assert sum(game.LINES[q["id"]].get("lang") == "tr" for q in questions) == 2
        assert len(questions) == 5
        for q in questions:
            item = game.LINES[q["id"]]
            lang = item.get("lang", "en")
            names = {d["character"] for d in game.LINES if d.get("lang", "en") != lang} | {d["name"] for d in game.DECOYS if d.get("lang", "en") != lang}
            assert not (set(q["options"]) - {item["character"]}) & names
