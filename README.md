# DotAnalyst

A local Dota 2 stats site for the players I care about. There are plenty of stat sites already, but I often want numbers they don't show. This started with an amateur tournament where I wanted to analyse the opposing teams thoroughly.

How it works:
- Match data comes from Valve's Steam Web API.
- The [OpenDota API](https://docs.opendota.com) provides the salt each match's replay URL needs.
- Replays are parsed by [odota/parser](https://github.com/odota/parser), OpenDota's replay parser, running locally in Docker.
