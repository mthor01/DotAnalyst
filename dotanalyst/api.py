"""Run with: uv run --env-file .env uvicorn dotanalyst.api:app"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import derive, poll, queries
from .db import DATA, Account, Hero, Item, open_engine
from .metrics import NAMES
from .poll import poll_forever
from .steam import SteamError

engine = open_engine()
FRONTEND = Path("frontend/dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller = asyncio.create_task(poll_forever(engine))
    yield
    poller.cancel()


app = FastAPI(lifespan=lifespan)


def db():
    with Session(engine) as session:
        yield session


Db = Annotated[Session, Depends(db)]
Where = Annotated[list, Depends(queries.conditions)]


@app.get("/api/accounts")
def accounts(session: Db) -> list[dict]:
    rows = session.scalars(select(Account).where(Account.active).order_by(Account.label, Account.account_id))
    return [{"account_id": a.account_id, "label": a.label, "history_exposed": a.history_exposed} for a in rows]


@app.get("/api/constants")
def constants(session: Db) -> dict:
    return {
        "heroes": {h.id: {"name": h.name, "localized_name": h.localized_name} for h in session.scalars(select(Hero))},
        "items": {i.id: i.name for i in session.scalars(select(Item))},
    }


@app.get("/api/matches")
def matches(session: Db, where: Where) -> list[dict]:
    return queries.matches(session, where)


@app.get("/api/matches/{match_id}")
def match(session: Db, match_id: int) -> dict:
    found = queries.match(session, match_id)
    if found is None:
        raise HTTPException(404, f"match {match_id} is not stored")
    return found


@app.get("/api/matches/{match_id}/positions")
def positions(match_id: int, start: int, end: int) -> list[dict]:
    log = DATA / "raw" / f"{match_id}.jsonl.gz"
    if not log.is_file():
        raise HTTPException(404, f"no replay log for match {match_id}")
    return derive.positions(log, start, end)


@app.get("/api/metrics")
def metric_values(session: Db, where: Where, metric: str) -> list[dict]:
    if metric not in NAMES:
        raise HTTPException(404, f"no metric {metric!r}; there are: {', '.join(NAMES)}")
    return queries.metric(session, where, metric)


@app.get("/api/metric-averages")
def metric_averages(session: Db, where: Where) -> list[dict]:
    return queries.metric_averages(session, where)


@app.get("/api/heroes")
def heroes(session: Db, where: Where) -> list[dict]:
    return queries.heroes(session, where)


@app.get("/api/teammates")
def teammates(session: Db, where: Where) -> list[dict]:
    return queries.teammates(session, where)


@app.get("/api/matchups")
def matchups(session: Db, where: Where) -> list[dict]:
    return queries.matchups(session, where)


# plain functions, so FastAPI runs them in a worker thread and a long check does not stall the other requests
@app.post("/api/refresh")
def refresh() -> dict:
    try:
        return poll.refresh(engine)
    except SteamError as error:
        raise HTTPException(502, f"Steam: {error}") from None


@app.post("/api/teams/refresh")
def refresh_leagues() -> dict:
    if not os.environ.get("STEAM_API_KEY"):
        raise HTTPException(503, "STEAM_API_KEY is not set")
    try:
        return poll.refresh_leagues(engine)
    except SteamError as error:
        raise HTTPException(502, f"Steam: {error}") from None


@app.get("/api/teams")
def teams(session: Db) -> list[dict]:
    return queries.teams(session)


@app.get("/api/teams/{team_id}")
def team(session: Db, team_id: int) -> dict:
    found = queries.team(session, team_id)
    if found is None:
        raise HTTPException(404, f"no league games of team {team_id} are stored")
    return found


if FRONTEND.is_dir():  # after the API routes, so /api/* wins
    app.mount("/", StaticFiles(directory=FRONTEND, html=True))
