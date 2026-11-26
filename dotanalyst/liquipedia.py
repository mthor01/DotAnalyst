"""A league's prize pool, Liquipedia tier, dates and place, from Liquipedia's wiki: one search for the page whose
source holds `leagueid=<id>`, with that page's wikitext in the same answer. Liquipedia asks for a User-Agent that
says who asks, gzip, and at most one request every 2 seconds. Its data is CC BY-SA 3.0: the site credits it."""
import re
import threading
import time

import httpx
from sqlalchemy.orm import Session

from . import catalog
from .db import LeagueCatalog
from .update import installed_version

API = "https://liquipedia.net/dota2/api.php"
AGENT = f"DotAnalyst/{installed_version() or 'dev'} (+https://github.com/mthor01/DotAnalyst)"
PAUSE = 2.0  # seconds between Liquipedia requests, from whatever thread
RECHECK_DAYS = 7  # a league still playing is asked again after this, as prize pools and dates change
_paced = {"last": 0.0}
_pace_lock = threading.Lock()
FIELDS = ("lp_tier", "prize_usd", "start_date", "end_date", "location")


def pace() -> None:
    with _pace_lock:
        time.sleep(max(0.0, _paced["last"] + PAUSE - time.monotonic()))
        _paced["last"] = time.monotonic()


def infobox(wikitext: str) -> dict:
    """The fields of a page's league infobox; what is missing or not a value (TBA, 2026-11-??) is None."""
    start = wikitext.find("{{Infobox league")
    end = wikitext.find("\n}}", start)
    box = wikitext[start : end if end >= 0 else None] if start >= 0 else ""
    field = {k: v.strip().removesuffix("}}").strip() for k, v in re.findall(r"^\|\s*(\w+)\s*=([^\n]*)", box, re.M)}
    date = lambda name: field[name] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", field.get(name, "")) else None  # noqa: E731
    prize = re.sub(r"[$,\s]", "", field.get("prizepoolusd", "")).split(".")[0]
    place = [field[k] for k in ("city", "country") if field.get(k)]
    if field.get("type", "").lower() == "online":
        place = ["Online", *place]
    return {
        "lp_tier": int(field["liquipediatier"]) if field.get("liquipediatier", "").isdigit() else None,
        "prize_usd": int(prize) if prize.isdigit() else None,
        "start_date": date("sdate"), "end_date": date("edate"),
        "location": ", ".join(place) or None,
    }  # fmt: skip


def lookup(session: Session, client: httpx.Client, league_id: int, now: float | None = None) -> bool:
    """Ask Liquipedia for the league's page and keep what its infobox says. A miss is kept too (lp_checked), so it is
    not asked again before due says. A failed request keeps nothing. Returns whether a page was found."""
    params = {
        "action": "query", "generator": "search", "gsrsearch": f'insource:"leagueid={league_id}"', "gsrlimit": 1,
        "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
    }  # fmt: skip
    pace()
    try:
        response = client.get(API, params=params, headers={"User-Agent": AGENT, "Accept-Encoding": "gzip"}, timeout=30)
        body = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        body = None
    if not isinstance(body, dict):
        return False
    page = next(iter(body.get("query", {}).get("pages", {}).values()), None)
    row = session.get(LeagueCatalog, league_id) or LeagueCatalog(league_id=league_id, name=f"League {league_id}")
    session.add(row)
    found = dict.fromkeys(FIELDS)
    if page:
        found = infobox(page["revisions"][0]["slots"]["main"]["*"])
    for name, value in found.items():
        setattr(row, name, value)
    row.lp_page, row.lp_checked = page["title"] if page else None, int(now or time.time())
    session.commit()
    return page is not None


def due(row: LeagueCatalog, now: float) -> bool:
    """Never asked, or asked over RECHECK_DAYS ago while the league still plays."""
    if row.lp_checked is None:
        return True
    return now - row.lp_checked > RECHECK_DAYS * 86400 and catalog.status(row, now) in ("live", "active")
