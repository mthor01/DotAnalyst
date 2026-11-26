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
    """One match (a `{{Match}}` or a match page's `{{MatchPage}}`): the two teams, its time, its Dota match ids, the
    maps (skipped ones dropped), the score and the winner (0, 1): the Match's own `winner=`, else a team that won more
    than half the listed maps. A `{{ApiMap|matchid=…|reversed=true}}` names only its game, the first team Dire when
    reversed: who won comes from our games (identify)."""
    p = params(body)
    ids = {n: int(v) for n, v in numbered(p, "matchid") if v.isdigit()}
    maps = []
    for n, value in numbered(p, "map"):
        mp = params(inner(value))
        if mp.get("finished") == "skip":
            continue
        won, own = mp.get("winner"), mp.get("matchid", "")
        side = mp.get("team1side") or (("dire" if mp.get("reversed") == "true" else "radiant") if own else None)
        maps.append({"team1side": side, "winner": int(won) - 1 if won in ("1", "2") else None,
                     "match_id": int(own) if own.isdigit() else ids.get(n)})  # fmt: skip
    m = {
        "opponents": [opponent(p.get("opponent1", "")), opponent(p.get("opponent2", ""))], "time": when(p.get("date", "")),
        "match_ids": [mp["match_id"] for mp in maps if mp["match_id"]] or list(ids.values()), "maps": maps,
        "score": [0, 0], "winner": int(p["winner"]) - 1 if p.get("winner") in ("1", "2") else None,
        # Bo3 and the like: the match's `bestof=`, else every map listed, skipped ones too
        "best_of": int(p["bestof"]) if p.get("bestof", "").isdigit() else len(numbered(p, "map")) or None,
    }  # fmt: skip
    return settle(m)


def settle(m: dict) -> dict:
    """The score from the maps won, and the winner when not given: a team that won more than half the listed maps."""
    maps = m["maps"]
    m["score"] = [sum(mp["winner"] == i for mp in maps) for i in (0, 1)]
    if m["winner"] is None and maps and max(m["score"]) > len(maps) / 2:
        m["winner"] = 0 if m["score"][0] > m["score"][1] else 1
    return m


def played(m: dict) -> bool:
    """A map with a winner or with a Dota match id has been played (or is being played)."""
    return m["winner"] is not None or any(mp["winner"] is not None or mp["match_id"] for mp in m["maps"])


def heading(text: str) -> str:
    """A heading's text: `{{Stage|Playoffs}}` is Playoffs, `[[Page|Group A]]` Group A."""
    text = re.sub(r"\{\{[^{}]*?\|([^{}|]*)\}\}", r"\1", text)
    return re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text).strip()


def slot(key: str) -> str | None:
    """`R1M2` is the layout's `R01-M002`; RxMBR stays."""
    if key == "RxMBR":
        return key
    m = re.fullmatch(r"R(\d+)M(\d+)", key)
    return f"R{int(m[1]):02d}-M{int(m[2]):03d}" if m else None


def empty(value: str) -> bool:
    return not any(k.startswith("opponent") or k.startswith("map") for k in params(inner(value)))


def listed(key: str) -> str | None:
    """A match list's `M3` is `0003` on its match page."""
    return f"{int(key[1:]):04d}" if re.fullmatch(r"M\d+", key) else None


def body_of(value: str, page: str | None) -> str:
    """What a slot's match is read from: its own `{{MatchPage}}` when the slot is empty and that page was read."""
    own = next((b for _, b in blocks(page, "MatchPage")), None) if page and empty(value) else None
    return own or inner(value)


def match_pages(pages: dict[str, str]) -> list[str]:
    """The pages of the matches a bracket or match list leaves empty: newer Liquipedia pages keep each on
    `Match:ID <bracket> R01-M001` or `Match:ID <list> 0001`."""
    found = []
    for text in pages.values():
        for template, name in (("Bracket", slot), ("Matchlist", listed)):
            for _, body in blocks(COMMENT.sub("", text), template):
                p = params(body)
                for key, value in p.items():
                    sid = name(key)
                    if sid and p.get("id") and empty(value):
                        found.append(f"Match:ID {p['id']} {sid}")
    return list(dict.fromkeys(found))


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


def final_slot(slots: list[dict]) -> str | None:
    """The layout's final: its one root, else the one match that feeds no other. None when there are several, as in a
    qualifier, where each advances a team."""
    roots = [s["id"] for s in slots if s["root"]]
    if roots:
        return roots[0] if len(roots) == 1 else None
    fed = {f for s in slots for f in (s["toupper"], s["tolower"]) if f}
    last = [s["id"] for s in slots if s["id"] and s["id"] != "RxMBR" and s["id"] not in fed]
    return last[0] if len(last) == 1 else None


def bracket(body: str, slots: list[dict], pages: dict[str, str] | None = None) -> dict:
    """The tree: per section (upper, lower) its rounds in order, each with its matches and the ids feeding them. A
    round is named by the page's own `R<r>M<m>header=`, else by the layout's header code. The bracket reset shows only
    when it was played."""
    p = params(body)
    matches, headers = {}, {}
    for key, value in p.items():
        if key.endswith("header") and slot(key.removesuffix("header")):
            headers[slot(key.removesuffix("header"))] = value
        elif sid := slot(key):
            matches[sid] = match(body_of(value, (pages or {}).get(f"Match:ID {p.get('id')} {sid}")))
    sections: dict[str, dict[int, dict]] = {}
    final = None  # the final, or the bracket reset once played: its winner wins the bracket
    final_id = final_slot(slots)
    for spot in slots:
        sid = spot["id"] or ""
        m = matches.get(sid) or match("Match")
        if sid == "RxMBR" and not played(m):
            continue
        number = re.match(r"R(\d+)", sid)
        index = 999 if sid == "RxMBR" or not number else int(number[1])
        r = sections.setdefault(spot["section"], {}).setdefault(index, {"page": None, "code": None, "matches": []})
        r["page"] = r["page"] or headers.get(sid)
        r["code"] = r["code"] or spot["header"]
        r["matches"].append({**m, "id": sid, "feeders": [f for f in (spot["toupper"], spot["tolower"]) if f]})
        if final_id and sid in (final_id, "RxMBR"):
            final = m
    return {"final": final, "sections": [
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
        title: [
            match(body_of(v, pages.get(f"Match:ID {p.get('id')} {listed(k)}")))
            for _, b in blocks(text, "Matchlist") for p in [params(b)] for k, v in p.items() if listed(k)
        ]
        for title, text in texts.items()
    }  # fmt: skip
    found: dict = {"brackets": [], "groups": [], "upcoming": [], "rosters": [], "matches": [m for ms in lists.values() for m in ms]}
    rostered: set[str] = set()
    for title, text in texts.items():
        heads = [(h.start(), h[2]) for h in HEADING.finditer(text)]

        def titled(at: int) -> str:
            return next((heading(h) for o, h in reversed(heads) if o < at), title.rsplit("/", 1)[-1])

        for at, body in blocks(text, "Bracket"):
            slots = layouts.get(params(body).get("1", "").strip())
            if slots:
                tree = bracket(body, slots, pages)
                found["brackets"].append({"title": titled(at), **tree})
                found["matches"] += [m for s in tree["sections"] for r in s["rounds"] for m in r["matches"]]
        for at, body in blocks(text, "GroupStandings"):
            p = params(body)
            members = [n for n in (opponent(v) for k, v in p.items() if k.isdigit()) if n]
            stage = p.get("stages", "").replace("{{FULLPAGENAME}}", title).replace("_", " ").strip()
            pool = lists[title] + (lists.get(stage, []) if stage != title else [])  # groups play as match lists
            # members and pool stay until identify has the games' winners; the page leaves them out
            found["groups"].append({"title": titled(at), "rows": group_rows(members, pool), "members": members, "pool": pool})
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
    # the last bracket final (a group may be a bracket too) names the winner; one whose games name only their ids is
    # kept, for Explore to decide from our games (decide)
    finals = [b.pop("final") for b in found["brackets"] if b.get("final")]
    found["final"] = max(enumerate(finals), key=lambda f: (f[1]["time"] or 0, f[0]))[1] if finals else None
    found["winner"] = winner(pages) or (decide(found["final"], []) if found["final"] else None)
    return found


def decide(final: dict, games: list[dict]) -> str | None:
    """The winner of a final: its own, else from these games' results (match_id, radiant_win) for maps without one."""
    known = {g["match_id"]: g.get("radiant_win") for g in games}
    m = {**final, "maps": [dict(mp) for mp in final["maps"]]}
    for mp in m["maps"]:
        won = known.get(mp["match_id"])
        if mp["winner"] is None and won is not None and mp["team1side"] in ("radiant", "dire"):
            mp["winner"] = 0 if (mp["team1side"] == "radiant") == won else 1
    settle(m)
    if m["winner"] is None:
        return None
    name = m["opponents"][m["winner"]]
    return name if isinstance(name, str) else (name or {}).get("name")


def winner(pages: dict[str, str]) -> str | None:
    """The tournament's winner: the team of the first place-1 slot of a prize pool (`{{Slot|place=1|…}}`, older pages
    `{{prize pool slot|place=1|…}}`, a shared first place `place=1-2` too); None before it is known."""
    for text in pages.values():
        text = COMMENT.sub("", text)
        for _, body in sorted(blocks(text, "Slot") + blocks(text, "prize pool slot") + blocks(text, "Prize pool slot")):
            place = params(body).get("place", "").strip()
            if place == "1" or place.startswith("1-"):
                return next((name for _, b in blocks(body, "TeamOpponent") if (name := opponent("{{" + b + "}}"))), None)
    return None


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

    every = found["matches"] + found["upcoming"] + [m for g in found["groups"] for m in g.get("pool", [])]
    every += [m for b in found["brackets"] for s in b["sections"] for r in s["rounds"] for m in r["matches"]]
    for m in every:
        for mp in m["maps"]:  # a game Liquipedia names only by its id: who won, from ours
            g = by_game.get(mp["match_id"])
            if mp["winner"] is None and g and g.get("radiant_win") is not None and mp["team1side"] in ("radiant", "dire"):
                mp["winner"] = 0 if (mp["team1side"] == "radiant") == g["radiant_win"] else 1
        settle(m)
    for m in every:
        fix(m)
    for g in found["groups"]:
        if "pool" in g:
            g["rows"] = group_rows(g["members"], [{**m, "opponents": [label(o) for o in m["opponents"]]} for m in g["pool"]])
        for r in g["rows"]:
            r["team_id"] = team_id(r["name"])
    for r in found["rosters"]:
        r["team_id"] = team_id(r["name"])
    return found
