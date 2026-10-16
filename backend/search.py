import os

import httpx

TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 6) -> list[dict]:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is missing in the .env file.")
    resp = httpx.post(
        TAVILY_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        },
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": (r.get("content") or "")[:700],
        }
        for r in results
    ]
