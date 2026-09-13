#!/usr/bin/env python3
"""Build the tracker's data file from the submissions/ and reviews/ folders.

Usage:
    python3 scripts/build.py                      # repo root -> site/data/index.json
    python3 scripts/build.py --root fixtures \
        --out site/data/sample-index.json         # sample data for the mockup

Every submission is a folder:  submissions/<member>/<folder>/submission.md
Every review is a file:        reviews/<member>/<folder>.md

Dates come from git (first commit that added the folder = submitted,
last commit that touched it = updated). A `submitted:` or `updated:` line
in the front matter overrides git, which is how the fixtures carry dates.
No third-party packages; only the standard library.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSES = ("submitted", "in-review", "changes-requested", "approved")
COMMENT_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s*$")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_front_matter(text):
    """Split a markdown file into (dict of key: value, body). Minimal on purpose."""
    meta, body = {}, text
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            head, body = parts[0][3:], parts[1]
            body = body.lstrip("\n")
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
    return meta, body.strip()


def git(args, cwd):
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def git_dates(folder, cwd):
    """(submitted_iso, updated_iso, first_author) from git, or (None, None, None)."""
    rel = os.path.relpath(folder, cwd)
    first = git(["log", "--diff-filter=A", "--reverse", "--format=%aI%x09%an", "--", rel], cwd)
    last = git(["log", "-1", "--format=%aI", "--", rel], cwd)
    if not first:
        return None, None, None
    date, author = first.splitlines()[0].split("\t", 1)
    return date[:10], (last or date)[:10], author


def fs_dates(folder):
    """Fallback when nothing is committed yet: use file modification times."""
    times = []
    for root, _, files in os.walk(folder):
        for name in files:
            times.append(os.path.getmtime(os.path.join(root, name)))
    if not times:
        return None, None
    fmt = lambda t: dt.datetime.fromtimestamp(t).date().isoformat()
    return fmt(min(times)), fmt(max(times))


def parse_review(path):
    meta, body = parse_front_matter(read(path))
    comments, current = [], None
    for line in body.splitlines():
        m = COMMENT_RE.match(line)
        if m:
            current = {"date": m.group(1), "author": m.group(2), "text": ""}
            comments.append(current)
        elif current is not None:
            current["text"] += line + "\n"
    for c in comments:
        c["text"] = c["text"].strip()
    status = meta.get("status", "in-review")
    if status not in STATUSES:
        print(f"warning: {path}: unknown status '{status}', using in-review", file=sys.stderr)
        status = "in-review"
    return {
        "status": status,
        "reviewer": meta.get("reviewer", comments[-1]["author"] if comments else ""),
        "comments": comments,
    }


def list_files(folder, root):
    out = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if name.startswith(".") or name == "submission.md" or os.path.isdir(p):
            continue
        out.append({"name": name, "path": os.path.relpath(p, root), "size": os.path.getsize(p)})
    return out


def build(root):
    members = json.load(open(os.path.join(REPO, "members.json")))
    assignments = json.load(open(os.path.join(REPO, "assignments.json")))["assignments"]
    by_id = {m["id"]: m for m in members["members"]}
    subs_dir = os.path.join(root, "submissions")
    revs_dir = os.path.join(root, "reviews")
    submissions = []

    for member_id in sorted(os.listdir(subs_dir)) if os.path.isdir(subs_dir) else []:
        mdir = os.path.join(subs_dir, member_id)
        if not os.path.isdir(mdir):
            continue
        if member_id not in by_id:
            print(f"warning: submissions/{member_id} is not in members.json, skipping", file=sys.stderr)
            continue
        for folder in sorted(os.listdir(mdir)):
            sdir = os.path.join(mdir, folder)
            sub_md = os.path.join(sdir, "submission.md")
            if not os.path.isdir(sdir) or not os.path.exists(sub_md):
                continue
            meta, body = parse_front_matter(read(sub_md))
            submitted, updated, author = git_dates(sdir, root)
            source = "git"
            if not submitted:
                submitted, updated = fs_dates(sdir)
                source = "filesystem"
            if meta.get("submitted"):
                # Front matter overrides both dates (the fixtures rely on this).
                # The git author goes with the git dates, so drop it too and
                # let submitted_by fall back to the member's name.
                submitted, source = meta["submitted"], "front-matter"
                updated = meta.get("updated", submitted)
                author = None
            elif meta.get("updated"):
                updated = meta["updated"]
            updated = updated or submitted

            review_path = os.path.join(revs_dir, member_id, folder + ".md")
            review = parse_review(review_path) if os.path.exists(review_path) else None

            submissions.append({
                "id": f"{member_id}/{folder}",
                "member": member_id,
                "folder": folder,
                "title": meta.get("title", folder),
                "assignment": meta.get("assignment", ""),
                "submitted": submitted,
                "updated": updated,
                "dates_from": source,
                "submitted_by": meta.get("submitted_by") or author or by_id[member_id]["name"],
                "notes": meta.get("notes", ""),
                "body": body,
                "files": list_files(sdir, root),
                "status": review["status"] if review else "submitted",
                "review": review,
            })

    submissions.sort(key=lambda s: (s["submitted"] or "", s["member"]))
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "group": members.get("group", "Group"),
        "repo": members.get("repo", ""),
        "branch": members.get("branch", "main"),
        "members": members["members"],
        "assignments": assignments,
        "statuses": list(STATUSES),
        "submissions": submissions,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=REPO, help="folder holding submissions/ and reviews/ (default: repo root)")
    ap.add_argument("--out", default=os.path.join(REPO, "site", "data", "index.json"))
    args = ap.parse_args()
    data = build(os.path.abspath(args.root))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    n = len(data["submissions"])
    print(f"wrote {os.path.relpath(args.out, REPO)}: {n} submission{'s' if n != 1 else ''}")


if __name__ == "__main__":
    main()
