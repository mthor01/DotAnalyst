"""A league's structure from Liquipedia's page source: bracket trees (`{{Bracket}}` plus the layout page on Liquipedia's
commons wiki), groups (`{{GroupStandings}}` with the results of the `{{Matchlist}}` matches), upcoming matches and
rosters (`{{TeamParticipants}}`). Pure functions over wikitext; liquipedia.py fetches. See Liquipedia brackets and
groups in IMPLEMENTATION.md."""
import calendar
import re

COMMENT = re.compile(r"<!--.*?-->", re.S)
HEADING = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.M)
MONTHS = {name: i for i, name in enumerate(calendar.month_name) if name}
# the time zones Liquipedia writes as {{Abbr/<zone>}}, hours from UTC; another one is read as UTC
ZONES = {"UTC": 0, "GMT": 0, "WET": 0, "CET": 1, "CEST": 2, "EET": 2, "EEST": 3, "MSK": 3, "GST": 4, "IST": 5.5,
         "ICT": 7, "WIB": 7, "SGT": 8, "PHT": 8, "CST": 8, "KST": 9, "JST": 9, "AEDT": 11, "AEST": 10,
         "PST": -8, "PDT": -7, "MST": -7, "MDT": -6, "EST": -5, "EDT": -4, "BRT": -3, "PET": -5, "CLT": -4}  # fmt: skip
ROUNDS = {"!u1!": "Grand Final", "!u2!": "Upper Bracket Final", "!u3!": "Upper Bracket Semifinals",
          "!u4!": "Upper Bracket Quarterfinals", "!l2!": "Lower Bracket Final", "!l3!": "Lower Bracket Semifinal",
          "!l4!": "Lower Bracket Quarterfinals"}  # fmt: skip
STALE = 12 * 3600  # an unplayed match dated longer ago than this is not upcoming
UPCOMING = 10


def blocks(text: str, name: str) -> list[tuple[int, str]]:
    """Every {{name…}} template at any depth, brace-balanced: (offset, body without the outer braces)."""
    found, start, opener = [], 0, "{{" + name
    while (i := text.find(opener, start)) >= 0:
        start = i + 2
        after = text[i + len(opener) : i + len(opener) + 1]
        if after and after not in "|}\n\t ":  # {{Matchlist is not {{Match
            continue
        depth, j = 0, i
        while j < len(text):
            if text.startswith("{{", j):
                depth, j = depth + 1, j + 2
            elif text.startswith("}}", j):
                depth, j = depth - 1, j + 2
                if not depth:
                    break
            else:
                j += 1
        if depth:  # never closed: the rest of the page is not this template
            break
        found.append((i, text[i + 2 : j - 2]))
    return found


def params(body: str) -> dict[str, str]:
    """A template body's top-level parameters: |key=value, and |value as "1", "2"… Splits only outside {{ }} and [[ ]]."""
    body = COMMENT.sub("", body)
    parts, current, braces, links, i = [], [], 0, 0, 0
    while i < len(body):
        two = body[i : i + 2]
        if two in ("{{", "}}", "[[", "]]"):
            braces += {"{{": 1, "}}": -1}.get(two, 0)
            links += {"[[": 1, "]]": -1}.get(two, 0)
            current.append(two)
            i += 2
            continue
        if body[i] == "|" and braces <= 0 and links <= 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(body[i])
        i += 1
    parts.append("".join(current))
    found, n = {}, 0
    for part in parts[1:]:
        key, eq, value = part.partition("=")
        if eq and key.strip() and "{{" not in key and "[[" not in key:
            found[key.strip()] = value.strip()
        else:
            n += 1
            found[str(n)] = part.strip()
    return found


def inner(value: str) -> str:
    """The body of a parameter that is one template, e.g. `{{Map|winner=1}}` → `Map|winner=1`."""
    value = value.strip()
    return value[2:-2] if value.startswith("{{") and value.endswith("}}") else ""


def when(date: str) -> int | None:
    """`November 13, 2026 - 11:00 {{Abbr/CET}}` in seconds; a day without a time is its noon UTC."""
    m = re.match(r"\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})(?:\s*-\s*(\d{1,2}):(\d{2}))?(?:\s*\{\{Abbr/(\w+)\}\})?", date or "")
    if not m or m[1] not in MONTHS:
        return None
    hour, minute, offset = (int(m[4]), int(m[5]), ZONES.get(m[6] or "", 0)) if m[4] else (12, 0, 0)
    try:
        return calendar.timegm((int(m[3]), MONTHS[m[1]], int(m[2]), hour, minute, 0)) - int(offset * 3600)
    except ValueError:
        return None


def opponent(value: str) -> str | None:
    """A team's name from `{{TeamOpponent|<name>}}`; none for an empty slot or TBD."""
    name = params(inner(value)).get("1", "").strip()
    return None if not name or name.upper() == "TBD" else name


def numbered(p: dict, prefix: str) -> list[tuple[int, str]]:
    return sorted((int(k[len(prefix) :]), v) for k, v in p.items() if re.fullmatch(rf"{prefix}\d+", k))


def match(body: str) -> dict:
    """One match: the two teams, its time, its Dota match ids, the maps played (skipped ones dropped), the score and
    the winner (0, 1): the Match's own `winner=`, else a team that won more than half the listed maps."""
    p = params(body)
    ids = {n: int(v) for n, v in numbered(p, "matchid") if v.isdigit()}
    maps = []
    for n, value in numbered(p, "map"):
        mp = params(inner(value))
        if mp.get("finished") == "skip":
            continue
        won = mp.get("winner")
        maps.append({"team1side": mp.get("team1side") or None, "winner": int(won) - 1 if won in ("1", "2") else None,
                     "match_id": ids.get(n)})  # fmt: skip
    score = [sum(m["winner"] == i for m in maps) for i in (0, 1)]
    if p.get("winner") in ("1", "2"):
        winner = int(p["winner"]) - 1
    elif maps and max(score) > len(maps) / 2:
        winner = 0 if score[0] > score[1] else 1
    else:
        winner = None
    return {
        "opponents": [opponent(p.get("opponent1", "")), opponent(p.get("opponent2", ""))],
        "time": when(p.get("date", "")), "match_ids": list(ids.values()), "maps": maps, "score": score, "winner": winner,
    }  # fmt: skip


def played(m: dict) -> bool:
    return any(mp["winner"] is not None for mp in m["maps"]) or m["winner"] is not None


def layout(wikitext: str) -> list[dict]:
    """A bracket layout (commons `Template:Bracket/<name>`): each match slot, the slots feeding it, its round header,
    and its section: lower after a header starting `!l`, until one starting `!u`."""
    found, section = [], "upper"
    for _, body in blocks(COMMENT.sub("", wikitext), "TemplateMatch"):
        p = params(body)
        header = p.get("header") or None
        if header and header.startswith("!l"):
            section = "lower"
        elif header and header.startswith("!u"):
            section = "upper"
        found.append({"id": p.get("matchid"), "toupper": p.get("toupper") or None, "tolower": p.get("tolower") or None,
                      "header": header, "root": p.get("root") == "true", "reset": p.get("bracketreset") or None,
                      "section": section})  # fmt: skip
    return found


def round_name(code: str | None, index: int) -> str:
    m = re.match(r"(!\w+?!)(\w*)", code or "")
    if m and m[1] in ROUNDS:
        return ROUNDS[m[1]]
    if m and m[1] in ("!lx!", "!ux!") and m[2].isdigit():
        return f"{'Lower' if m[1] == '!lx!' else 'Upper'} Bracket Round {m[2]}"
    return f"Round {index}"


def bracket(body: str, slots: list[dict]) -> dict:
    """The tree: per section (upper, lower) its rounds in order, each with its matches and the ids feeding them. A
    round is named by the page's own `R<r>M<m>header=`, else by the layout's header code. The bracket reset shows only
    when it was played."""
    p = params(body)
    matches, headers = {}, {}
    for key, value in p.items():
        m = re.fullmatch(r"R(\d+)M(\d+)(header)?", key)
        if key == "RxMBR":
            matches["RxMBR"] = match(inner(value))
        elif m and m[3]:
            headers[f"R{int(m[1]):02d}-M{int(m[2]):03d}"] = value
        elif m:
            matches[f"R{int(m[1]):02d}-M{int(m[2]):03d}"] = match(inner(value))
    sections: dict[str, dict[int, dict]] = {}
    for slot in slots:
        sid = slot["id"] or ""
        m = matches.get(sid) or match("Match")
        if sid == "RxMBR" and not played(m):
            continue
        number = re.match(r"R(\d+)", sid)
        index = 999 if sid == "RxMBR" or not number else int(number[1])
        r = sections.setdefault(slot["section"], {}).setdefault(index, {"page": None, "code": None, "matches": []})
        r["page"] = r["page"] or headers.get(sid)
        r["code"] = r["code"] or slot["header"]
        r["matches"].append({**m, "id": sid, "feeders": [f for f in (slot["toupper"], slot["tolower"]) if f]})
    return {"sections": [
        {"name": name, "rounds": [
            {"name": "Bracket Reset" if i == 999 else r["page"] or round_name(r["code"], i), "matches": r["matches"]}
            for i, r in sorted(sections[name].items())]}
        for name in ("upper", "lower") if name in sections
    ]}  # fmt: skip


def group_rows(members: list[str], pool: list[dict]) -> list[dict]:
    """A group's table from the matches between its members: series, then maps, then map difference. Names match in
    any case: one page writes both "Cyberhero" and "CyberHero"."""
    rows = {n.lower(): {"name": n, "series_wins": 0, "series_losses": 0, "map_wins": 0, "map_losses": 0} for n in members}
    for m in pool:
        a, b = ((o or "").lower() for o in m["opponents"])
        if a in rows and b in rows and sum(m["score"]):
            for i, name in enumerate((a, b)):
                mine, theirs = m["score"][i], m["score"][1 - i]
                t = rows[name]
                t["series_wins"] += mine > theirs
                t["series_losses"] += mine < theirs
                t["map_wins"] += mine
                t["map_losses"] += theirs
    return sorted(rows.values(), key=lambda t: (-t["series_wins"], t["series_losses"], t["map_losses"] - t["map_wins"],
                                                t["name"].lower()))  # fmt: skip


def layout_names(pages: dict[str, str]) -> set[str]:
    """The bracket layouts the pages use, e.g. Bracket/8U8L2DSL1D."""
    return {params(b).get("1", "").strip() for t in pages.values() for _, b in blocks(COMMENT.sub("", t), "Bracket")} - {""}


def structure(pages: dict[str, str], layouts: dict[str, list[dict]], now: float) -> dict:
    """Brackets, groups, upcoming matches, rosters and every match of the event page and its stage pages. A bracket or
    group is titled by the nearest heading above it, else by its page's last part."""
    texts = {title: COMMENT.sub("", t) for title, t in pages.items()}
    lists = {
        title: [match(inner(v)) for _, b in blocks(text, "Matchlist") for k, v in params(b).items() if re.fullmatch(r"M\d+", k)]
        for title, text in texts.items()
    }  # fmt: skip
    found: dict = {"brackets": [], "groups": [], "upcoming": [], "rosters": [], "matches": [m for ms in lists.values() for m in ms]}
    rostered: set[str] = set()
    for title, text in texts.items():
        heads = [(h.start(), h[2]) for h in HEADING.finditer(text)]

        def titled(at: int) -> str:
            return next((h for o, h in reversed(heads) if o < at), title.rsplit("/", 1)[-1])

        for at, body in blocks(text, "Bracket"):
            slots = layouts.get(params(body).get("1", "").strip())
            if slots:
                tree = bracket(body, slots)
                found["brackets"].append({"title": titled(at), **tree})
                found["matches"] += [m for s in tree["sections"] for r in s["rounds"] for m in r["matches"]]
        for at, body in blocks(text, "GroupStandings"):
            p = params(body)
            members = [n for n in (opponent(v) for k, v in p.items() if k.isdigit()) if n]
            stage = p.get("stages", "").replace("{{FULLPAGENAME}}", title).replace("_", " ").strip()
            pool = lists[title] + (lists.get(stage, []) if stage != title else [])  # groups play as match lists
            found["groups"].append({"title": titled(at), "rows": group_rows(members, pool)})
        for _, body in blocks(text, "TeamParticipants"):
            for _, team in blocks(body, "Opponent"):
                p = params(team)
                name = p.get("1", "").strip()
                if not name or name in rostered:
                    continue
                rostered.add(name)
                people = [params(b) for _, b in blocks(p.get("players", ""), "Person")]
                found["rosters"].append({"name": name, "players": [
                    {"handle": q.get("1", "").strip(), "role": q.get("role") or None, "sub": q.get("status") == "sub"}
                    for q in people if q.get("1", "").strip()]})  # fmt: skip
    found["upcoming"] = sorted(
        (m for m in found["matches"]
         if None not in m["opponents"] and m["time"] is not None and m["time"] >= now - STALE and not played(m)),
        key=lambda m: m["time"],
    )[:UPCOMING]  # fmt: skip
    return found


def identify(found: dict, games: list[dict], teams: list[dict]) -> dict:
    """Give every Liquipedia team its Dota team id (0 when unknown): from a played map whose match id is among the
    games (`team1side` says which side the first team was), else by name, any case, among the league's teams."""
    label = lambda o: o["name"] if isinstance(o, dict) else o  # noqa: E731
    by_game = {g["match_id"]: g for g in games}
    ids: dict[str, int] = {}
    for m in found["matches"]:
        first, second = (label(o) for o in m["opponents"])
        for mp in m["maps"]:
            g = by_game.get(mp["match_id"])
            if g and first and second and mp["team1side"] in ("radiant", "dire"):
                a, b = ("radiant", "dire") if mp["team1side"] == "radiant" else ("dire", "radiant")
                ids.setdefault(first.lower(), g[a]["team_id"])  # any case, as in group_rows
                ids.setdefault(second.lower(), g[b]["team_id"])
    by_name = {t["name"].strip().lower(): t["team_id"] for t in teams if t.get("name")}

    def team_id(name: str | None) -> int:
        return (ids.get(name.lower()) or by_name.get(name.strip().lower()) or 0) if name else 0

    def fix(m: dict) -> None:
        m["opponents"] = [o if isinstance(o, dict) else {"name": o, "team_id": team_id(o)} for o in m["opponents"]]

    every = found["matches"] + found["upcoming"]
    every += [m for b in found["brackets"] for s in b["sections"] for r in s["rounds"] for m in r["matches"]]
    for m in every:
        fix(m)
    for g in found["groups"]:
        for r in g["rows"]:
            r["team_id"] = team_id(r["name"])
    for r in found["rosters"]:
        r["team_id"] = team_id(r["name"])
    return found
