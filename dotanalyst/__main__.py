import argparse
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import func, select

from .db import Account, Match, open_session
from .replay import ReplayError, parse_replay
from .steam import SteamError, sync, sync_constants


def main() -> int:
    parser = argparse.ArgumentParser(prog="dotanalyst")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add-account", help="track a Steam account (32-bit friend id)")
    add.add_argument("account_id", type=int)
    add.add_argument("label", nargs="?")
    remove = sub.add_parser("remove-account", help="stop tracking an account; its data stays")
    remove.add_argument("account_id", type=int)
    sub.add_parser("status", help="show what is stored")
    sub.add_parser("sync", help="fetch new matches of all tracked accounts")
    sub.add_parser("sync-constants", help="fetch hero and item names")
    replay = sub.add_parser("parse-replay", help="parse a .dem named <match_id>.dem")
    replay.add_argument("dem", type=Path)
    args = parser.parse_args()

    key = os.environ.get("STEAM_API_KEY", "")
    if args.command in ("sync", "sync-constants") and not key:
        print("error: STEAM_API_KEY is not set (run with: uv run --env-file .env ...)", file=sys.stderr)
        return 1

    with open_session() as session:
        if args.command == "add-account":
            account = session.get(Account, args.account_id) or Account(account_id=args.account_id)
            account.active = True
            account.label = args.label or account.label
            session.add(account)
            session.commit()
            print(f"tracking {account.account_id} ({account.label or 'no label'})")
        elif args.command == "remove-account":
            account = session.get(Account, args.account_id)
            if account is None:
                print(f"account {args.account_id} is not tracked", file=sys.stderr)
                return 1
            account.active = False
            session.commit()
            print(f"stopped tracking {account.account_id}")
        elif args.command == "status":
            for account in session.scalars(select(Account).order_by(Account.account_id)):
                flags = [] if account.active else ["inactive"]
                if account.history_exposed is False:
                    flags.append("match history not exposed")
                print(f"account {account.account_id} {account.label or ''} {' '.join(flags)}".rstrip())
            states = dict(
                session.execute(select(Match.replay_state, func.count()).group_by(Match.replay_state)).all()
            )
            print(f"matches: {sum(states.values())}, parsed: {states.get('parsed', 0)}")
            for state, count in sorted(states.items()):
                print(f"  replay {state}: {count}")
        elif args.command in ("sync", "sync-constants"):
            try:
                with httpx.Client() as client:
                    if args.command == "sync-constants":
                        heroes, items = sync_constants(session, client, key)
                        print(f"{heroes} heroes and {items} items stored")
                        return 0
                    counts = sync(session, client, key)
            except SteamError as error:
                print(f"error: {error} (matches stored so far are kept)", file=sys.stderr)
                return 1
            for account_id, new in counts.items():
                print(f"account {account_id}: " + ("match history not exposed" if new is None else f"{new} new"))
            print(f"{sum(new or 0 for new in counts.values())} new")
        elif args.command == "parse-replay":
            try:
                with httpx.Client() as client:
                    out = parse_replay(session, args.dem, client)
            except (ReplayError, OSError, httpx.HTTPError) as error:
                print(f"error: {error}", file=sys.stderr)
                return 1
            print(f"stored {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
