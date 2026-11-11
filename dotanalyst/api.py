"""Run with: uv run --env-file .env uvicorn dotanalyst.api:app"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import queries
from .db import Account, Hero, Item, open_engine
from .poll import poll_forever

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


@app.get("/api/heroes")
def heroes(session: Db, where: Where) -> list[dict]:
    return queries.heroes(session, where)


@app.get("/api/teammates")
def teammates(session: Db, where: Where) -> list[dict]:
    return queries.teammates(session, where)


@app.get("/api/matchups")
def matchups(session: Db, where: Where) -> list[dict]:
    return queries.matchups(session, where)


if FRONTEND.is_dir():  # after the API routes, so /api/* wins
    app.mount("/", StaticFiles(directory=FRONTEND, html=True))
