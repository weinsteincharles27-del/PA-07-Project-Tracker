#!/usr/bin/env python3
"""Create a submission folder, commit it, and (optionally) push it.

    python3 scripts/submit.py --as bryan --assignment "Data memo" --title "Sources and cadence" memo.md sources.csv --push

Makes submissions/<member>/<today>-<slug>/ with a submission.md and copies of
the files, then commits with the message "<Name>: <title> (<assignment>)".
The commit date is the submission date the tracker shows.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slug(s):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))[:40] or "submission"


def main():
    members = json.load(open(os.path.join(REPO, "members.json")))["members"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as", dest="member", required=True, choices=[m["id"] for m in members], help="your member id")
    ap.add_argument("--assignment", required=True, help="assignment name, typed exactly as it was given to you")
    ap.add_argument("--title", required=True)
    ap.add_argument("--notes", default="", help="one-line note for the reviewer")
    ap.add_argument("--body", default="", help="longer description (markdown)")
    ap.add_argument("--push", action="store_true", help="git push after committing")
    ap.add_argument("--no-commit", action="store_true", help="only create the folder")
    ap.add_argument("files", nargs="*", help="files to include")
    args = ap.parse_args()

    name = next(m["name"] for m in members if m["id"] == args.member)
    if not args.assignment.strip() or not args.title.strip():
        sys.exit("--assignment and --title cannot be blank")
    # Check every input before touching the repo, so a typo cannot leave a
    # half-created folder behind.
    missing = [src for src in args.files if not os.path.isfile(src)]
    if missing:
        sys.exit("not a file: " + ", ".join(missing) + "\nnothing was created")
    folder = f"{dt.date.today().isoformat()}-{slug(args.title)}"
    path = os.path.join(REPO, "submissions", args.member, folder)
    if os.path.exists(path):
        sys.exit(f"{os.path.relpath(path, REPO)} already exists; pick a different title")
    member_dir = os.path.dirname(path)
    new_member_dir = not os.path.isdir(member_dir)
    os.makedirs(path)
    try:
        with open(os.path.join(path, "submission.md"), "w", encoding="utf-8") as f:
            f.write(f"---\ntitle: {args.title}\nassignment: {args.assignment}\n")
            if args.notes:
                f.write(f"notes: {args.notes}\n")
            f.write("---\n")
            if args.body:
                f.write(args.body.strip() + "\n")
        for src in args.files:
            shutil.copy2(src, os.path.join(path, os.path.basename(src)))
    except BaseException:
        # Anything that fails mid-write (disk error, Ctrl-C) removes what was
        # started, including a member folder that did not exist before.
        shutil.rmtree(member_dir if new_member_dir else path, ignore_errors=True)
        raise
    rel = os.path.relpath(path, REPO)
    print(f"created {rel}/ with submission.md and {len(args.files)} file(s)")
    if args.no_commit:
        return
    msg = f"{name}: {args.title} ({args.assignment})"
    subprocess.run(["git", "add", rel], cwd=REPO, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=REPO, check=True)
    print(f"committed: {msg}")
    if args.push:
        subprocess.run(["git", "push"], cwd=REPO, check=True)
        print("pushed")
    else:
        print("run `git push` to submit it")


if __name__ == "__main__":
    main()
