# QA paths: scripts/build.py and scripts/submit.py

Checklist of happy and unhappy paths identified for the three pipeline scripts. Every path is encoded as a test in `tests/test_scripts.py`, named `test_<ID>_...`. "Covered" means there is an automated assertion for it, not that the underlying code is bug-free; see the QA report for which ones fail and why.

## Happy paths, build.py

| ID | Description | Covered |
|----|--------------|---------|
| P-01 | Fixtures (`--root fixtures`) build to exactly 16 submissions | Yes |
| P-02 | Fixtures submissions carry the expected status mix: 8 approved, 2 changes-requested, 2 in-review, 4 submitted (no review file) | Yes |
| P-03 | A root with no submissions/ or reviews/ directories at all builds to 0 submissions with the right top-level keys (generated_at, group, repo, branch, members, assignments, statuses, submissions) | Yes |
| P-04 | Front matter parsing: ordinary `key: value` pairs and the body text below `---` | Yes |
| P-05 | Review parsing with multiple `## date name` comments, in document order | Yes |
| P-06 | `list_files` excludes `submission.md` and dotfiles, and includes name/path/size for the rest | Yes |
| P-07 | Submissions are sorted by `submitted` date, then by `member` | Yes |
| P-08 | Status is derived as `submitted` when there is no matching review file | Yes |
| P-09 | `submitted_by` falls back to the member's display name when there is no front-matter override and no git author available | Yes |
| P-10 | `repo`, `branch`, and `group` in the built index pass through from members.json | Yes |

## Unhappy paths, build.py

| ID | Description | Covered |
|----|--------------|---------|
| P-11 | A folder with files but no `submission.md` is indexed with a title from its name, no assignment, and `has_metadata: false`; an empty or dot-prefixed folder is skipped; `title_from_folder` edge cases; `has_metadata: true` otherwise | Yes |
| P-12 | A member folder not present in members.json prints a warning to stderr and is skipped | Yes |
| P-13 | A review with an unknown `status:` prints a warning and falls back to `in-review` | Yes |
| P-14 | A review file with no front matter at all (status defaults to in-review, reviewer defaults to the last comment's author) | Yes |
| P-15 | A review file with front matter but no `## date name` comments (empty comments list, no crash) | Yes |
| P-16 | A comment heading with a malformed date (wrong format, e.g. `2026/09/07`) is not treated as a new comment; its text is swallowed into the previous comment | Yes |
| P-17 | A front-matter value containing a colon (e.g. `title: Results: part 2`) is parsed correctly (split on first colon only) | Yes |
| P-18 | Front matter with CRLF line endings parses correctly | Yes |
| P-19 | A `submission.md` that is only `---\n---` (empty front matter, empty body) does not crash | Yes |
| P-20 | A folder name with spaces and unicode characters is indexed correctly | Yes |
| P-21 | Any `assignment:` text is indexed as typed (there is no fixed list) | Yes |
| P-22 | Nested subfolders inside a submission folder are skipped entirely by `list_files` (not walked recursively); this is not documented in README.md | Yes |
| P-23 | An empty (but existing) submissions/ directory builds to 0 submissions | Yes |
| P-24 | `--root` pointing at a directory with no `.git` anywhere: dates fall back to filesystem mtimes, `dates_from == "filesystem"` | Yes |
| P-25 | A real git-tracked submission with a backdated `GIT_AUTHOR_DATE`: `submitted` equals that date and `dates_from == "git"` | Yes |
| P-26 | A second, later commit on the same folder: `updated` moves to the later date while `submitted` stays at the original date | Yes |
| P-27 | A folder added in one commit and renamed (`git mv`) in a later commit: git history is not followed across the rename (no `--follow`), so `submitted` becomes the rename commit's date, not the original add date. Informational: this matches the code's folder-name-as-identity model (reviews are also matched by folder name) but is a real limitation worth knowing about | Yes |
| P-28 | The `git()` helper does not raise when the `git` executable is missing from PATH (returns `""` / `(None, None, None)`) | Yes |
| P-29 | `build()` end-to-end does not crash when `git` is missing from PATH, even over a real git-tracked folder; falls back to filesystem dates | Yes |

## Unhappy paths, submit.py

(All run inside a temporary clone of the repo; the real repo is never touched, and `--push` is never passed.)

| ID | Description | Covered |
|----|--------------|---------|
| P-30 | An unknown `--as` value is rejected by argparse (`choices=`), nonzero exit | Yes |
| P-31 | A blank `--assignment` is rejected with a message, nonzero exit, and nothing created | Yes |
| P-32 | A title that slugs to empty (e.g. `"!!!"`) still produces a folder, using the `"submission"` fallback slug | Yes |
| P-33 | A title with quotes and unicode (`Café "Results" v2 — 100%`) round-trips correctly through `submission.md`'s front matter | Yes |
| P-34 | A duplicate folder on the same day exits nonzero with a message and does not overwrite the original `submission.md` | Yes |
| P-35 | A missing file argument exits nonzero, and: does it leave a half-created folder behind? (Checked directly.) | Yes |
| P-36 | `--no-commit` creates the folder but leaves it untracked; the last real commit is unchanged | Yes |
| P-37 | A normal commit (no `--no-commit`) uses the message `"<Name>: <AssignmentId> <Title>"` | Yes |

## Cross-cutting checks

| ID | Description | Covered |
|----|--------------|---------|
| P-38 | `python3 scripts/build.py --help` exits 0 | Yes |
| P-39 | `python3 scripts/submit.py --help` exits 0 | Yes |
| P-40 | `site/data/index.json` (checked in) matches what `build.py` produces right now for the real repo root, ignoring `generated_at` | Yes |
| P-41 | `site/data/sample-index.json` (checked in) matches what `build.py --root fixtures` produces right now, ignoring `generated_at` | Yes |
| P-42 | Every submission's `files[].path` in the sample index points at a file that actually exists under `fixtures/` | Yes |
| P-43 | Every review file under `fixtures/reviews/` has a matching submission folder under `fixtures/submissions/` | Yes |
| P-44 | Every `status` in the sample index is one of the four allowed statuses | Yes |
| P-45 | Every `member` referenced in the sample index exists in members.json | Yes |
| P-46 | The sample index has no `assignments` key and every submission carries a non-empty typed assignment name | Yes |
| P-47 | `scripts/mockup.py` runs to completion and writes 9 PNGs into `mockups/` (smoke test only, not tested deeply) | Yes |

## Round two: fix-specific regressions (submit.py validate/cleanup, build.py submitted_by)

Added after the round-one bug-fix pass (see the QA report for verdicts).

| ID | Description | Covered |
|----|--------------|---------|
| P-48 | `submitted_by` uses the real git commit author when a submission's dates come from git (no front-matter override) | Yes |
| P-49 | `submitted_by` falls back to the member's display name, not the git commit author, when the dates come from front matter and there is no `submitted_by:` override | Yes |
| P-50 | An explicit `submitted_by:` in front matter wins over both the git commit author and the member's display name | Yes |
| P-51 | `submit.py` with two missing file arguments lists both filenames in the error and creates nothing | Yes |
| P-52 | `submit.py`'s failure cleanup removes a brand-new member folder entirely when a file fails to copy mid-write (the member had no folder before this run) | Yes |
| P-53 | `submit.py`'s failure cleanup removes only the half-created submission folder, not the member folder or an unrelated sibling submission already in it, when a file fails to copy mid-write | Yes |

## Paths considered and deliberately not automated

- Manually exercising the three ways to submit described in README.md ("On GitHub, no git needed" and "Upload on GitHub"): these are the site's UI flows, not part of the Python scripts, and out of scope for this script-level suite (site behavior is covered separately in `tests/test_site.py`).
- `submit.py --push`: constraints explicitly say never to pass `--push`; pushing would require a remote and is out of scope for a local QA pass.
- Exact wall-clock/mtime-ordering races in `fs_dates` (e.g. two files written in the same microsecond): inherently flaky to construct deterministically and not worth the brittleness.

## Sync files

| id | path | covered |
|---|---|---|
| P-54 | `--sync-files` mirrors `<root>/submissions` into the site folder next to `--out`, replacing a previous copy | Yes |
| P-55 | `--sync-files` with no submissions folder still creates an empty `site/submissions/` | Yes |

