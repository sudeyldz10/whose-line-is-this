# Whose Line Is This? (Guess the line + Song Edition)

This version has no "Find the line" (voice search). It has two games:

- **Guess the line**: a series or film line is shown and you pick the right character out of 4. Getting 5/5 wins the prize.
- **Song Edition**: a 3-second song clip plays and you pick the song within 7 seconds. Getting 5/5 wins the prize.

No API keys are needed: Gemini, Tavily and TMDB are not used.

## Run

    pip install -r requirements-dev.txt
    uvicorn backend.main:app --reload

## Song Edition clips

    python scripts/fetch_previews.py

The script creates `backend/song_clips.py` (iTunes preview URLs). Without clips the Song Edition card stays hidden.

## Adding lines

Copy `lines_template.txt`, fill in one line per entry, then run:

    python scripts/add_lines.py lines.txt tr    # Turkish lines
    python scripts/add_lines.py lines.txt en    # English lines

The format is `line | character | series or film | year | e/m/h` (easy, medium, hard). Duplicates are skipped.
Each game uses 2 Turkish and 3 English lines.

## Files

- `backend/main.py`: app entry, health check, static files
- `backend/game.py`, `backend/game_data.py`: Guess the line logic and lines
- `backend/song.py`, `backend/song_data.py`: Song Edition logic and song list
- `backend/security.py`, `backend/config.py`, `backend/cache.py`: security, settings, SQLite
- `frontend/`: page, styles, game code, images, fonts
- `tests/`: automated tests
