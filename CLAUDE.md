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