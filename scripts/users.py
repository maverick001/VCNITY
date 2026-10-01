"""Make and manage sign-in accounts. There is no sign-up page; accounts come from here.

    uv run --project app python app/scripts/users.py demo                      # one account per role, newest job
    uv run --project app python app/scripts/users.py add sam community --job 1  # asks for a password
    uv run --project app python app/scripts/users.py list
    uv run --project app python app/scripts/users.py password sam
    uv run --project app python app/scripts/users.py remove sam

A community or client account belongs to one job and sees nothing else. A
facilitator or analyst account sees every job.
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vcnity import auth, db  # noqa: E402
from vcnity.models import Job, User  # noqa: E402


def _ask_password() -> str:
    while True:
        pw = getpass.getpass(f"Password (at least {auth.MIN_PASSWORD} characters): ")
        if pw == getpass.getpass("Again: "):
            return pw
        print("Those didn't match. Try again.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="make an account")
    add.add_argument("username")
    add.add_argument("role", choices=auth.ROLES)
    add.add_argument("--job", type=int, help="the job a community or client account belongs to")
    sub.add_parser("list", help="show every account")
    pw = sub.add_parser("password", help="set a new password")
    pw.add_argument("username")
    rm = sub.add_parser("remove", help="delete an account")
    rm.add_argument("username")
    demo = sub.add_parser("demo", help="one account per role, with printed passwords")
    demo.add_argument("--job", type=int, help="the job for the community and client accounts (default: newest)")
    args = ap.parse_args()

    db.init_db()
    try:
        with db.session() as s:
            if args.cmd == "add":
                user = auth.create_user(s, args.username, _ask_password(), args.role, args.job)
                print(f"Made {user.username} ({user.role}" + (f", job {user.job_id})" if user.job_id else ")"))
            elif args.cmd == "list":
                jobs = {j.id: j.name for j in s.query(Job)}
                for u in s.query(User).order_by(User.role, User.username):
                    where = f"job {u.job_id} · {jobs.get(u.job_id, '?')}" if u.job_id else "every job"
                    print(f"{u.username:<20} {u.role:<12} {where}")
            elif args.cmd == "password":
                auth.set_password(s, args.username, _ask_password())
                print("Password changed.")
            elif args.cmd == "remove":
                n = s.query(User).filter_by(username=args.username.strip().lower()).delete()
                print("Removed." if n else f"No account called {args.username}.")
            elif args.cmd == "demo":
                job = s.get(Job, args.job) if args.job else s.query(Job).order_by(Job.id.desc()).first()
                if job:
                    print(f"Community and client accounts belong to job {job.id} · {job.name}\n")
                for role in auth.ROLES:
                    if s.query(User).filter_by(username=role).one_or_none():
                        print(f"{role:<12} already exists — use 'password {role}' to reset it")
                        continue
                    if role not in auth.STAFF and job is None:
                        print(f"{role:<12} skipped — no job yet. Make one as the facilitator, then run demo again")
                        continue
                    password = secrets.token_urlsafe(9)
                    auth.create_user(s, role, password, role, job.id if job else None)
                    print(f"{role:<12} password: {password}")
                print("\nWrite these down: they aren't shown again.")
    except (ValueError, KeyError) as e:
        print(f"Couldn't do that: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
