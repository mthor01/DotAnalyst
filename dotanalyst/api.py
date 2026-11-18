"""Run with: uv run --env-file .env uvicorn dotanalyst.api:app"""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import derive, opendota, poll, queries
from .db import DATA, Ability, Account, Hero, Item, League, open_engine
from .poll import poll_forever
from .replay import ReplayError
from .steam import ANONYMOUS, STEAM_ID_BASE, SteamError, leagues, team_logo

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
    return [{"account_id": a.account_id, "label": a.label, "history_exposed": a.history_exposed, "avatar": a.avatar} for a in rows]


def track(session: Session, account_ids: list[int]) -> None:
    """Track these accounts from the next poll on; one tracked before is tracked again, with its stored matches."""
    for account_id in account_ids:
        account = session.get(Account, account_id) or Account(account_id=account_id)
        account.active = True
        session.add(account)
    session.commit()


@app.post("/api/accounts")
def add_account(session: Db, account_id: Annotated[int, Body(embed=True)]) -> dict:
    """Track a profile by its friend id (32 bits) or its Steam id (64 bits)."""
    if account_id >= STEAM_ID_BASE:
        account_id -= STEAM_ID_BASE
    if not 0 < account_id < ANONYMOUS:
        raise HTTPException(422, f"{account_id} is not a friend id or a Steam id")
    track(session, [account_id])
    return {"account_id": account_id}


@app.post("/api/accounts/{account_id}/teammates")
def add_teammates(session: Db, account_id: int) -> dict:
    """Track every player with queries.TEAMMATE_GAMES games on this account's team in its newest
    queries.TEAMMATE_MATCHES. Returns those that were not tracked yet."""
    tracked = set(session.scalars(select(Account.account_id).where(Account.active)))
    added = [a for a in queries.frequent_teammates(session, account_id) if a not in tracked]
    track(session, added)
    return {"added": added}


@app.get("/api/constants")
def constants(session: Db) -> dict:
    return {
        "heroes": {h.id: {"name": h.name, "localized_name": h.localized_name} for h in session.scalars(select(Hero))},
        "items": {i.id: i.name for i in session.scalars(select(Item))},
        "abilities": {a.name: a.dname for a in session.scalars(select(Ability))},
        "leagues": leagues(session),
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


@app.post("/api/matches/{match_id}/replay")
def request_replay(match_id: int) -> dict:
    """Fetch this match's replay now. About 15 seconds; the answer is the replay state it ends in."""
    try:
        state = poll.refresh_replay(engine, match_id)
    except ReplayError as error:
        raise HTTPException(502, str(error)) from None
    if state is None:
        raise HTTPException(404, f"match {match_id} is not stored")
    return {"replay_state": state}


@app.get("/api/matches/{match_id}/positions")
def positions(match_id: int, start: int, end: int) -> list[dict]:
    log = DATA / "raw" / f"{match_id}.jsonl.gz"
    if not log.is_file():
        raise HTTPException(404, f"no replay log for match {match_id}")
    return derive.positions(log, start, end)


@app.get("/api/metric-averages")
def metric_averages(session: Db, where: Where) -> list[dict]:
    return queries.metric_averages(session, where)


@app.get("/api/heroes")
def heroes(session: Db, where: Where) -> list[dict]:
    return queries.heroes(session, where)


@app.get("/api/wards")
def wards(session: Db, where: Where) -> list[dict]:
    return queries.wards(session, where)


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


@app.get("/api/queue")
def queue(session: Db) -> dict:
    return poll.queue(session, poll.replay_dir())


@app.post("/api/teams/refresh")
def refresh_leagues() -> dict:
    if not os.environ.get("STEAM_API_KEY"):
        raise HTTPException(503, "STEAM_API_KEY is not set")
    try:
        return poll.refresh_leagues(engine)
    except SteamError as error:
        raise HTTPException(502, f"Steam: {error}") from None


@app.post("/api/teams/{team_id}/players/refresh")
def refresh_team_players(session: Db, team_id: int) -> dict:
    """The games outside the league of the team's league players, for their role wheels, of those never asked for."""
    found = queries.team(session, team_id, None, None, None)
    if found is None:
        raise HTTPException(404, f"no league games of team {team_id} are stored")
    try:
        return {"players": poll.refresh_players(engine, [p["account_id"] for p in found["players"]])}
    except httpx.HTTPError as error:
        raise HTTPException(502, f"OpenDota: {error}") from None


@app.get("/api/leagues")
def tournaments(session: Db) -> list[dict]:
    return queries.tournaments(session)


@app.post("/api/leagues")
def add_tournament(session: Db, league_id: Annotated[int, Body(embed=True)]) -> dict:
    """Track a tournament by its league id: the poller then stores its games. Its name comes from OpenDota, once."""
    if league_id <= 0:
        raise HTTPException(422, f"{league_id} is not a league id")
    known = leagues(session)  # first, so that a new database still starts with LEAGUES
    if league_id not in known:
        with httpx.Client() as client:
            known[league_id] = opendota.league_name(client, league_id) or f"League {league_id}"
        session.add(League(league_id=league_id, name=known[league_id]))
        session.commit()
    return {"league_id": league_id, "name": known[league_id]}


@app.get("/api/teams")
def teams(session: Db) -> list[dict]:
    return queries.teams(session)


@app.get("/api/teams/{team_id}")
def team(
    session: Db, team_id: int, date_from: date | None = None, date_to: date | None = None, league_id: int | None = None
) -> dict:
    found = queries.team(session, team_id, date_from, date_to, league_id)
    if found is None:
        raise HTTPException(404, f"no league games of team {team_id} are stored")
    logo_id = found.pop("logo_id")  # too big for a JavaScript number, so the page only gets the address
    with httpx.Client() as client:
        found["logo"] = logo_id and team_logo(client, os.environ.get("STEAM_API_KEY", ""), logo_id)
    return found


if FRONTEND.is_dir():  # after the API routes, so /api/* wins
    app.mount("/", StaticFiles(directory=FRONTEND, html=True))
