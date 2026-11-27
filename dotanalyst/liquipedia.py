"""A league's prize pool, Liquipedia tier, dates and place, from Liquipedia's wiki: one search for the page whose
source holds `leagueid=<id>`, with that page's wikitext in the same answer. Liquipedia asks for a User-Agent that
says who asks, gzip, and at most one request every 2 seconds. Its data is CC BY-SA 3.0: the site credits it."""
import json
import re
import threading
import time
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from . import catalog, lp_structure
from .db import LeagueCatalog
from .update import installed_version

API = "https://liquipedia.net/dota2/api.php"
COMMONS = "https://liquipedia.net/commons/api.php"  # bracket layouts live on the shared wiki
AGENT = f"DotAnalyst/{installed_version() or 'dev'} (+https://github.com/mthor01/DotAnalyst)"
PAUSE = 2.0  # seconds between Liquipedia requests, from whatever thread
RECHECK_DAYS = 7  # a league still playing is asked again after this, as prize pools and dates change
_paced = {"last": 0.0}
_pace_lock = threading.Lock()
FIELDS = ("lp_tier", "prize_usd", "start_date", "end_date", "location", "region")
STRUCTURE_HOURS = 6  # brackets and groups of a league still playing are read again after this; a finished one's never
MAX_PAGES = 50  # what one revisions request may ask for
NOT_STAGES = ("Statistics",)  # a prizepool subpage names the winner
VERSION = 7  # of the kept structure: one kept by another version is read again
MISMATCH_DAYS = 30  # a page whose event ended this long before the league's first known game is another event's


def fits(row: LeagueCatalog, start_date: str | None, end_date: str | None) -> bool:
    """Whether a page with these dates can be the league's. A lobby league (FACEIT's) plays for years and once hosted
    a two-day qualifier whose page names its id: an event over long before the league's games is not the league. Its
    games: the first known, else when Steam last saw it live (an amateur league's games are known once its page is
    opened)."""
    end, played = catalog.day_end(end_date) or catalog.day_end(start_date), row.first_game or row.live_seen
    return not (played and end and end < played - MISMATCH_DAYS * 86400)


def pace() -> None:
    with _pace_lock:
        time.sleep(max(0.0, _paced["last"] + PAUSE - time.monotonic()))
        _paced["last"] = time.monotonic()


def _fields(wikitext: str) -> dict[str, str]:
    """Every field of a page's league infobox, as written."""
    start = wikitext.find("{{Infobox league")
    end = wikitext.find("\n}}", start)
    box = wikitext[start : end if end >= 0 else None] if start >= 0 else ""
    return {k: v.strip().removesuffix("}}").strip() for k, v in re.findall(r"^\|\s*(\w+)\s*=([^\n]*)", box, re.M)}


def infobox(wikitext: str) -> dict:
    """The fields of a page's league infobox; what is missing or not a value (TBA, 2026-11-??) is None."""
    field = _fields(wikitext)
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
        "region": catalog.region_of(field.get("region", ""), field.get("country", "")),
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
        if not fits(row, found["start_date"], found["end_date"]):
            page, found = None, dict.fromkeys(FIELDS)  # kept as a miss
    for name, value in found.items():
        setattr(row, name, value)
    row.lp_page, row.lp_checked = page["title"] if page else None, int(now or time.time())
    session.commit()
    return page is not None


def due(row: LeagueCatalog, now: float) -> bool:
    """Never asked, kept with a page that does not fit its games (found before fits was), or asked over RECHECK_DAYS
    ago while the league still plays."""
    if row.lp_checked is None or (row.lp_page and not fits(row, row.start_date, row.end_date)):
        return True
    return now - row.lp_checked > RECHECK_DAYS * 86400 and catalog.status(row, now) in ("live", "active")


def _get(client: httpx.Client, url: str, params: dict) -> dict | None:
    """One paced Liquipedia request; None when it failed."""
    pace()
    try:
        response = client.get(url, params={**params, "format": "json"}, headers={"User-Agent": AGENT, "Accept-Encoding": "gzip"}, timeout=30)
        body = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        body = None
    return body if isinstance(body, dict) else None


LIST = "Liquipedia:Tournaments"  # the upcoming, ongoing and completed tournaments of Liquipedia's sidebar
LIST_HOURS = 6  # the list is read again after this


def sidebar(wikitext: str) -> list[dict]:
    """The upcoming and ongoing tournaments of Liquipedia's sidebar list (`** Page_title | Short name | …` under
    `*Upcoming` and `*Ongoing`), each page title as the API writes it (spaces, not underscores)."""
    found, state = [], None
    for line in wikitext.splitlines():
        if line.startswith("*") and not line.startswith("**"):
            state = line.lstrip("*").strip().lower()
        elif line.startswith("**") and state in ("upcoming", "ongoing"):
            page = line.lstrip("*").split("|")[0].strip().replace("_", " ")
            if page:
                found.append({"page": page[0].upper() + page[1:], "state": state})
    return found


def fetch_list(client: httpx.Client, data: Path, now: float) -> int:
    """Liquipedia's upcoming and ongoing tournaments with their infobox (name, tier, prize pool, dates, place, region,
    league id once it has one) into data/explore/lp_tournaments.json, unless read under LIST_HOURS ago: 2 requests. A
    failed request keeps the old list. A page without an answer is left out. Returns the tournaments kept."""
    stored = data / "explore" / "lp_tournaments.json"
    try:
        kept = json.loads(stored.read_text())
    except (OSError, ValueError):
        kept = None
    if isinstance(kept, dict) and now - kept.get("read", 0) < LIST_HOURS * 3600:
        return 0
    body = _get(client, API, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": LIST})
    listed = sidebar(_texts(body).get(LIST, "")) if body else []
    body = listed and _get(client, API, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                         "titles": "|".join(t["page"] for t in listed[:MAX_PAGES])})  # fmt: skip
    if not body:
        return 0
    texts, found = _texts(body), []
    for t in listed[:MAX_PAGES]:
        if t["page"] not in texts:
            continue
        field = _fields(texts[t["page"]])
        found.append({**t, "name": field.get("name") or t["page"], "league_id": int(field["leagueid"]) if field.get("leagueid", "").isdigit() else None,
                      **infobox(texts[t["page"]])})  # fmt: skip
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps({"read": now, "tournaments": found}))
    return len(found)


def _texts(body: dict) -> dict[str, str]:
    found = {}
    for page in body.get("query", {}).get("pages", {}).values():
        text = (page.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*")
        if text is not None:
            found[page["title"]] = text
    return found


def pages(client: httpx.Client, title: str, league_id: int) -> dict[str, str] | None:
    """The wikitext of the event page and its direct subpages (its stages), in one request after the list of them. A
    subpage with an infobox of its own is another tournament (a qualifier) unless it names this league. None on a
    failed request."""
    listed = _get(client, API, {"action": "query", "list": "allpages", "apprefix": f"{title}/", "aplimit": 500})
    if listed is None:
        return None
    children = [
        p["title"] for p in listed.get("query", {}).get("allpages", [])
        if "/" not in p["title"][len(title) + 1 :] and p["title"].rsplit("/", 1)[-1] not in NOT_STAGES
    ]  # fmt: skip
    body = _get(client, API, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                              "titles": "|".join([title, *children][:MAX_PAGES])})  # fmt: skip
    if body is None:
        return None
    found = _texts(body)
    for name, text in list(found.items()):
        own = re.search(r"\|\s*leagueid\s*=\s*(\d+)", text) if "{{Infobox league" in text else None
        if name != title and "{{Infobox league" in text and not (own and int(own[1]) == league_id):
            del found[name]
    wanted = lp_structure.match_pages(found)  # the matches a bracket keeps on pages of their own
    for i in range(0, len(wanted), MAX_PAGES):
        more = _get(client, API, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                  "titles": "|".join(wanted[i : i + MAX_PAGES])})  # fmt: skip
        if more is None:
            return None
        found.update(_texts(more))
    return found


def layouts(client: httpx.Client, names: set[str], data: Path) -> dict[str, list[dict]]:
    """The bracket layouts, from data/leagues/brackets.json; one asked of commons only while it is not there, as a
    layout never changes."""
    stored = data / "leagues" / "brackets.json"
    known = json.loads(stored.read_text()) if stored.exists() else {}
    missing = sorted(n for n in names if n not in known)
    if missing:
        body = _get(client, COMMONS, {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                      "titles": "|".join(f"Template:{n}" for n in missing[:MAX_PAGES])})  # fmt: skip
        for name, text in _texts(body or {}).items():
            known[name.removeprefix("Template:")] = lp_structure.layout(text)
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_text(json.dumps(known))
    return {n: known[n] for n in names if n in known}


def _kept(league_id: int, data: Path) -> dict | None:
    """The kept structure file, None when missing, unreadable or of another VERSION."""
    stored = data / "leagues" / f"{league_id}.lp.json"
    try:
        cached = json.loads(stored.read_text())
    except (OSError, ValueError):
        return None
    return cached if isinstance(cached, dict) and cached.get("version") == VERSION else None


def kept(league_id: int, data: Path) -> dict | None:
    """The league's kept structure whatever its age, never asking Liquipedia (Explore reads it)."""
    cached = _kept(league_id, data)
    return cached["found"] if cached else None


def structure_due(row: LeagueCatalog, data: Path, now: float, finished: bool) -> bool:
    """Whether structure would ask Liquipedia: nothing kept for this page, or kept STRUCTURE_HOURS ago while it plays."""
    cached = _kept(row.league_id, data)
    return not cached or cached["page"] != row.lp_page or (not finished and now - cached["fetched"] >= STRUCTURE_HOURS * 3600)


def structure(client: httpx.Client, row: LeagueCatalog, data: Path, now: float, finished: bool) -> dict | None:
    """The league's brackets, groups, upcoming matches and rosters (lp_structure.structure), kept in
    data/leagues/<id>.lp.json: read again after STRUCTURE_HOURS while the league plays, a finished league's never. A
    failed request keeps what was read before."""
    stored = data / "leagues" / f"{row.league_id}.lp.json"
    cached = _kept(row.league_id, data)
    if cached and cached["page"] != row.lp_page:  # Liquipedia's search found another page since
        cached = None
    if cached and not structure_due(row, data, now, finished):
        return cached["found"]
    got = pages(client, row.lp_page, row.league_id)
    if got is None:
        return cached["found"] if cached else None
    found = lp_structure.structure(got, layouts(client, lp_structure.layout_names(got), data), now)
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps({"version": VERSION, "fetched": now, "page": row.lp_page, "found": found}))
    return found
