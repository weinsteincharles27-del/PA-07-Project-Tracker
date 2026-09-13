#!/usr/bin/env python3
"""QA tests for scripts/build.py and scripts/submit.py.

Each test is named after the path id it encodes (see tests/QA-PATHS-SCRIPTS.md).
Stdlib only. build.py is exercised both by importing it directly (for
unit-level checks on its helper functions) and by running it as a
subprocess (for --help and CLI-level checks). submit.py is always run as a
subprocess, inside a fresh temporary clone of this repo, so the real repo
is never touched and nothing is ever pushed.

Run with:
    cd /Users/charlieweinstein/project-tracker
    /usr/bin/python3 -m unittest tests.test_scripts -v
"""
import contextlib
import datetime as dt
import glob
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_PY = os.path.join(REPO, "scripts", "build.py")
SUBMIT_PY = os.path.join(REPO, "scripts", "submit.py")
MOCKUP_PY = os.path.join(REPO, "scripts", "mockup.py")
FIXTURES = os.path.join(REPO, "fixtures")
PYTHON = "/usr/bin/python3"


def load_build_module():
    """Import scripts/build.py by path, independent of cwd/sys.path."""
    spec = importlib.util.spec_from_file_location("_qa_build_module", BUILD_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bm = load_build_module()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_submission(root, member, folder, front_matter=None, body=""):
    """Create submissions/<member>/<folder>/submission.md under root and return its dir."""
    d = os.path.join(root, "submissions", member, folder)
    os.makedirs(d, exist_ok=True)
    lines = ["---"]
    for k, v in (front_matter or {}).items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    content = "\n".join(lines) + "\n"
    if body:
        content += body.strip() + "\n"
    with open(os.path.join(d, "submission.md"), "w", encoding="utf-8") as f:
        f.write(content)
    return d


def run_git(args, cwd, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    )


def strip_generated_at(data):
    return {k: v for k, v in data.items() if k != "generated_at"}


class TempDirMixin:
    def mkdtemp(self):
        path = tempfile.mkdtemp(prefix="qa-scripts-")
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def patch_path_env(self, value):
        """Temporarily replace PATH (e.g. to hide git), restored on cleanup."""
        old = os.environ.get("PATH")
        os.environ["PATH"] = value

        def _restore():
            if old is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old

        self.addCleanup(_restore)


# ---------------------------------------------------------------------------
# Happy paths, build.py (P-01 .. P-10)
# ---------------------------------------------------------------------------
class HappyPathTests(TempDirMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_data = bm.build(FIXTURES)
        cls.members = read_json(os.path.join(REPO, "members.json"))
        cls.member_ids = {m["id"] for m in cls.members["members"]}

    def test_P01_fixtures_build_16_submissions(self):
        self.assertEqual(len(self.fixture_data["submissions"]), 16)

    def test_P02_fixtures_expected_status_mix(self):
        subs = self.fixture_data["submissions"]
        counts = {}
        for s in subs:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        self.assertEqual(
            counts,
            {"approved": 8, "changes-requested": 2, "in-review": 2, "submitted": 4},
        )
        no_review_ids = {s["id"] for s in subs if s["status"] == "submitted"}
        self.assertEqual(
            no_review_ids,
            {
                "bode/2026-09-08-data-memo",
                "bryan/2026-09-11-dataset",
                "kayla/2026-09-12-dataset",
                "kiley/2026-09-06-data-memo",
            },
        )

    def test_P03_empty_root_has_right_top_level_keys(self):
        root = self.mkdtemp()  # no submissions/ or reviews/ at all
        data = bm.build(root)
        self.assertEqual(data["submissions"], [])
        self.assertEqual(
            set(data.keys()),
            {
                "generated_at",
                "group",
                "repo",
                "branch",
                "upload_url",
                "members",
                "statuses",
                "submissions",
            },
        )

    def test_P04_front_matter_basic_parsing(self):
        meta, body = bm.parse_front_matter(
            "---\ntitle: A Title\nassignment: A2\n---\nSome body text.\n"
        )
        self.assertEqual(meta, {"title": "A Title", "assignment": "A2"})
        self.assertEqual(body, "Some body text.")

    def test_P05_review_parsing_multiple_comments_in_order(self):
        review = os.path.join(FIXTURES, "reviews", "bryan", "2026-09-03-data-memo.md")
        parsed = bm.parse_review(review)
        self.assertEqual(len(parsed["comments"]), 3)
        self.assertEqual(
            [c["author"] for c in parsed["comments"]], ["Charlie", "Bryan", "Charlie"]
        )
        self.assertEqual(
            [c["date"] for c in parsed["comments"]],
            ["2026-09-05", "2026-09-07", "2026-09-08"],
        )
        self.assertEqual(parsed["status"], "in-review")

    def test_P06_files_listing_excludes_submission_md_and_dotfiles(self):
        root = self.mkdtemp()
        d = write_submission(root, "bryan", "2026-01-01-files-test", {"title": "T"})
        write_text(os.path.join(d, "keep.csv"), "a,b\n1,2\n")
        write_text(os.path.join(d, ".hidden"), "secret")
        os.makedirs(os.path.join(d, "subdir"))
        write_text(os.path.join(d, "subdir", "inner.csv"), "x\n")
        files = bm.list_files(d, root)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "keep.csv")
        self.assertEqual(files[0]["path"], "submissions/bryan/2026-01-01-files-test/keep.csv")
        self.assertEqual(files[0]["size"], os.path.getsize(os.path.join(d, "keep.csv")))

    def test_P07_sorted_by_submitted_then_member(self):
        subs = self.fixture_data["submissions"]
        keys = [(s["submitted"], s["member"]) for s in subs]
        self.assertEqual(keys, sorted(keys))
        # Spot check a same-date tie is broken by member name.
        idx_aanika = keys.index(("2026-08-28", "aanika"))
        idx_max = keys.index(("2026-08-28", "max"))
        self.assertLess(idx_aanika, idx_max)

    def test_P08_status_submitted_when_no_review_file(self):
        s = next(
            s
            for s in self.fixture_data["submissions"]
            if s["id"] == "bode/2026-09-08-data-memo"
        )
        self.assertIsNone(s["review"])
        self.assertEqual(s["status"], "submitted")

    def test_P09_submitted_by_falls_back_to_member_name(self):
        # A plain (non-git) tempdir: git_dates returns no author, fs_dates
        # returns none either, and there is no submitted_by override, so
        # submitted_by must fall back to the member's display name.
        root = self.mkdtemp()
        write_submission(
            root, "max", "2026-01-01-fallback", {"title": "T", "assignment": "A1"}
        )
        data = bm.build(root)
        self.assertEqual(len(data["submissions"]), 1)
        self.assertEqual(data["submissions"][0]["submitted_by"], "Max")

    def test_P10_repo_branch_group_pass_through(self):
        self.assertEqual(self.fixture_data["repo"], self.members["repo"])
        self.assertEqual(self.fixture_data["branch"], self.members["branch"])
        self.assertEqual(self.fixture_data["group"], self.members["group"])


# ---------------------------------------------------------------------------
# Unhappy paths, build.py (P-11 .. P-29)
# ---------------------------------------------------------------------------
class BuildUnhappyPathTests(TempDirMixin, unittest.TestCase):
    def test_P11_bare_folder_without_submission_md_is_indexed_from_its_name(self):
        # A web upload that skipped submission.md still counts.
        root = self.mkdtemp()
        d = os.path.join(root, "submissions", "bryan", "2026-01-01-pa-07_house-tracker")
        os.makedirs(d)
        write_text(os.path.join(d, "notes.txt"), "hi")
        data = bm.build(root)
        self.assertEqual(len(data["submissions"]), 1)
        sub = data["submissions"][0]
        self.assertEqual(sub["title"], "Pa 07 house tracker")
        self.assertEqual(sub["assignment"], "")
        self.assertFalse(sub["has_metadata"])
        self.assertEqual([f["name"] for f in sub["files"]], ["notes.txt"])
        self.assertEqual(sub["submitted_by"], "Bryan")

    def test_P11b_empty_bare_folder_is_skipped(self):
        root = self.mkdtemp()
        os.makedirs(os.path.join(root, "submissions", "bryan", "2026-01-01-empty"))
        os.makedirs(os.path.join(root, "submissions", "bryan", ".hidden"))
        self.assertEqual(bm.build(root)["submissions"], [])

    def test_P11c_title_from_folder_edge_cases(self):
        self.assertEqual(bm.title_from_folder("2026-09-13-memo"), "Memo")
        self.assertEqual(bm.title_from_folder("2026-09-13"), "2026-09-13")
        self.assertEqual(bm.title_from_folder("no-date-here"), "No date here")
        self.assertEqual(bm.title_from_folder("2026-09-13-"), "2026-09-13-")

    def test_P11d_submission_with_metadata_reports_has_metadata(self):
        root = self.mkdtemp()
        write_submission(root, "bryan", "2026-01-01-x", {"title": "X", "assignment": "Memo"})
        sub = bm.build(root)["submissions"][0]
        self.assertTrue(sub["has_metadata"])
        self.assertEqual(sub["title"], "X")

    def test_P12_unknown_member_folder_warns_and_skips(self):
        root = self.mkdtemp()
        write_submission(root, "notamember", "2026-01-01-x", {"title": "X"})
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            data = bm.build(root)
        self.assertEqual(data["submissions"], [])
        self.assertIn("notamember", buf.getvalue())
        self.assertIn("not in members.json", buf.getvalue())

    def test_P13_unknown_review_status_warns_and_falls_back(self):
        root = self.mkdtemp()
        write_submission(
            root, "bryan", "2026-01-01-x", {"title": "T", "submitted": "2026-01-01"}
        )
        rd = os.path.join(root, "reviews", "bryan")
        os.makedirs(rd)
        with open(os.path.join(rd, "2026-01-01-x.md"), "w") as f:
            f.write("---\nstatus: bogus-status\nreviewer: X\n---\n## 2026-01-01 X\nhi\n")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            data = bm.build(root)
        self.assertEqual(data["submissions"][0]["status"], "in-review")
        self.assertIn("unknown status", buf.getvalue())
        self.assertIn("bogus-status", buf.getvalue())

    def test_P14_review_with_no_front_matter(self):
        text = "Just some text, no front matter.\n\n## 2026-01-01 Nobody\n\nHello\n"
        tmp = self.mkdtemp()
        p = os.path.join(tmp, "r.md")
        write_text(p, text)
        parsed = bm.parse_review(p)
        self.assertEqual(parsed["status"], "in-review")
        self.assertEqual(parsed["reviewer"], "Nobody")
        self.assertEqual(len(parsed["comments"]), 1)

    def test_P15_review_with_front_matter_but_no_comments(self):
        text = "---\nstatus: in-review\nreviewer: Someone\n---\nJust a note.\n"
        tmp = self.mkdtemp()
        p = os.path.join(tmp, "r.md")
        write_text(p, text)
        parsed = bm.parse_review(p)
        self.assertEqual(parsed["status"], "in-review")
        self.assertEqual(parsed["reviewer"], "Someone")
        self.assertEqual(parsed["comments"], [])

    def test_P16_comment_heading_with_malformed_date(self):
        text = (
            "---\nstatus: in-review\nreviewer: Charlie\n---\n\n"
            "## 2026-09-05 Charlie\n\nFirst comment text.\n\n"
            "## 2026/09/07 Charlie\n\nThis malformed-date heading should not start a new comment.\n"
        )
        tmp = self.mkdtemp()
        p = os.path.join(tmp, "r.md")
        write_text(p, text)
        parsed = bm.parse_review(p)
        # The malformed heading does not match COMMENT_RE, so it (and the
        # text under it) is swallowed into the previous comment instead of
        # starting a new one.
        self.assertEqual(len(parsed["comments"]), 1)
        self.assertEqual(parsed["comments"][0]["author"], "Charlie")
        self.assertIn("2026/09/07", parsed["comments"][0]["text"])

    def test_P17_front_matter_value_with_colon(self):
        meta, body = bm.parse_front_matter(
            "---\ntitle: Results: part 2\nassignment: A2\n---\nBody.\n"
        )
        self.assertEqual(meta["title"], "Results: part 2")
        self.assertEqual(meta["assignment"], "A2")

    def test_P18_front_matter_with_crlf(self):
        meta, body = bm.parse_front_matter(
            "---\r\ntitle: CRLF Test\r\nassignment: A1\r\n---\r\nBody with CRLF.\r\n"
        )
        self.assertEqual(meta, {"title": "CRLF Test", "assignment": "A1"})
        self.assertEqual(body, "Body with CRLF.")

    def test_P19_submission_md_only_dashes(self):
        meta, body = bm.parse_front_matter("---\n---\n")
        self.assertEqual(meta, {})
        self.assertEqual(body, "")
        # And end to end: build() must not crash on it.
        root = self.mkdtemp()
        d = os.path.join(root, "submissions", "bryan", "2026-01-01-empty")
        os.makedirs(d)
        write_text(os.path.join(d, "submission.md"), "---\n---\n")
        data = bm.build(root)
        self.assertEqual(len(data["submissions"]), 1)
        self.assertEqual(data["submissions"][0]["title"], "Empty")  # derived from the folder name

    def test_P20_folder_name_with_spaces_and_unicode(self):
        root = self.mkdtemp()
        folder = "2026-01-02 André's Notes"
        write_submission(
            root,
            "aanika",
            folder,
            {"title": "Unicode Test", "assignment": "A1", "submitted": "2026-01-02"},
        )
        data = bm.build(root)
        self.assertEqual(len(data["submissions"]), 1)
        s = data["submissions"][0]
        self.assertEqual(s["folder"], folder)
        self.assertEqual(s["id"], f"aanika/{folder}")

    def test_P21_any_assignment_text_is_indexed(self):
        root = self.mkdtemp()
        write_submission(
            root,
            "max",
            "2026-01-01-z9",
            {"title": "T", "assignment": "Z9", "submitted": "2026-01-01"},
        )
        data = bm.build(root)
        self.assertEqual(len(data["submissions"]), 1)
        self.assertEqual(data["submissions"][0]["assignment"], "Z9")

    def test_P22_nested_subfolder_is_skipped_not_walked(self):
        root = self.mkdtemp()
        d = write_submission(root, "bryan", "2026-01-01-nested", {"title": "T"})
        os.makedirs(os.path.join(d, "extra"))
        write_text(os.path.join(d, "extra", "data.csv"), "x,y\n1,2\n")
        write_text(os.path.join(d, "top.csv"), "a,b\n1,2\n")
        files = bm.list_files(d, root)
        names = [f["name"] for f in files]
        self.assertEqual(names, ["top.csv"])
        self.assertNotIn("extra", names)
        # Documentation check: README.md does not mention this behavior.
        readme = read_text(os.path.join(REPO, "README.md"))
        self.assertNotIn("nested", readme.lower())

    def test_P23_empty_submissions_dir(self):
        root = self.mkdtemp()
        os.makedirs(os.path.join(root, "submissions"))
        data = bm.build(root)
        self.assertEqual(data["submissions"], [])

    def test_P24_root_not_a_git_dir_uses_filesystem_dates(self):
        root = self.mkdtemp()
        write_submission(root, "bryan", "2026-01-01-fstest", {"title": "FS Test", "assignment": "A1"})
        data = bm.build(root)
        s = data["submissions"][0]
        self.assertEqual(s["dates_from"], "filesystem")
        today = dt.date.today().isoformat()
        self.assertEqual(s["submitted"], today)
        self.assertEqual(s["updated"], today)

    def test_P25_real_git_backdated_commit(self):
        root = self.mkdtemp()
        run_git(["init", "-q"], root)
        run_git(["config", "user.name", "QA"], root)
        run_git(["config", "user.email", "qa@example.com"], root)
        d = os.path.join(root, "submissions", "bryan", "2026-02-01-gittest")
        os.makedirs(d)
        write_text(os.path.join(d, "submission.md"), "---\ntitle: Git Test\nassignment: A1\n---\n")
        run_git(["add", "-A"], root)
        run_git(
            ["commit", "-q", "-m", "add"],
            root,
            extra_env={
                "GIT_AUTHOR_DATE": "2026-02-01T09:00:00",
                "GIT_COMMITTER_DATE": "2026-02-01T09:00:00",
            },
        )
        data = bm.build(root)
        s = data["submissions"][0]
        self.assertEqual(s["dates_from"], "git")
        self.assertEqual(s["submitted"], "2026-02-01")

    def test_P26_second_later_commit_moves_updated_not_submitted(self):
        root = self.mkdtemp()
        run_git(["init", "-q"], root)
        run_git(["config", "user.name", "QA"], root)
        run_git(["config", "user.email", "qa@example.com"], root)
        d = os.path.join(root, "submissions", "bryan", "2026-02-01-gittest2")
        os.makedirs(d)
        write_text(os.path.join(d, "submission.md"), "---\ntitle: Git Test\nassignment: A1\n---\n")
        run_git(["add", "-A"], root)
        run_git(
            ["commit", "-q", "-m", "add"],
            root,
            extra_env={
                "GIT_AUTHOR_DATE": "2026-02-01T09:00:00",
                "GIT_COMMITTER_DATE": "2026-02-01T09:00:00",
            },
        )
        first = bm.build(root)["submissions"][0]
        self.assertEqual(first["submitted"], "2026-02-01")
        self.assertEqual(first["updated"], "2026-02-01")

        write_text(os.path.join(d, "extra.txt"), "more")
        run_git(["add", "-A"], root)
        run_git(
            ["commit", "-q", "-m", "update"],
            root,
            extra_env={
                "GIT_AUTHOR_DATE": "2026-02-10T09:00:00",
                "GIT_COMMITTER_DATE": "2026-02-10T09:00:00",
            },
        )
        second = bm.build(root)["submissions"][0]
        self.assertEqual(second["submitted"], "2026-02-01", "submitted must not move")
        self.assertEqual(second["updated"], "2026-02-10", "updated must move to the later commit")

    def test_P27_rename_across_commits(self):
        root = self.mkdtemp()
        run_git(["init", "-q"], root)
        run_git(["config", "user.name", "QA"], root)
        run_git(["config", "user.email", "qa@example.com"], root)
        orig = os.path.join(root, "submissions", "bryan", "2026-04-01-orig")
        os.makedirs(orig)
        write_text(os.path.join(orig, "submission.md"), "---\ntitle: Rename Test\nassignment: A1\n---\n")
        run_git(["add", "-A"], root)
        run_git(
            ["commit", "-q", "-m", "add"],
            root,
            extra_env={
                "GIT_AUTHOR_DATE": "2026-04-01T09:00:00",
                "GIT_COMMITTER_DATE": "2026-04-01T09:00:00",
            },
        )
        run_git(["mv", "submissions/bryan/2026-04-01-orig", "submissions/bryan/2026-04-02-renamed"], root)
        run_git(
            ["commit", "-q", "-m", "rename"],
            root,
            extra_env={
                "GIT_AUTHOR_DATE": "2026-04-05T09:00:00",
                "GIT_COMMITTER_DATE": "2026-04-05T09:00:00",
            },
        )
        data = bm.build(root)
        self.assertEqual(len(data["submissions"]), 1)
        s = data["submissions"][0]
        self.assertEqual(s["id"], "bryan/2026-04-02-renamed")
        # git log is not run with --follow, so history before the rename is
        # invisible for the new path: "submitted" becomes the rename date,
        # not the original 2026-04-01 add date. This is a real limitation
        # (see tests/QA-PATHS-SCRIPTS.md, P-27) but matches the code's
        # folder-name-as-identity model used elsewhere (e.g. review lookup).
        self.assertEqual(s["dates_from"], "git")
        self.assertEqual(s["submitted"], "2026-04-05")
        self.assertEqual(s["updated"], "2026-04-05")

    def test_P28_git_helper_survives_missing_git(self):
        self.patch_path_env("/definitely-not-a-real-dir")
        out = bm.git(["--version"], cwd=REPO)
        self.assertEqual(out, "")
        dates = bm.git_dates(os.path.join(REPO, "fixtures"), REPO)
        self.assertEqual(dates, (None, None, None))

    def test_P29_build_survives_missing_git_end_to_end(self):
        root = self.mkdtemp()
        run_git(["init", "-q"], root)
        run_git(["config", "user.name", "QA"], root)
        run_git(["config", "user.email", "qa@example.com"], root)
        d = os.path.join(root, "submissions", "bryan", "2026-03-01-pathtest")
        os.makedirs(d)
        write_text(os.path.join(d, "submission.md"), "---\ntitle: Path Test\nassignment: A1\n---\n")
        run_git(["add", "-A"], root)
        run_git(
            ["commit", "-q", "-m", "add"],
            root,
            extra_env={
                "GIT_AUTHOR_DATE": "2026-03-01T09:00:00",
                "GIT_COMMITTER_DATE": "2026-03-01T09:00:00",
            },
        )
        self.patch_path_env("/definitely-not-a-real-dir")
        data = bm.build(root)  # must not raise
        s = data["submissions"][0]
        self.assertEqual(s["dates_from"], "filesystem")


# ---------------------------------------------------------------------------
# Unhappy paths, submit.py (P-30 .. P-37)
# ---------------------------------------------------------------------------
class SubmitScriptTests(unittest.TestCase):
    def setUp(self):
        self.clone = tempfile.mkdtemp(prefix="qa-clone-")
        self.addCleanup(shutil.rmtree, self.clone, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "-q", REPO, self.clone],
            check=True,
            capture_output=True,
            text=True,
        )
        run_git(["config", "user.name", "QA Bot"], self.clone)
        run_git(["config", "user.email", "qa@example.com"], self.clone)
        self.script = os.path.join(self.clone, "scripts", "submit.py")
        # A clone only carries committed content, so copy the working-tree
        # script in; otherwise these tests exercise the last commit, not the
        # code under test.
        shutil.copy2(SUBMIT_PY, self.script)

    def run_submit(self, *args):
        return subprocess.run(
            [PYTHON, self.script, *args],
            cwd=self.clone,
            capture_output=True,
            text=True,
        )

    def today_folder(self, slug):
        return f"{dt.date.today().isoformat()}-{slug}"

    def test_P30_unknown_as_value_rejected(self):
        r = self.run_submit("--as", "nobody", "--assignment", "A2", "--title", "X")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("invalid choice", r.stderr)

    def test_P31_blank_assignment_rejected(self):
        # The assignment is free text, but it cannot be blank.
        r = self.run_submit("--as", "bryan", "--assignment", "   ", "--title", "X")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("cannot be blank", r.stderr)
        today = dt.date.today().isoformat()
        self.assertFalse(os.path.isdir(os.path.join(self.clone, "submissions", "bryan", f"{today}-x")))

    def test_P32_title_slugs_to_empty_still_creates_folder(self):
        r = self.run_submit("--as", "bryan", "--assignment", "A2", "--title", "!!!", "--no-commit")
        self.assertEqual(r.returncode, 0, r.stderr)
        folder = os.path.join(self.clone, "submissions", "bryan", self.today_folder("submission"))
        self.assertTrue(os.path.isdir(folder))

    def test_P33_title_with_quotes_and_unicode_round_trips(self):
        title = 'Café "Results" v2 — 100%'
        r = self.run_submit("--as", "aanika", "--assignment", "A2", "--title", title, "--no-commit")
        self.assertEqual(r.returncode, 0, r.stderr)
        member_dir = os.path.join(self.clone, "submissions", "aanika")
        candidates = [
            f for f in os.listdir(member_dir) if f.startswith(dt.date.today().isoformat())
        ]
        self.assertEqual(len(candidates), 1)
        sub_md = os.path.join(member_dir, candidates[0], "submission.md")
        meta, _ = bm.parse_front_matter(read_text(sub_md))
        self.assertEqual(meta["title"], title)

    def test_P34_duplicate_folder_same_day_does_not_overwrite(self):
        r1 = self.run_submit("--as", "kayla", "--assignment", "A1", "--title", "Dup Test", "--no-commit")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        folder = os.path.join(self.clone, "submissions", "kayla", self.today_folder("dup-test"))
        before = read_text(os.path.join(folder, "submission.md"))

        r2 = self.run_submit("--as", "kayla", "--assignment", "A2", "--title", "Dup Test", "--no-commit")
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("already exists", r2.stdout + r2.stderr)

        after = read_text(os.path.join(folder, "submission.md"))
        self.assertEqual(before, after, "the original submission.md must not be overwritten")

    def test_P35_missing_file_argument_exits_nonzero_and_should_not_leave_partial_folder(self):
        r = self.run_submit(
            "--as", "bryan", "--assignment", "A2", "--title", "Missing File Test", "nonexistent-file.md"
        )
        self.assertNotEqual(r.returncode, 0, "a missing file argument must be a hard failure")
        folder = os.path.join(
            self.clone, "submissions", "bryan", self.today_folder("missing-file-test")
        )
        self.assertFalse(
            os.path.exists(folder),
            "submit.py should not leave a half-created submission folder behind "
            "when a --file argument does not exist",
        )

    def test_P36_no_commit_leaves_folder_untracked(self):
        before_head = run_git(["log", "-1", "--format=%H"], self.clone).stdout.strip()
        r = self.run_submit(
            "--as", "max", "--assignment", "A3", "--title", "Commit Msg Test", "--no-commit"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        after_head = run_git(["log", "-1", "--format=%H"], self.clone).stdout.strip()
        self.assertEqual(before_head, after_head, "no new commit should be made with --no-commit")
        status = run_git(["status", "--porcelain"], self.clone).stdout
        self.assertIn("submissions/max/", status)

    def test_P37_commit_message_format(self):
        r = self.run_submit(
            "--as", "bode", "--assignment", "Preliminary results", "--title", "Committed Test"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        subject = run_git(["log", "-1", "--format=%s"], self.clone).stdout.strip()
        self.assertEqual(subject, "Bode: Committed Test (Preliminary results)")


# ---------------------------------------------------------------------------
# Cross-cutting checks (P-38 .. P-47)
# ---------------------------------------------------------------------------
class CrossCuttingTests(unittest.TestCase):
    def test_P38_build_help_exits_zero(self):
        r = subprocess.run([PYTHON, BUILD_PY, "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_P39_submit_help_exits_zero(self):
        r = subprocess.run([PYTHON, SUBMIT_PY, "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_P40_index_json_in_sync_with_real_root(self):
        fresh = strip_generated_at(bm.build(bm.REPO))
        checked_in = strip_generated_at(
            read_json(os.path.join(REPO, "site", "data", "index.json"))
        )
        self.assertEqual(fresh, checked_in)

    def test_P41_sample_index_json_in_sync_with_fixtures(self):
        fresh = strip_generated_at(bm.build(FIXTURES))
        checked_in = strip_generated_at(
            read_json(os.path.join(REPO, "site", "data", "sample-index.json"))
        )
        self.assertEqual(
            fresh,
            checked_in,
            "site/data/sample-index.json is stale relative to `build.py --root fixtures`",
        )

    def test_P42_sample_index_file_paths_exist_under_fixtures(self):
        data = read_json(os.path.join(REPO, "site", "data", "sample-index.json"))
        for s in data["submissions"]:
            for f in s["files"]:
                full = os.path.join(FIXTURES, f["path"])
                self.assertTrue(os.path.exists(full), f"missing file: {f['path']}")

    def test_P43_every_fixture_review_has_matching_submission_folder(self):
        rev_root = os.path.join(FIXTURES, "reviews")
        sub_root = os.path.join(FIXTURES, "submissions")
        for member in os.listdir(rev_root):
            mdir = os.path.join(rev_root, member)
            if not os.path.isdir(mdir):
                continue
            for fname in os.listdir(mdir):
                if not fname.endswith(".md"):
                    continue
                folder = fname[: -len(".md")]
                expected = os.path.join(sub_root, member, folder)
                self.assertTrue(
                    os.path.isdir(expected),
                    f"reviews/{member}/{fname} has no matching submissions/{member}/{folder}/",
                )

    def test_P44_sample_index_statuses_all_allowed(self):
        data = read_json(os.path.join(REPO, "site", "data", "sample-index.json"))
        allowed = set(bm.STATUSES)
        for s in data["submissions"]:
            self.assertIn(s["status"], allowed)

    def test_P45_sample_index_members_all_known(self):
        data = read_json(os.path.join(REPO, "site", "data", "sample-index.json"))
        member_ids = {m["id"] for m in data["members"]}
        for s in data["submissions"]:
            self.assertIn(s["member"], member_ids)

    def test_P46_sample_index_assignments_are_typed_names(self):
        # No fixed list: every sample submission carries a non-empty typed name.
        data = read_json(os.path.join(REPO, "site", "data", "sample-index.json"))
        self.assertNotIn("assignments", data)
        for s in data["submissions"]:
            self.assertTrue(s["assignment"].strip(), s["id"])

    def test_P47_mockup_runs_and_produces_9_pngs(self):
        out_dir = os.path.join(REPO, "mockups")
        r = subprocess.run(
            [PYTHON, MOCKUP_PY], cwd=REPO, capture_output=True, text=True, timeout=120
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        pngs = glob.glob(os.path.join(out_dir, "*.png"))
        self.assertEqual(len(pngs), 9, pngs)


# ---------------------------------------------------------------------------
# Round-two regression checks: build.py's submitted_by fix (P-48 .. P-50)
#
# Before the fix, `author` (the real git commit author) was used for
# submitted_by even when the submission's dates were overridden by front
# matter, so a fixture dated by `submitted:` but committed by someone else
# (say, whoever ran the fixture-authoring commit) would show
# that committer's name instead of the submitting member's. The fix clears
# `author` whenever front matter supplies the date. These tests build real
# git history so `git_dates()` returns a real, distinctive author name, then
# check submitted_by in each of the three date-source combinations.
# ---------------------------------------------------------------------------
class SubmittedByTests(TempDirMixin, unittest.TestCase):
    def make_git_repo(self):
        root = self.mkdtemp()
        run_git(["init", "-q"], root)
        run_git(["config", "user.name", "QA"], root)
        run_git(["config", "user.email", "qa@example.com"], root)
        return root

    def commit_submission(self, root, d, extra_env, commit_author=("Some Committer", "committer@example.com")):
        run_git(["add", "-A"], root)
        env = dict(extra_env)
        env["GIT_AUTHOR_NAME"] = commit_author[0]
        env["GIT_AUTHOR_EMAIL"] = commit_author[1]
        run_git(["commit", "-q", "-m", "add"], root, extra_env=env)

    def test_P48_submitted_by_uses_git_author_when_dates_come_from_git(self):
        # No `submitted:` override in front matter, so dates come from git,
        # and submitted_by should be the real commit author, not the
        # member's display name.
        root = self.make_git_repo()
        d = os.path.join(root, "submissions", "bryan", "2026-05-01-gitauthor")
        os.makedirs(d)
        write_text(os.path.join(d, "submission.md"), "---\ntitle: Git Author Test\nassignment: A1\n---\n")
        self.commit_submission(
            root, d,
            {"GIT_AUTHOR_DATE": "2026-05-01T09:00:00", "GIT_COMMITTER_DATE": "2026-05-01T09:00:00"},
            commit_author=("Bryan Real Name", "bryan@example.com"),
        )
        data = bm.build(root)
        s = data["submissions"][0]
        self.assertEqual(s["dates_from"], "git")
        self.assertEqual(s["submitted_by"], "Bryan Real Name")

    def test_P49_submitted_by_ignores_git_author_when_front_matter_dates_win(self):
        # Front matter supplies `submitted:`, so dates_from is front-matter.
        # The commit author is a name that is neither the member's display
        # name nor a submitted_by override, so if the fix regressed (author
        # leaking through again), submitted_by would come back as
        # "Someone Else" instead of falling back to "Max".
        root = self.make_git_repo()
        d = os.path.join(root, "submissions", "max", "2026-05-02-fmdate")
        os.makedirs(d)
        write_text(
            os.path.join(d, "submission.md"),
            "---\ntitle: FM Date Test\nassignment: A1\nsubmitted: 2026-05-02\n---\n",
        )
        self.commit_submission(
            root, d,
            {"GIT_AUTHOR_DATE": "2026-05-03T09:00:00", "GIT_COMMITTER_DATE": "2026-05-03T09:00:00"},
            commit_author=("Someone Else", "someone@example.com"),
        )
        data = bm.build(root)
        s = data["submissions"][0]
        self.assertEqual(s["dates_from"], "front-matter")
        self.assertEqual(s["submitted"], "2026-05-02", "front matter must still win the date")
        self.assertEqual(
            s["submitted_by"], "Max",
            "submitted_by must fall back to the member's name, not the git commit author, "
            "when the date came from front matter",
        )

    def test_P50_submitted_by_front_matter_override_wins_over_everything(self):
        # An explicit submitted_by: in front matter must win over both the
        # git author and the member's display name.
        root = self.make_git_repo()
        d = os.path.join(root, "submissions", "max", "2026-05-04-fmauthor")
        os.makedirs(d)
        write_text(
            os.path.join(d, "submission.md"),
            "---\ntitle: FM Author Test\nassignment: A1\nsubmitted: 2026-05-04\n"
            "submitted_by: A Delegate\n---\n",
        )
        self.commit_submission(
            root, d,
            {"GIT_AUTHOR_DATE": "2026-05-05T09:00:00", "GIT_COMMITTER_DATE": "2026-05-05T09:00:00"},
            commit_author=("Someone Else", "someone@example.com"),
        )
        data = bm.build(root)
        s = data["submissions"][0]
        self.assertEqual(s["submitted_by"], "A Delegate")


# ---------------------------------------------------------------------------
# Round-two regression checks: submit.py's validate-first / cleanup-on-
# failure fix (P-51 .. P-53)
# ---------------------------------------------------------------------------
class SubmitCleanupTests(unittest.TestCase):
    def setUp(self):
        self.clone = tempfile.mkdtemp(prefix="qa-clone-cleanup-")
        self.addCleanup(shutil.rmtree, self.clone, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "-q", REPO, self.clone],
            check=True, capture_output=True, text=True,
        )
        run_git(["config", "user.name", "QA Bot"], self.clone)
        run_git(["config", "user.email", "qa@example.com"], self.clone)
        self.script = os.path.join(self.clone, "scripts", "submit.py")
        # A clone only carries committed content; copy the working-tree
        # script in so these tests exercise the code under test.
        shutil.copy2(SUBMIT_PY, self.script)

    def run_submit(self, *args):
        return subprocess.run(
            [PYTHON, self.script, *args], cwd=self.clone, capture_output=True, text=True,
        )

    def today_folder(self, slug):
        return f"{dt.date.today().isoformat()}-{slug}"

    def make_unreadable_file(self, path, text="x"):
        """A file that passes os.path.isfile() (submit.py's pre-check only
        looks at the file type) but raises PermissionError when actually
        read, so it fails partway through the copy loop instead of at the
        upfront validation -- the scenario the try/except cleanup exists for."""
        write_text(path, text)
        os.chmod(path, 0o000)
        self.addCleanup(os.chmod, path, 0o644)
        return path

    def test_P51_two_missing_files_both_listed_nothing_created(self):
        r = self.run_submit(
            "--as", "kiley", "--assignment", "A2", "--title", "Two Missing Files",
            "nonexistent-one.md", "nonexistent-two.csv",
        )
        self.assertNotEqual(r.returncode, 0)
        combined = r.stdout + r.stderr
        self.assertIn("nonexistent-one.md", combined, "first missing file should be listed")
        self.assertIn("nonexistent-two.csv", combined, "second missing file should also be listed")
        folder = os.path.join(self.clone, "submissions", "kiley", self.today_folder("two-missing-files"))
        self.assertFalse(os.path.exists(folder), "nothing should be created when any file is missing")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "chmod 0o000 has no effect as root")
    def test_P52_cleanup_removes_brand_new_member_folder_entirely(self):
        # Every member folder in this repo already holds a committed
        # README.md; delete it so this clone starts exactly like a member
        # who has never submitted before -- the case the fix's
        # new_member_dir tracking targets.
        member_dir = os.path.join(self.clone, "submissions", "bryan")
        shutil.rmtree(member_dir)

        good = os.path.join(self.clone, "good.txt")
        write_text(good, "fine")
        bad = self.make_unreadable_file(os.path.join(self.clone, "unreadable.txt"))

        r = self.run_submit(
            "--as", "bryan", "--assignment", "A2", "--title", "Cleanup New Member",
            "--no-commit", good, bad,
        )
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertFalse(
            os.path.exists(member_dir),
            "a member folder that did not exist before this run must be removed entirely on failure",
        )

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "chmod 0o000 has no effect as root")
    def test_P53_cleanup_preserves_preexisting_member_folder_and_sibling(self):
        # bryan's member folder already exists (README.md); add an unrelated
        # sibling submission so we can confirm the cleanup only removes the
        # folder this run started, not the member folder or other work in it.
        member_dir = os.path.join(self.clone, "submissions", "bryan")
        sibling = os.path.join(member_dir, "2020-01-01-untouched")
        os.makedirs(sibling)
        write_text(os.path.join(sibling, "submission.md"), "---\ntitle: Untouched\nassignment: A1\n---\n")
        write_text(os.path.join(sibling, "keep.txt"), "do not delete me")

        good = os.path.join(self.clone, "good2.txt")
        write_text(good, "fine")
        bad = self.make_unreadable_file(os.path.join(self.clone, "unreadable2.txt"))

        r = self.run_submit(
            "--as", "bryan", "--assignment", "A2", "--title", "Cleanup Sibling Test",
            "--no-commit", good, bad,
        )
        self.assertNotEqual(r.returncode, 0, r.stdout)
        new_folder = os.path.join(member_dir, self.today_folder("cleanup-sibling-test"))
        self.assertFalse(os.path.exists(new_folder), "the half-created submission folder must be removed")
        self.assertTrue(os.path.isdir(member_dir), "a member folder that already held other work must survive")
        self.assertTrue(os.path.isdir(sibling), "an unrelated sibling submission must not be touched")
        self.assertEqual(read_text(os.path.join(sibling, "keep.txt")), "do not delete me")


if __name__ == "__main__":
    unittest.main()


class SyncFilesTests(unittest.TestCase):
    def test_P54_sync_files_mirrors_submissions_next_to_the_site(self):
        tmp = tempfile.mkdtemp(prefix="tracker-sync-")
        self.addCleanup(shutil.rmtree, tmp, True)
        site = os.path.join(tmp, "site")
        os.makedirs(os.path.join(site, "data"))
        stale = os.path.join(site, "submissions", "old")
        os.makedirs(stale)
        write_text(os.path.join(stale, "leftover.txt"), "stale")
        r = subprocess.run(
            [sys.executable, BUILD_PY, "--root", os.path.join(REPO, "fixtures"), "--out", os.path.join(site, "data", "index.json"), "--sync-files"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("synced submissions/", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(site, "submissions", "bryan", "2026-08-26-lit-review", "lit-review.pdf")))
        self.assertFalse(os.path.exists(stale), "a previous copy is replaced, not merged")

    def test_P55_sync_files_with_no_submissions_folder_makes_an_empty_one(self):
        tmp = tempfile.mkdtemp(prefix="tracker-sync-")
        self.addCleanup(shutil.rmtree, tmp, True)
        root = os.path.join(tmp, "root"); site = os.path.join(tmp, "site")
        os.makedirs(root); os.makedirs(os.path.join(site, "data"))
        r = subprocess.run(
            [sys.executable, BUILD_PY, "--root", root, "--out", os.path.join(site, "data", "index.json"), "--sync-files"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isdir(os.path.join(site, "submissions")))
