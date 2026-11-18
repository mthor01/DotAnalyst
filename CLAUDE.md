# Testing
- Write tests for data fetching, parsing and stat calculations (pytest)
- Tests never call live APIs (Steam/OpenDota): use saved JSON fixtures in tests/fixtures/
- Parser tests use a small sample replay + its saved parser output, never download replays in tests
- UI/templates don't need unit tests

# Conventions
- Python 3.14, FastAPI, SQLite via SQLAlchemy
- Frontend: Svelte + TypeScript, charts with ECharts
- Python env and dependencies via uv (pyproject.toml)
- No new dependencies without asking
- Make a new git commit for every change you make but ask before pushing

# Architecture decisions
- Replay parsing via odota/parser in Docker (HTTP on port 5600, POST .dem, returns JSON lines)
- Keep raw parser output per match (compressed .jsonl.gz); derived stats tables are recomputable from it

# Gotchas
- API keys only in .env (gitignored), never hardcode or commit them
- External APIs are rate-limited: never refetch a match or replay that's already stored
- The GitHub repo is public: nothing committed may identify a real player (account ids, Steam ids, names). Fixtures saved from live answers get made-up ids (1001, 2001, ...) and names ("Player 1") before they are committed; the pre-commit hook in .githooks/ refuses ids it finds in the local database

# Documentation
- IMPLEMENTATION.md records the logic of everything the site works out itself (lanes, teamfights, lotuses collected, camps pulled, healing, team stats, ...)
- With every change, check IMPLEMENTATION.md and update it where a rule, a threshold or a known limit changed; a new computed stat gets its own section there

# Design
- Show heroes by picture, not by name: `heroPortrait` (wide) where there is room, `heroIcon` (small square) in tight spots; both in frontend/src/lib/constants.svelte.ts. The name goes in the image's `alt` and `title`, so hovering and screen readers still give it
