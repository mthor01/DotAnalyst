# DotAnalyst

A local Dota 2 stats site for the players I care about. There are plenty of stat sites already, but I often want numbers they don't show. This started with an amateur tournament where I wanted to analyse the opposing teams thoroughly.

How it works:
- Match data comes from Valve's Steam Web API.
- The salt each match's replay URL needs comes from Valve's game coordinator, asked by a second Steam account (`steam/salts.mjs`), or else from the [OpenDota API](https://docs.opendota.com).
- Replays are parsed by [odota/parser](https://github.com/odota/parser), OpenDota's replay parser, running locally in Docker.

## Setup

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 itself), [Node.js](https://nodejs.org) and [Docker Desktop](https://www.docker.com/products/docker-desktop/).

1. `uv sync` installs the Python packages.
2. Start the replay parser once; Docker restarts it from then on:
   `docker run -d -p 127.0.0.1:5600:5600 --restart unless-stopped --name parser odota/parser:latest`
   The port stays on localhost because the parser fetches any URL it is given.
3. Get a Steam Web API key at <https://steamcommunity.com/dev/apikey> and put it in a file `.env` in the repo folder:
   ```
   STEAM_API_KEY=your-key
   ```
   `.env` is gitignored; never commit it. The commands and the server read it when it is there. Without it the site still runs and step 4 still works, but no new matches are fetched.
4. `uv run python -m dotanalyst sync-constants` fetches hero and item names.
5. `cd frontend`, `npm install`, `npm run build`, `cd ..` builds the site.
6. `uv run uvicorn dotanalyst.api:app` starts it at <http://127.0.0.1:8000>. While it runs it checks every minute for new matches and downloads and parses their replays.

Every command below runs from the repo folder.

## Adding players

A player is tracked by their Dota account id, the short number (8 to 10 digits), not the 17-digit Steam id. To find it:

- in Dota 2, open the player's profile: it is the **Friend ID** under their name;
- or take the number at the end of their [OpenDota](https://www.opendota.com), [Dotabuff](https://www.dotabuff.com) or [STRATZ](https://stratz.com) profile URL, e.g. `opendota.com/players/12345678`;
- or, from a Steam profile URL `steamcommunity.com/profiles/7656119...`, subtract 76561197960265728 from that number.

Then add it with **Add profile** at the top of the site; it takes the Steam id too. Or from the command line, with an optional name for the Account menu:

```
uv run python -m dotanalyst add-account 12345678 "Player 1"
uv run python -m dotanalyst sync
```

`sync` fetches the account's last 500 matches at once; the running server picks a new account up within a minute either way. On a profile, **Add frequent teammates** adds every player with 10 or more games on that player's team in their last 500 matches. The player must have **Expose Public Match Data** on (Dota 2 → Settings → Options → Social), or Steam returns no matches; `status` then says so. Other commands: `remove-account <id>` stops tracking, `status` lists the tracked accounts and replay counts.

## Keeping player ids out of the repo

`git config core.hooksPath .githooks` once per clone turns on a pre-commit check that refuses files holding the account id or Steam id of any player in the local database. Test fixtures use made-up ids and names.

## Scouting league teams

The Teams tab of the Tournaments page shows, for every team of the tracked tournaments, which heroes are banned against it, whether it picks them when they are open, and who plays what. The replays of games from the last 30 days are fetched by the running server; an older game's when you ask for it on the page; with replays a team page also shows where each player wards and where the team walks in the first seconds of a game.

`uv run python -m dotanalyst sync-leagues` fetches the league's games; the first run takes about half an hour. After that, the running server gets the newest ones every minute, and the button "Check for new league games" on the Tournaments page at once.

### Adding a tournament

A new database tracks the leagues in `LEAGUES` at the top of [`dotanalyst/steam.py`](dotanalyst/steam.py) (the Reincarnation league, seasons 6 to 8). To add another:

1. Find the league id: it is the number in the league's URL on [OpenDota](https://www.opendota.com/leagues) (`opendota.com/leagues/12345`) or [Dotabuff](https://www.dotabuff.com/esports/leagues) (`dotabuff.com/esports/leagues/12345-my-cup`). Only leagues Valve itself lists (the ones with an in-game ticket) can be fetched; those sites list exactly those.
2. Enter it on the Tournaments page under **Add tournament**. Its name comes from OpenDota.
3. The running server reads its games on its next check for league games; `sync-leagues` does it at once.

Steam lists only the newest 500 games of a league, so a bigger league misses its oldest games.

## Replay salts from a second Steam account

Optional; without it OpenDota is asked, which can take hours to know a new match.

1. `npm install` in `steam/`.
2. Put the account in `.env` as `STEAM_ALT_USER` and `STEAM_ALT_PASSWORD`. Use an account you do not play on: the script shows it as playing Dota 2.
3. Run `node --env-file=.env steam/salts.mjs` once and type the Steam Guard code it asks for. It prints `{}` when the login worked.
4. Restart the server.
