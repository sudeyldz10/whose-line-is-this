import json
import os
import re
import time

from google import genai
from google.genai import errors, types

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
RETRY_CODES = {429, 500, 503, 504}
ATTEMPTS = 3
_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing in the .env file.")
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
    return _client


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _generate(system: str, contents) -> dict:
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        temperature=0.1,
    )
    last = None
    for model in [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]:
        for attempt in range(ATTEMPTS):
            try:
                resp = _get_client().models.generate_content(model=model, contents=contents, config=config)
                return _parse_json(resp.text)
            except errors.APIError as e:
                last = e
                if e.code == 404:
                    break
                if e.code not in RETRY_CODES:
                    raise
                time.sleep(1.5 * (attempt + 1))
    raise last


QUERY_RULES = (
    "The line can be in any language. If it is not English, it may be a dubbed or translated "
    "version, so also use the likely original English wording when you know it."
)


def transcribe(audio: bytes, mime: str) -> dict:
    system = (
        "You hear a person saying a line from a movie or TV show. Transcribe exactly what is said, "
        "in the language that is spoken. Then correct obviously misheard words if the line is a known quote. "
        + QUERY_RULES
        + " If there is no intelligible speech, return empty strings. Return ONLY JSON: "
        '{"transcript": "exact words heard", "language": "name of the spoken language", '
        '"cleaned_quote": "the corrected line in the spoken language", '
        '"search_query": "short web search query: the line in quotes plus movie OR tv quote"}'
    )
    contents = [types.Part.from_bytes(data=audio, mime_type=mime), "Transcribe this audio."]
    return _generate(system, contents)


def prepare_query(transcript: str) -> dict:
    system = (
        "The user typed or said a line from a movie or TV show. The text may contain misheard words. "
        + QUERY_RULES
        + " Return ONLY JSON: "
        '{"cleaned_quote": "the corrected line", '
        '"search_query": "short web search query: the line in quotes plus movie OR tv quote"}'
    )
    data = _generate(system, f"Line: {transcript}")
    cleaned = (data.get("cleaned_quote") or transcript).strip()
    query = (data.get("search_query") or f'"{cleaned}" movie tv quote').strip()
    return {"cleaned_quote": cleaned, "search_query": query}


def analyze_results(quote: str, results: list[dict]) -> dict:
    listing = "\n\n".join(
        f"[{i}] {r['title']}\nURL: {r['url']}\n{r['content']}"
        for i, r in enumerate(results)
    )
    system = (
        "Using only the search results below, identify the character who SPEAKS the given line "
        "and the movie or TV production it comes from. The character must be the one who says the line, "
        "never a character the line is about, addressed to, or merely mentioned in the same page. "
        "If a line is about two people (for example a couple), name only the one who says it. "
        "If the results do not make clear who speaks it, lower the confidence below 0.6. "
        "The line may be in any language, possibly a dubbed version. Rely strictly on evidence in the results. "
        "If the results do not support the line, set found to false. "
        "If sources contradict each other, lower the confidence. "
        "Use the original title of the production. "
        "Also give official_quote: the line copied exactly as it is written in the search results, "
        "or an empty string if no result shows the exact wording. Return ONLY JSON: "
        '{"found": true or false, "character": "character name", "title": "original title", '
        '"year": "year or empty", "media_type": "movie or tv", "official_quote": "exact wording or empty", '
        '"source_index": number of the best source, '
        '"supporting_indices": [numbers of all sources that support the answer], '
        '"confidence": number from 0 to 1, "note": "one sentence of reasoning"}'
    )
    return _generate(system, f"Line: {quote}\n\nSearch results:\n{listing}")
