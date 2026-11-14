# DotAnalyst

A local Dota 2 stats site for the players I care about. There are plenty of stat sites already, but I often want numbers they don't show. This started with an amateur tournament where I wanted to analyse the opposing teams thoroughly.

How it works:
- Match data comes from Valve's Steam Web API.
- The salt each match's replay URL needs comes from Valve's game coordinator, asked by a second Steam account (`steam/salts.mjs`), or else from the [OpenDota API](https://docs.opendota.com).
- Replays are parsed by [odota/parser](https://github.com/odota/parser), OpenDota's replay parser, running locally in Docker.

## Scouting league teams

The Teams page shows, for every team of the Reincarnation league (seasons 6 to 8), which heroes are banned against it, whether it picks them when they are open, and who plays what.

`uv run --env-file .env python -m dotanalyst sync-leagues` fetches the league's games; the first run takes about half an hour. After that, the button "Check for new league games" on the Teams page gets the newest ones.

## Replay salts from a second Steam account

Optional; without it OpenDota is asked, which can take hours to know a new match.

1. `npm install` in `steam/`.
2. Put the account in `.env` as `STEAM_ALT_USER` and `STEAM_ALT_PASSWORD`. Use an account you do not play on: the script shows it as playing Dota 2.
3. Run `node --env-file=.env steam/salts.mjs` once and type the Steam Guard code it asks for. It prints `{}` when the login worked.
4. Restart the server.
