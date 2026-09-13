# PA-07 Project Tracker

A submission and review tracker that runs on git. Members submit work by
committing a folder. Admins review by committing a markdown file next to it.
A small static site reads the repo and shows a dashboard, a per-person
timeline, and a review thread for every submission. Dates come from git, so
they cannot be edited after the fact.

**Members:** Bryan, Aanika, Kiley, Kayla, Bode, Max, Charlie, Prof. Crain
**Admins (see and review everything):** Charlie, Prof. Crain

Mockups of every page are in [`mockups/`](mockups/), rendered with sample data:

| | |
|---|---|
| ![Admin dashboard](mockups/01-dashboard-admin.png) | ![Timeline](mockups/03-timeline-admin.png) |
| Admin dashboard: everyone's work, coverage by assignment | Timeline: one lane per person, with revisions |
| ![Review thread](mockups/05-submission-review.png) | ![Submit](mockups/08-submit-filled.png) |
| A submission with its review thread | The submit form and what it creates |
| ![File viewer](mockups/09-file-viewer.png) | |
| A PDF opened from the dashboard | |

## How submitting works

Every submission is one folder:

```
submissions/<your-id>/<YYYY-MM-DD>-<short-title>/
    submission.md      title, assignment, a note for the reviewer
    ...your files      anything: .md, .csv, .xlsx, .pdf, .ipynb, images
```

`submission.md` looks like this:

```markdown
---
title: Sources and update cadence
assignment: Data collection memo
notes: Second upload adds the Q2 FEC pull.
---
Optional longer description, in markdown.
```

The assignment is whatever you were asked to do, typed as a name. Type it
the same way each time (the Submit page suggests names already in use), since
the admins' coverage grid groups work by that exact name.

Three ways to get it into the repo. Pick whichever you are comfortable with.

1. **On GitHub, no git needed.** Open the site's Submit page, fill in the
   form, download the generated `submission.md`, then press *Upload on
   GitHub*. It opens GitHub's upload page pointed at your folder; drop in
   `submission.md` and your files and commit.
2. **Terminal.** Make the folder, save `submission.md` and your files in it,
   then `git add`, `git commit`, `git push`. The Submit page prints the exact
   commands.
3. **Helper script.** From the repo root:
   ```bash
   python3 scripts/submit.py --as bryan --assignment "Data collection memo" --title "Sources and update cadence" memo.md --push
   ```

If a folder has files but no `submission.md` (say, a quick web upload), it
still shows up: the title comes from the folder name and the assignment is
blank until a `submission.md` is added to the folder.

To revise a submission, change the files in the same folder and commit again.
The tracker shows both the original date and the latest revision date.
Renaming a submission folder resets its dates and detaches its review, since
the folder name is how the tracker identifies it, so revise in place instead.

Your member id is your first name in lowercase (`bryan`, `aanika`, `kiley`,
`kayla`, `bode`, `max`, `charlie`) or `prof-crain`. The full list is in
[`members.json`](members.json).

## How reviewing works

Admins review by writing one file per submission:

```
reviews/<member-id>/<submission-folder-name>.md
```

```markdown
---
status: changes-requested
reviewer: Prof. Crain
---

## 2026-09-05 Charlie

The FEC section stops at Q1. Please add the Q2 quarterly filing.

## 2026-09-07 Bryan

Re-uploaded with the Q2 pull.
```

`status` is one of `submitted`, `in-review`, `changes-requested`, or
`approved`. Each `## <date> <name>` heading is one comment in the thread.
Anyone can add a comment; only admins change the status. The submission page
on the site drafts this file for you and opens GitHub's editor with it filled
in, so a review is one click plus a commit.

## Viewing submitted files

Every file in a submission folder is stored in the repo (as a git blob, like
everything else) and published with the site. On the dashboard and on each
submission page, the files show as buttons: PDFs and images open in a pop-up
viewer right there, with "Open in new tab" and "Download" alongside; other
file types open in a new tab. Members see the buttons on their own work,
admins on everyone's.

## Running the site

The site is plain HTML and reads `site/data/index.json`, which
`scripts/build.py` generates from the repo. `--sync-files` also copies
`submissions/` into `site/` so the files are served (that copy is
gitignored). No dependencies beyond Python 3.

```bash
python3 scripts/build.py --sync-files
python3 -m http.server 8000 -d site
```

Then open <http://localhost:8000/>. Pick who you are from *Viewing as* in the
top bar. Members see only their own work; admins see everyone's.

A GitHub Actions workflow rebuilds `index.json` on every push to `main`,
commits it, and publishes `site/` to GitHub Pages. Pages has to be switched
on once in the repo's Settings (Pages, Source: GitHub Actions); after that
every push goes live at `https://weinsteincharles27-del.github.io/PA-07-Project-Tracker/`.
Pages on a **private** repo needs a paid GitHub plan; on the free plan the
repo has to be public, or the site runs locally as above.

## Who can see what

The visibility rule (members see their own work, admins see everything) is
applied by the site. It is not enforced by the repo: anyone with read access
to a git repository can read every file in it, and GitHub has no per-folder
read permissions. Two practical setups:

- **Trust the group.** Keep one private repo, add everyone as a collaborator,
  and rely on the site's role views. Simplest, and fine if members seeing
  each other's folders on GitHub is acceptable.
- **Enforce it.** Give each member their own private repo (or fork) that only
  they and the admins can read, and have the admins' copy of this repo pull
  those in as submodules or with a sync script. More setup, real isolation.

Either way, a CODEOWNERS file can require an admin's approval before anything
under `reviews/` is merged, and branch protection can require pull requests
so nobody rewrites history.

## Layout

```
members.json          roster, roles, and the GitHub repo the site links to
submissions/<id>/     one folder per submission (members write here)
reviews/<id>/         one markdown file per submission (admins write here)
site/                 the static site; data/index.json is generated
scripts/build.py      repo -> site/data/index.json
scripts/submit.py     helper that creates, commits, and pushes a submission
scripts/mockup.py     renders the site with sample data and screenshots it (Playwright)
fixtures/             sample submissions and reviews used only for the mockups
mockups/              the screenshots
```

To regenerate the mockups after changing the site:

```bash
python3 scripts/build.py --root fixtures --out site/data/sample-index.json
python3 scripts/mockup.py
```
