"""Out-of-band human approvals. ChatGPT can request, but cannot approve."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .settings import Settings, load_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    created INTEGER NOT NULL,
    expires INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','approved','consumed'))
);
CREATE TABLE IF NOT EXISTS audit (
    ts INTEGER NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    result TEXT NOT NULL
);
"""


@contextmanager
def connect(settings: Settings):
    # The state directory MUST be owned by the unprivileged service user.
    settings.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if settings.state_dir.is_symlink():
        raise PermissionError("Symlinked state directory prohibited")
    dbpath = settings.state_dir / "agent.sqlite3"
    with sqlite3.connect(dbpath, timeout=10, isolation_level=None) as db:
        db.executescript(SCHEMA)
        yield db


def audit(settings: Settings, actor: str, kind: str, target: str, result: str) -> None:
    with connect(settings) as db:
        db.execute(
            "INSERT INTO audit(ts,actor,kind,target,result) VALUES (?,?,?,?,?)",
            (int(time.time()), actor[:200], kind[:80], target[:500], result[:120]),
        )


def request(settings: Settings, actor: str, kind: str, target: str) -> dict:
    rid = str(uuid.uuid4())
    now = int(time.time())
    with connect(settings) as db:
        db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?)",
                   (rid, actor, kind, target, now, now + 300, "pending"))
    audit(settings, actor, kind, target, "pending")
    return {
        "request_id": rid, "kind": kind, "target": target, "expires_in_seconds": 300,
        "next_step": "Server owner approves locally with server-mcp-approve approve REQUEST_ID",
    }


def consume(settings: Settings, actor: str, request_id: str) -> tuple[str, str]:
    now = int(time.time())
    with connect(settings) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT actor,kind,target,state,expires FROM requests WHERE id=?", (request_id,)
        ).fetchone()
        if row is None or row[0] != actor or row[3] != "approved" or row[4] < now:
            db.execute("ROLLBACK")
            raise PermissionError("Request not approved, expired, or owned by a different account")
        changed = db.execute(
            "UPDATE requests SET state='consumed' WHERE id=? AND state='approved'",
            (request_id,),
        ).rowcount
        if changed != 1:
            db.execute("ROLLBACK")
            raise PermissionError("Request already consumed")
        db.execute("COMMIT")
        return row[1], row[2]


def approve(settings: Settings, request_id: str) -> bool:
    with connect(settings) as db:
        row = db.execute(
            "SELECT actor,kind,target,state,expires FROM requests WHERE id=?", (request_id,)
        ).fetchone()
        if row is None or row[3] != "pending" or row[4] < int(time.time()):
            print("Request does not exist or has expired", file=sys.stderr)
            return False
        print(f"Actor: {row[0]}\nAction: {row[1]}\nTarget: {row[2]}\nID: {request_id}")
        answer = input(f"Type APPROVE {request_id} to authorize once: ")
        if answer != f"APPROVE {request_id}":
            return False
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute(
            "UPDATE requests SET state='approved' WHERE id=? AND state='pending' AND expires>=?",
            (request_id, int(time.time())),
        ).rowcount
        db.execute("COMMIT")
        if changed:
            audit(settings, "local-operator", "approval", request_id, "approved")
        return bool(changed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local human-only operation approval")
    parser.add_argument("command", choices=["list", "approve"])
    parser.add_argument("request_id", nargs="?")
    options = parser.parse_args()
    settings = load_settings()
    if options.command == "list":
        with connect(settings) as db:
            for item in db.execute(
                "SELECT id,actor,kind,target,expires,state FROM requests "
                "WHERE expires >= ? ORDER BY created DESC LIMIT 25", (int(time.time()),)
            ):
                print(json.dumps(dict(zip(("id","actor","kind","target","expires","state"), item))))
    elif not options.request_id or not approve(settings, options.request_id):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
