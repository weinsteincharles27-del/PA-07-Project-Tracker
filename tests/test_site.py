"""Playwright QA suite for the PA-07 Project Tracker static site.

Serves a temp copy of site/ over http.server (the same way scripts/mockup.py
does) and drives it with Playwright's sync API on Chromium. Test method names
embed the path id from tests/QA-PATHS.md (for example test_S12_... covers
S-12). Nothing under site/, scripts/, fixtures/, submissions/, reviews/, or
the JSON config files is modified; data-shape edge cases are written as
throwaway index.json variants into the served temp copy.

Run with:
    cd /Users/charlieweinstein/project-tracker
    /usr/bin/python3 -m unittest tests.test_site -v
"""
import copy
import functools
import http.server
import json
import os
import re
import shutil
import socket
import tempfile
import threading
import unittest
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SAMPLE = _load_json(os.path.join(SITE, "data", "sample-index.json"))
EMPTY = _load_json(os.path.join(SITE, "data", "index.json"))


def clone(base):
    return copy.deepcopy(base)


def without_member(base, member_id):
    """Sample data with every submission from member_id removed."""
    d = clone(base)
    d["submissions"] = [s for s in d["submissions"] if s["member"] != member_id]
    return d


def js_slug(s):
    """Python replica of Tracker.slug() in site/assets/app.js, so expected
    values can be computed independently of the app under test."""
    t = s.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = re.sub(r"^-+|-+$", "", t)
    t = t[:40]
    return t or "submission"


def sh_quote(s):
    """Python replica of the q() shell-quoting helper in submit.html."""
    return "'" + s.replace("'", "'\\''") + "'"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=root)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


class ServedSiteTestCase(unittest.TestCase):
    """Base class: copies site/ to a scratch dir, serves it, launches one
    Chromium browser shared by every test in the (sub)class."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tracker-qa-")
        cls.root = os.path.join(cls.tmp, "site")
        shutil.copytree(SITE, cls.root)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        cls.httpd, cls.port = serve(cls.root)
        cls.base = f"http://127.0.0.1:{cls.port}/"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.httpd.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- data helpers ---------------------------------------------------
    def write_data(self, data):
        """Overwrite the served data/index.json. Every test that needs a
        particular data shape calls this itself at the top, so tests do not
        depend on execution order."""
        with open(os.path.join(self.root, "data", "index.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    # -- page helpers -----------------------------------------------------
    def new_page(self, viewport=None, color_scheme=None):
        ctx = self.browser.new_context(
            viewport=viewport or {"width": 1280, "height": 900},
            color_scheme=color_scheme or "light",
        )
        page = ctx.new_page()
        page._page_errors = []
        page._console_errors = []
        page._dialogs = []
        page._popups = []
        page.on("pageerror", lambda e: page._page_errors.append(str(e)))
        page.on("console", lambda m: page._console_errors.append(m.text) if m.type == "error" else None)
        page.on("dialog", lambda d: (page._dialogs.append(d.message), d.dismiss()))
        page.on("popup", lambda p: page._popups.append(p))
        self.addCleanup(ctx.close)
        return page

    def goto(self, page, path):
        page.goto(self.base + path, wait_until="networkidle")
        page.wait_for_selector(".page")
        return page

    def assert_clean(self, page, msg=""):
        """No uncaught exceptions and no console.error calls (the general
        'no console errors or uncaught page errors' rule)."""
        self.assertEqual(page._page_errors, [], f"{msg} (uncaught page errors)")
        self.assertEqual(page._console_errors, [], f"{msg} (console.error calls)")
        self.assertEqual(page._dialogs, [], f"{msg} (an alert/confirm/prompt fired)")


# ======================================================================
# Identity, navigation, top bar, and the shared failure path
# ======================================================================
class TestIdentityAndNav(ServedSiteTestCase):
    def test_S01_dashboard_nav_links_carry_as(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=bryan")
        for label, target in [("Dashboard", "index.html"), ("Timeline", "timeline.html"), ("Submit", "submit.html")]:
            href = page.locator(f".nav a:has-text('{label}')").get_attribute("href")
            self.assertIn("as=bryan", href, f"{label} link should carry ?as=bryan, got {href}")
            self.assertTrue(href.startswith(target), href)
        self.assert_clean(page, "dashboard nav")

    def test_S02_timeline_nav_links_carry_as(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=kiley")
        href = page.locator(".nav a:has-text('Submit')").get_attribute("href")
        self.assertIn("as=kiley", href)
        self.assert_clean(page, "timeline nav")

    def test_S03_submit_nav_links_carry_as(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=aanika")
        href = page.locator(".nav a:has-text('Dashboard')").get_attribute("href")
        self.assertIn("as=aanika", href)
        self.assert_clean(page, "submit nav")

    def test_S04_viewer_select_switches_identity_and_reloads(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=bryan")
        self.assertIn("Your submissions", page.locator("h1").inner_text())
        with page.expect_navigation():
            page.select_option("#viewer-select", "charlie")
        page.wait_for_load_state("networkidle")
        self.assertIn("as=charlie", page.url)
        self.assertIn("All submissions", page.locator("h1").inner_text())
        self.assert_clean(page, "viewer switch")

    def test_S05_dashboard_unknown_as_falls_back(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=nonexistent-person")
        # falls back to an admin (Charlie is listed first in members.json)
        self.assertIn("All submissions", page.locator("h1").inner_text())
        self.assert_clean(page, "dashboard unknown ?as=")

    def test_S06_timeline_unknown_as_falls_back(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=totally-bogus")
        self.assertTrue(page.locator("h1").inner_text())
        self.assert_clean(page, "timeline unknown ?as=")

    def test_S07_submission_unknown_as_falls_back(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=bogus&id=bryan/2026-09-03-data-memo")
        self.assert_clean(page, "submission unknown ?as=")

    def test_S08_submit_unknown_as_falls_back(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bogus")
        self.assertIn("Submit work", page.locator("h1").inner_text())
        self.assert_clean(page, "submit unknown ?as=")

    def test_S09_xss_in_as_param_does_not_execute(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=" + "<img src=x onerror=alert(1)>")
        self.assertEqual(page._dialogs, [], "an alert fired from the ?as= payload")
        self.assertTrue(page.locator("h1").inner_text())
        self.assert_clean(page, "xss in ?as=")


class TestMissingDataFile(ServedSiteTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.remove(os.path.join(cls.root, "data", "index.json"))

    def test_S10_dashboard_missing_data_file_shows_friendly_card(self):
        page = self.new_page()
        self.goto(page, "index.html")
        self.assertIn("Could not load the tracker", page.content())
        # T.fail() deliberately calls console.error(err); that is expected,
        # so only require there be no *uncaught* exception.
        self.assertEqual(page._page_errors, [], "uncaught exception on missing data file")

    def test_S11_timeline_missing_data_file_shows_friendly_card(self):
        page = self.new_page()
        self.goto(page, "timeline.html")
        self.assertIn("Could not load the tracker", page.content())
        self.assertEqual(page._page_errors, [], "uncaught exception on missing data file")


# ======================================================================
# Dashboard
# ======================================================================
class TestDashboard(ServedSiteTestCase):
    def test_S12_admin_sees_everyone(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        rows = page.locator("table.list tbody tr")
        members_shown = set(page.eval_on_selector_all(
            "table.list tbody tr td:first-child", "els => els.map(e => e.textContent.trim())"))
        self.assertGreater(rows.count(), 0)
        self.assertGreater(len(members_shown), 1, "admin table should include multiple people")
        self.assert_clean(page, "admin dashboard")

    def test_S13_stat_tiles_sum_to_total(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        values = page.eval_on_selector_all(".tiles .tile .value", "els => els.map(e => parseInt(e.textContent, 10))")
        total_subs = len(SAMPLE["submissions"])
        self.assertEqual(len(values), 4, "expected 4 stat tiles")
        self.assertEqual(sum(values), total_subs, f"tile counts {values} should sum to {total_subs}")
        self.assert_clean(page, "stat tiles")

    def test_S14_coverage_grid_one_row_per_member(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        rows = page.locator("table.coverage tbody tr")
        self.assertEqual(rows.count(), len(SAMPLE["members"]))
        self.assert_clean(page, "coverage grid rows")

    def test_S15_coverage_grid_one_column_per_assignment(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        headers = page.locator("table.coverage thead th")
        names = sorted({s["assignment"] for s in SAMPLE["submissions"] if s["assignment"]})
        # +1 for the leading "Person" column; one column per typed name in use
        self.assertEqual(headers.count(), len(names) + 1)
        self.assertEqual([h.strip() for h in headers.all_inner_texts()][1:], names)
        self.assert_clean(page, "coverage grid columns")

    def test_S16_filter_by_person_narrows_table(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        total = len(SAMPLE["submissions"])
        expect = len([s for s in SAMPLE["submissions"] if s["member"] == "bryan"])
        page.select_option("#f-person", "bryan")
        self.assertEqual(page.locator("#f-count").inner_text(), f"{expect} of {total}")
        rows = page.locator("table.list tbody tr")
        self.assertEqual(rows.count(), expect)
        self.assert_clean(page, "filter by person")

    def test_S17_filter_by_assignment_narrows_table(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        total = len(SAMPLE["submissions"])
        expect = len([s for s in SAMPLE["submissions"] if s["assignment"] == "Data collection memo"])
        page.select_option("#f-assignment", "Data collection memo")
        self.assertEqual(page.locator("#f-count").inner_text(), f"{expect} of {total}")
        self.assert_clean(page, "filter by assignment")

    def test_S18_filter_by_status_narrows_table(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        total = len(SAMPLE["submissions"])
        expect = len([s for s in SAMPLE["submissions"] if s["status"] == "approved"])
        page.select_option("#f-status", "approved")
        self.assertEqual(page.locator("#f-count").inner_text(), f"{expect} of {total}")
        self.assert_clean(page, "filter by status")

    def test_S19_member_sees_only_own_rows(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=bryan")
        row_count = page.locator("#table table.list tbody tr").count()
        expect = len([s for s in SAMPLE["submissions"] if s["member"] == "bryan"])
        self.assertEqual(row_count, expect)
        # confirm no "Person" column (member view table has no showPerson)
        self.assertEqual(page.locator("#table table.list thead th:has-text('Person')").count(), 0)
        self.assert_clean(page, "member dashboard")

    def test_S20_member_view_has_submitting_help_and_no_due_list(self):
        # Assignments are typed, not listed, so there is nothing to mark as
        # "still to submit"; the member gets a short how-to card instead.
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=bryan")
        self.assertEqual(page.locator(".card:has-text('Still to submit')").count(), 0)
        self.assertIn("Type the assignment name", page.locator(".card:has-text('Submitting')").inner_text())
        self.assert_clean(page, "member submitting help")

    def test_S21_submit_work_button_links_with_as(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=bryan")
        href = page.locator("a.btn.primary:has-text('Submit work')").get_attribute("href")
        self.assertTrue(href.startswith("submit.html"))
        self.assertIn("as=bryan", href)
        self.assert_clean(page, "submit work link")

    def test_S22_member_with_zero_submissions(self):
        self.write_data(without_member(SAMPLE, "max"))
        page = self.new_page()
        self.goto(page, "index.html?as=max")
        self.assertEqual(page.locator("#table table.list tbody tr").count(), 1)
        self.assertIn("have not submitted anything", page.locator("#table").inner_text())
        self.assertEqual(page.locator(".card:has-text('Submitting')").count(), 1)
        self.assert_clean(page, "zero-submission member")

    def test_S23_orphan_assignment_id_does_not_crash_dashboard(self):
        data = clone(SAMPLE)
        orphan = clone([s for s in data["submissions"] if s["member"] == "bode"][0])
        orphan["id"] = "bode/2026-09-09-orphan"
        orphan["folder"] = "2026-09-09-orphan"
        orphan["assignment"] = "A9"
        orphan["title"] = "Orphaned assignment submission"
        orphan["submitted"] = orphan["updated"] = "2026-09-09"
        orphan["status"] = "submitted"
        orphan["review"] = None
        data["submissions"].append(orphan)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        values = page.eval_on_selector_all(".tiles .tile .value", "els => els.map(e => parseInt(e.textContent, 10))")
        self.assertEqual(sum(values), len(data["submissions"]), "tiles should still count the orphan submission")
        self.assertIn("A9", page.locator("table.list").inner_text())
        self.assert_clean(page, "orphan assignment id")

    def test_S24_xss_title_renders_as_text_not_executed(self):
        data = clone(SAMPLE)
        payload = "<img src=x onerror=alert(1)>"
        data["submissions"][0] = clone(data["submissions"][0])
        data["submissions"][0]["title"] = payload
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        self.assertEqual(page._dialogs, [], "the onerror payload executed an alert")
        self.assertEqual(page.locator("img[src='x']").count(), 0, "payload was inserted as a real <img> element")
        self.assertIn(payload, page.locator("table.list").inner_text())
        self.assert_clean(page, "xss title on dashboard")

    def test_S25_unrecognized_status_value_on_coverage_grid(self):
        """Adversarial data-shape case: a hand-edited index.json with a status
        outside the four known values. site/index.html's coverage-grid cell()
        reads T.STATUS[s.status].color with no fallback (unlike chip(), which
        has one), so this is expected to throw and fail assert_clean."""
        data = clone(SAMPLE)
        bad = clone([s for s in data["submissions"] if s["member"] == "kayla" and s["assignment"] == "Data collection memo"][0])
        bad["id"] = "kayla/2026-09-09-bad-status"
        bad["folder"] = "2026-09-09-bad-status"
        bad["status"] = "needs-revision"
        # must sort after the existing kayla/A2 submission so cell() picks
        # this one as "the latest submission for this member+assignment"
        bad["submitted"] = bad["updated"] = "2026-09-09"
        if bad.get("review"):
            bad["review"]["status"] = "needs-revision"
        data["submissions"].append(bad)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        self.assert_clean(page, "unrecognized status value should not crash the coverage grid")

    def test_S26_empty_state_admin(self):
        self.write_data(EMPTY)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        self.assertIn("0 submissions", page.locator(".lede").inner_text())
        self.assertIn("No submissions yet", page.locator("table.list").inner_text())
        self.assert_clean(page, "empty state admin dashboard")

    def test_S27_empty_state_member(self):
        self.write_data(EMPTY)
        page = self.new_page()
        self.goto(page, "index.html?as=bryan")
        self.assertIn("have not submitted anything", page.locator("#table").inner_text())
        self.assert_clean(page, "empty state member dashboard")


# ======================================================================
# Timeline
# ======================================================================
class TestTimeline(ServedSiteTestCase):
    def test_S28_admin_sees_all_lanes(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        labels = page.locator(".lane-label")
        self.assertEqual(labels.count(), len(SAMPLE["members"]))
        self.assert_clean(page, "admin timeline lanes")

    def test_S29_member_sees_only_own_lane(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=kiley")
        labels = page.eval_on_selector_all(".lane-label", "els => els.map(e => e.textContent)")
        self.assertEqual(labels, ["Kiley"])
        self.assert_clean(page, "member timeline lane")

    def test_S30_one_mark_per_submission(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        marks = page.locator("circle.mark")
        self.assertEqual(marks.count(), len(SAMPLE["submissions"]))
        self.assert_clean(page, "one mark per submission")

    def test_S31_revision_line_when_updated_differs(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        revised = [s for s in SAMPLE["submissions"] if s["updated"] != s["submitted"]]
        self.assertGreater(len(revised), 0, "fixture should include a revised submission")
        self.assertEqual(page.locator("line.rev-line").count(), len(revised))
        self.assertEqual(page.locator("circle.mark-update").count(), len(revised))
        self.assert_clean(page, "revision line")

    def test_S32_no_revision_line_when_dates_equal(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        same = [s for s in SAMPLE["submissions"] if s["updated"] == s["submitted"]]
        total = len(SAMPLE["submissions"])
        self.assertEqual(page.locator("line.rev-line").count(), total - len(same))
        self.assert_clean(page, "no revision line for equal dates")

    def test_S33_no_due_lines_without_an_assignment_list(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        self.assertEqual(page.locator("line.due-line").count(), 0)
        self.assertEqual(page.locator("text.due-label").count(), 0)
        self.assertNotIn("assignment due", page.locator(".legend").inner_text())
        self.assertEqual(page.locator("line.today-line").count(), 1)
        self.assert_clean(page, "no due lines")

    def test_S34_today_line_present(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        self.assertEqual(page.locator("line.today-line").count(), 1)
        self.assertEqual(page.locator("text.today-label").count(), 1)
        self.assert_clean(page, "today line")

    def test_S35_hover_mark_shows_tooltip(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        hit = page.locator("rect.hit").first
        hit.hover()
        page.wait_for_timeout(150)
        tip = page.locator("#tip")
        self.assertFalse(tip.is_hidden(), "tooltip should be visible on hover")
        self.assertTrue(tip.inner_text().strip(), "tooltip should have content")
        self.assert_clean(page, "hover tooltip")

    def test_S36_click_mark_navigates_to_submission(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        page.locator("rect.hit").first.click()
        page.wait_for_load_state("networkidle")
        self.assertIn("submission.html", page.url)
        self.assertIn("id=", page.url)
        self.assert_clean(page, "click mark navigation")

    def test_S37_table_view_lists_same_submissions(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        rows = page.locator("#table table.list tbody tr")
        self.assertEqual(rows.count(), len(SAMPLE["submissions"]))
        self.assert_clean(page, "timeline table view")

    def test_S38_single_lane_member_view(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "timeline.html?as=bryan")
        self.assertEqual(page.locator(".lane-label").count(), 1)
        expect = len([s for s in SAMPLE["submissions"] if s["member"] == "bryan"])
        self.assertEqual(page.locator("circle.mark").count(), expect)
        self.assert_clean(page, "single lane timeline")

    def test_S39_zero_submission_member_lane(self):
        self.write_data(without_member(SAMPLE, "max"))
        page = self.new_page()
        self.goto(page, "timeline.html?as=max")
        self.assertEqual(page.locator(".lane-label").count(), 1)
        self.assertEqual(page.locator("circle.mark").count(), 0)
        self.assert_clean(page, "zero-submission lane")

    def test_S40_today_line_before_all_submissions(self):
        data = clone(SAMPLE)
        future_start = date.today() + timedelta(days=30)
        for i, s in enumerate(data["submissions"]):
            d = (future_start + timedelta(days=i)).isoformat()
            s["submitted"] = d
            s["updated"] = d
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        today_x = float(page.locator("line.today-line").get_attribute("x1"))
        mark_xs = [float(x) for x in page.eval_on_selector_all("circle.mark", "els => els.map(e => e.getAttribute('cx'))")]
        self.assertTrue(mark_xs, "expected at least one mark")
        self.assertTrue(all(today_x < mx for mx in mark_xs),
                         f"today line (x={today_x}) should be left of every mark {mark_xs}")
        self.assert_clean(page, "today line before all submissions")

    def test_S41_unrecognized_status_value_on_timeline(self):
        """Adversarial data-shape case, twin of S-25: timeline.html's mark
        drawing loop also reads T.STATUS[s.status].color with no fallback,
        so an out-of-vocabulary status is expected to throw."""
        data = clone(SAMPLE)
        bad = clone(data["submissions"][0])
        bad["id"] = "bryan/2026-09-09-bad-status"
        bad["folder"] = "2026-09-09-bad-status"
        bad["status"] = "needs-revision"
        data["submissions"].append(bad)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        self.assert_clean(page, "unrecognized status value should not crash the timeline")

    def test_S42_empty_state_timeline(self):
        self.write_data(EMPTY)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        self.assertIn("0 in all", page.locator(".lede").inner_text())
        self.assertEqual(page.locator("circle.mark").count(), 0)
        self.assert_clean(page, "empty state timeline")


# ======================================================================
# Submission page
# ======================================================================
class TestSubmission(ServedSiteTestCase):
    def test_S43_unknown_id_shows_not_found(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=nobody/nothing")
        self.assertIn("Submission not found", page.locator(".page").inner_text())
        self.assert_clean(page, "unknown id")

    def test_S44_member_no_access_to_others_submission(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=max&id=bryan/2026-09-03-data-memo")
        self.assertIn("do not have access", page.locator(".page").inner_text())
        self.assert_clean(page, "member denied access")

    def test_S45_admin_can_open_anything(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=prof-crain&id=bryan/2026-09-03-data-memo")
        self.assertIn("Data collection memo", page.locator("h1").inner_text())
        self.assert_clean(page, "admin access")

    def test_S46_member_can_open_own_submission(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=bryan&id=bryan/2026-09-03-data-memo")
        self.assertIn("Data collection memo", page.locator("h1").inner_text())
        self.assert_clean(page, "member own access")

    def test_S47_shows_title_status_dates_files(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=bryan/2026-09-11-dataset")
        text = page.locator(".page").inner_text()
        self.assertIn("Cleaned results dataset", text)
        # the ".k" label is CSS-uppercased (text-transform), so compare case-insensitively
        self.assertIn("submitted", text.lower())
        self.assertEqual(page.locator(".chip").first.count(), 1)
        self.assertEqual(page.locator(".card:has-text('Files') li").count(), 2)
        self.assert_clean(page, "submission detail fields")

    def test_S48_review_comments_in_order(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=bryan/2026-09-03-data-memo")
        sub = next(s for s in SAMPLE["submissions"] if s["id"] == "bryan/2026-09-03-data-memo")
        expected = [(c["author"], c["date"]) for c in sub["review"]["comments"]]
        names = page.eval_on_selector_all(".thread .name", "els => els.map(e => e.textContent)")
        self.assertEqual(len(names), len(expected))
        for (author, _), name in zip(expected, names):
            self.assertEqual(name, author)
        self.assert_clean(page, "review thread order")

    def test_S49_admin_sees_status_select(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=bryan/2026-09-03-data-memo")
        self.assertEqual(page.locator("#c-status").count(), 1)
        self.assertEqual(page.locator("#c-text").count(), 1)
        self.assert_clean(page, "admin comment box")

    def test_S50_member_no_status_select(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=bryan&id=bryan/2026-09-03-data-memo")
        self.assertEqual(page.locator("#c-status").count(), 0)
        self.assertEqual(page.locator("#c-text").count(), 1)
        self.assert_clean(page, "member comment box")

    def test_S51_preview_with_existing_review_appends_entry(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=bryan/2026-09-03-data-memo")
        page.fill("#c-text", "Looks good now.")
        pre = page.locator("#c-pre").inner_text()
        self.assertIn("append to reviews/bryan/2026-09-03-data-memo.md", pre)
        self.assertRegex(pre, r"## \d{4}-\d{2}-\d{2} Charlie")
        self.assertIn("Looks good now.", pre)
        self.assert_clean(page, "preview existing review")

    def test_S52_preview_with_no_review_produces_full_front_matter(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=kiley/2026-09-06-data-memo")
        page.fill("#c-text", "Please add the finance section.")
        pre = page.locator("#c-pre").inner_text()
        self.assertTrue(pre.startswith("---\nstatus:"), pre[:80])
        self.assertIn("reviewer: Charlie", pre)
        self.assertRegex(pre, r"## \d{4}-\d{2}-\d{2} Charlie")
        self.assertIn("Please add the finance section.", pre)
        self.assert_clean(page, "preview no review yet")

    def test_S53_review_with_zero_comments(self):
        data = clone(SAMPLE)
        for s in data["submissions"]:
            if s["id"] == "kiley/2026-09-06-data-memo":
                s["review"] = {"status": "in-review", "reviewer": "Charlie", "comments": []}
                s["status"] = "in-review"
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=kiley/2026-09-06-data-memo")
        head = page.locator(".card-head:has-text('Review thread')").inner_text()
        self.assertIn("0 comments", head)
        self.assertIn("reviewer Charlie", head)
        self.assert_clean(page, "review with zero comments")

    def test_S54_orphan_assignment_id_on_detail_page(self):
        data = clone(SAMPLE)
        sub = clone(data["submissions"][0])
        sub["id"] = "bryan/2026-09-09-orphan"
        sub["folder"] = "2026-09-09-orphan"
        sub["assignment"] = "A9"
        data["submissions"].append(sub)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=bryan/2026-09-09-orphan")
        self.assertIn("A9", page.locator(".page").inner_text())
        self.assert_clean(page, "orphan assignment detail page")

    def test_S55_xss_title_on_detail_page(self):
        data = clone(SAMPLE)
        payload = "<img src=x onerror=alert(1)>"
        data["submissions"][0] = clone(data["submissions"][0])
        data["submissions"][0]["title"] = payload
        target_id = data["submissions"][0]["id"]
        self.write_data(data)
        page = self.new_page()
        self.goto(page, f"submission.html?as=charlie&id={target_id}")
        self.assertEqual(page._dialogs, [], "the onerror payload executed an alert")
        self.assertEqual(page.locator("img[src='x']").count(), 0)
        self.assertIn(payload, page.locator("h1").inner_text())
        self.assert_clean(page, "xss title on detail page")

    def test_S56_url_encoded_id_resolves(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=prof-crain&id=bryan%2F2026-09-03-data-memo")
        self.assertIn("Data collection memo", page.locator("h1").inner_text())
        self.assert_clean(page, "url-encoded id")

    def test_S57_doubled_slash_is_not_found(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=prof-crain&id=bryan//2026-09-03-data-memo")
        self.assertIn("Submission not found", page.locator(".page").inner_text())
        self.assert_clean(page, "doubled slash id")

    def test_S58_dates_equal_shows_no_revisions(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submission.html?as=charlie&id=aanika/2026-08-28-lit-review")
        self.assertIn("No revisions", page.locator(".meta").inner_text())
        self.assert_clean(page, "dates equal detail page")


# ======================================================================
# Submit page
# ======================================================================
class TestSubmit(ServedSiteTestCase):
    def test_S59_assignment_preselected(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=aanika&assignment=A4")
        self.assertEqual(page.eval_on_selector("#s-assignment", "el => el.value"), "A4")
        self.assert_clean(page, "assignment preselect")

    def test_S60_assignment_param_prefills_text_field_and_names_are_suggested(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=aanika&assignment=Anything%20at%20all")
        self.assertEqual(page.eval_on_selector("#s-assignment", "el => el.value"), "Anything at all")
        names = sorted({s["assignment"] for s in SAMPLE["submissions"] if s["assignment"]})
        options = page.eval_on_selector_all("#assignment-names option", "els => els.map(e => e.value)")
        self.assertEqual(sorted(options), names)
        self.assert_clean(page, "assignment prefill and suggestions")

    def test_S61_title_updates_folder_and_preview(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "Cleaned turnout dataset")
        today = page.evaluate("new Date().toISOString().slice(0,10)")
        expected_folder = f"{today}-cleaned-turnout-dataset"
        tree_folder = page.eval_on_selector("#s-tree b", "el => el.textContent").rstrip("/")
        self.assertEqual(tree_folder, expected_folder)
        preview = page.locator("#s-preview").inner_text()
        self.assertIn("title: Cleaned turnout dataset", preview)
        self.assertIn("assignment: A3", preview)
        self.assert_clean(page, "title updates folder/preview")

    def test_S62_files_are_listed(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.set_input_files("#s-files", [
            {"name": "turnout.csv", "mimeType": "text/csv", "buffer": b"district,year\nPA-07,2020\n"},
            {"name": "codebook.md", "mimeType": "text/markdown", "buffer": b"# Codebook\n"},
        ])
        items = page.eval_on_selector_all("#s-filelist li .mono", "els => els.map(e => e.textContent)")
        self.assertEqual(items, ["turnout.csv", "codebook.md"])
        tree = page.locator("#s-tree").inner_text()
        self.assertIn("turnout.csv", tree)
        self.assertIn("codebook.md", tree)
        self.assert_clean(page, "files listed")

    def test_S63_download_link_is_data_url_with_markdown(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "Turnout dataset")
        href = page.eval_on_selector("#s-download", "el => el.href")
        self.assertTrue(href.startswith("data:text/markdown"))
        import urllib.parse
        decoded = urllib.parse.unquote(href.split(",", 1)[1])
        self.assertIn("title: Turnout dataset", decoded)
        self.assertIn("assignment: A3", decoded)
        self.assert_clean(page, "download data url")

    def test_S64_upload_empty_title_focuses_and_no_window(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "")
        page.click("#s-go")
        page.wait_for_timeout(200)
        self.assertEqual(len(page._popups), 0, "a window opened despite an empty title")
        focused = page.evaluate("document.activeElement.id")
        self.assertEqual(focused, "s-title")
        self.assert_clean(page, "upload empty title")

    def test_S65_upload_with_title_opens_correct_url(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "Cleaned turnout dataset")
        today = page.evaluate("new Date().toISOString().slice(0,10)")
        # Hermetic: answer the popup's github.com request locally so the URL
        # can be asserted without a network round trip (or DNS at all).
        page.context.route(
            "https://github.com/**",
            lambda route: route.fulfill(status=200, content_type="text/html", body="<title>stub</title>"),
        )
        with page.expect_popup() as popup_info:
            page.click("#s-go")
        popup = popup_info.value
        expected = f"https://github.com/{SAMPLE['repo']}/upload/{SAMPLE['branch']}/submissions/bode/{today}-cleaned-turnout-dataset"
        self.assertEqual(popup.url, expected)
        popup.close()
        self.assert_clean(page, "upload with title")

    def test_S66_tabs_toggle_panels(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        self.assertFalse(page.locator("[data-panel=web]").is_hidden())
        self.assertTrue(page.locator("[data-panel=git]").is_hidden())
        page.click(".tabs button[data-tab=git]")
        self.assertTrue(page.locator("[data-panel=web]").is_hidden())
        self.assertFalse(page.locator("[data-panel=git]").is_hidden())
        page.click(".tabs button[data-tab=script]")
        self.assertTrue(page.locator("[data-panel=git]").is_hidden())
        self.assertFalse(page.locator("[data-panel=script]").is_hidden())
        self.assert_clean(page, "tab toggling")

    def test_S67_terminal_panel_reflects_form_values(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "Cleaned turnout dataset")
        today = page.evaluate("new Date().toISOString().slice(0,10)")
        git = page.locator("#s-git").inner_text()
        self.assertIn(f"mkdir -p submissions/bode/{today}-cleaned-turnout-dataset", git)
        self.assertIn("git add", git)
        self.assertIn(sh_quote("Bode: Cleaned turnout dataset (A3)"), git)
        self.assert_clean(page, "terminal panel values")

    def test_S68_helper_script_reflects_form_values(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "Cleaned turnout dataset")
        page.fill("#s-notes", "Two cycles only.")
        script = page.locator("#s-script").inner_text()
        self.assertIn("--as bode", script)
        self.assertIn(f"--assignment {sh_quote('A3')}", script)
        self.assertIn(f"--title {sh_quote('Cleaned turnout dataset')}", script)
        self.assertIn(f"--notes {sh_quote('Two cycles only.')}", script)
        self.assert_clean(page, "helper script values")

    def test_S69_title_with_quotes_produces_safe_commands(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        title = 'He said "hi" there'
        page.fill("#s-title", title)
        folder_prefix_slug = js_slug(title)
        tree_folder = page.eval_on_selector("#s-tree b", "el => el.textContent").rstrip("/")
        self.assertTrue(tree_folder.endswith(folder_prefix_slug), tree_folder)
        git = page.locator("#s-git").inner_text()
        self.assertIn(sh_quote(f"Bode: {title} (A3)"), git)
        self.assert_clean(page, "title with quotes")

    def test_S70_title_with_apostrophes_escaped(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        title = "Bryan's memo, v2"
        page.fill("#s-title", title)
        git = page.locator("#s-git").inner_text()
        script = page.locator("#s-script").inner_text()
        self.assertIn(sh_quote(f"Bode: {title} (A3)"), git)
        self.assertIn(sh_quote(title), script)
        self.assert_clean(page, "title with apostrophes")

    def test_S71_title_with_unicode_produces_safe_slug(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        title = "Café ☕ résumé v2"
        page.fill("#s-title", title)
        expected_slug = js_slug(title)
        tree_folder = page.eval_on_selector("#s-tree b", "el => el.textContent").rstrip("/")
        self.assertTrue(tree_folder.endswith(expected_slug), f"{tree_folder} vs slug {expected_slug}")
        self.assertRegex(expected_slug, r"^[a-z0-9-]+$")
        self.assertNotEqual(expected_slug, "", "slug should not be empty for a title with alnum characters")
        # the raw unicode title should still appear verbatim (safely) in the preview
        self.assertIn(title, page.locator("#s-preview").inner_text())
        self.assert_clean(page, "title with unicode")

    def test_S72_very_long_title_slug_capped(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        title = "This is an extremely long submission title that goes on and on and on past forty characters for sure"
        page.fill("#s-title", title)
        expected_slug = js_slug(title)
        self.assertLessEqual(len(expected_slug), 40)
        tree_folder = page.eval_on_selector("#s-tree b", "el => el.textContent").rstrip("/")
        self.assertTrue(tree_folder.endswith(expected_slug))
        self.assert_clean(page, "very long title")

    def test_S73_leading_trailing_spaces_trimmed(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        title = "   Padded Title   "
        page.fill("#s-title", title)
        expected_slug = js_slug(title.strip())
        tree_folder = page.eval_on_selector("#s-tree b", "el => el.textContent").rstrip("/")
        self.assertTrue(tree_folder.endswith(expected_slug), tree_folder)
        self.assertFalse(tree_folder.endswith("-"), tree_folder)
        self.assert_clean(page, "leading/trailing spaces")

    def test_S74_only_punctuation_falls_back_to_submission(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=bode&assignment=A3")
        page.fill("#s-title", "??!!...")
        tree_folder = page.eval_on_selector("#s-tree b", "el => el.textContent").rstrip("/")
        self.assertTrue(tree_folder.endswith("-submission"), tree_folder)
        self.assert_clean(page, "punctuation-only title")


# ======================================================================
# Responsiveness and dark mode
# ======================================================================
class TestResponsiveAndDarkMode(ServedSiteTestCase):
    def test_S75_dashboard_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        page = self.new_page(viewport={"width": 390, "height": 844})
        self.goto(page, "index.html?as=charlie")
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        self.assertLessEqual(overflow, 1, f"dashboard scrolls horizontally at 390px (overflow={overflow}px)")
        self.assert_clean(page, "dashboard 390px")

    def test_S76_submit_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        page = self.new_page(viewport={"width": 390, "height": 844})
        self.goto(page, "submit.html?as=bode&assignment=A3")
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        self.assertLessEqual(overflow, 1, f"submit page scrolls horizontally at 390px (overflow={overflow}px)")
        self.assert_clean(page, "submit 390px")

    def test_S77_dashboard_dark_mode(self):
        self.write_data(SAMPLE)
        page = self.new_page(color_scheme="dark")
        self.goto(page, "index.html?as=charlie")
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        r, g, b = [int(x) for x in re.findall(r"\d+", bg)[:3]]
        self.assertLess(max(r, g, b), 60, f"expected a dark background in dark mode, got {bg}")
        self.assert_clean(page, "dashboard dark mode")

    def test_S78_timeline_dark_mode(self):
        self.write_data(SAMPLE)
        page = self.new_page(color_scheme="dark")
        self.goto(page, "timeline.html?as=charlie")
        self.assertGreater(page.locator("circle.mark").count(), 0)
        self.assert_clean(page, "timeline dark mode")

    def test_S79_submission_dark_mode(self):
        self.write_data(SAMPLE)
        page = self.new_page(color_scheme="dark")
        self.goto(page, "submission.html?as=charlie&id=bryan/2026-09-03-data-memo")
        self.assertIn("Data collection memo", page.locator("h1").inner_text())
        self.assert_clean(page, "submission dark mode")

    def test_S80_submit_dark_mode(self):
        self.write_data(SAMPLE)
        page = self.new_page(color_scheme="dark")
        self.goto(page, "submit.html?as=bode&assignment=A3")
        self.assertIn("Submit work", page.locator("h1").inner_text())
        self.assert_clean(page, "submit dark mode")


# ======================================================================
# Round two: fix-specific regression tests and new adversarial cases
# (see tests/QA-PATHS.md, S-85 onward)
# ======================================================================
class TestStatusOfFix(ServedSiteTestCase):
    """T.statusOf() fallback (site/assets/app.js): would fail with an
    uncaught TypeError if any of these three call sites reverted to a bare
    T.STATUS[s.status] lookup."""

    def test_S85_unrecognized_status_shows_muted_dot_and_raw_label_chip(self):
        data = clone(SAMPLE)
        bad = clone([s for s in data["submissions"] if s["member"] == "kayla" and s["assignment"] == "Data collection memo"][0])
        bad["id"] = "kayla/2026-09-09-bad-status"
        bad["folder"] = "2026-09-09-bad-status"
        bad["title"] = "Bad Status Coverage Test"
        bad["status"] = "needs-revision"
        bad["submitted"] = bad["updated"] = "2026-09-09"
        bad["review"] = None
        data["submissions"].append(bad)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        dot_style = page.eval_on_selector("a.cell[title='Bad Status Coverage Test'] .dot", "el => el.getAttribute('style')")
        self.assertIn("var(--muted)", dot_style, "coverage-grid dot for an unknown status should use the muted fallback color")
        row = page.locator("table.list tr", has_text="Bad Status Coverage Test")
        self.assertIn("needs-revision", row.inner_text(), "the raw status string should render as the chip label")
        self.assertIn("?", row.locator(".chip .sym").inner_text())
        self.assert_clean(page, "unrecognized status muted dot and raw label chip")

    def test_S86_unrecognized_status_on_detail_page(self):
        data = clone(SAMPLE)
        sub = clone(data["submissions"][0])
        sub["id"] = "bryan/2026-09-09-bad-status-detail"
        sub["folder"] = "2026-09-09-bad-status-detail"
        sub["status"] = "needs-revision"
        data["submissions"].append(sub)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, f"submission.html?as=charlie&id={sub['id']}")
        chip = page.locator(".page-head .chip").last
        self.assertIn("needs-revision", chip.inner_text())
        self.assertIn("?", chip.locator(".sym").inner_text())
        self.assert_clean(page, "unrecognized status on submission detail page")

    def test_S87_unrecognized_status_mark_and_tooltip_on_timeline(self):
        data = clone(SAMPLE)
        bad = clone(data["submissions"][0])
        bad["id"] = "bryan/2026-09-09-bad-status-timeline"
        bad["folder"] = "2026-09-09-bad-status-timeline"
        bad["status"] = "needs-revision"
        bad["submitted"] = bad["updated"] = "2026-09-09"
        data["submissions"].append(bad)
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        mark_fill = page.evaluate(
            "(id) => { const hit = document.querySelector(`rect.hit[data-id='${id}']`); "
            "const mark = hit && hit.previousElementSibling; "
            "return mark && mark.classList.contains('mark') ? mark.getAttribute('fill') : null; }",
            bad["id"],
        )
        self.assertEqual(mark_fill, "var(--muted)", "the timeline mark for an unknown status should use the muted fallback color")
        page.locator(f"rect.hit[data-id='{bad['id']}']").hover()
        page.wait_for_timeout(150)
        tip_text = page.locator("#tip").inner_text()
        self.assertIn("needs-revision", tip_text, "the tooltip chip should show the raw status label")
        self.assert_clean(page, "unrecognized status timeline mark and tooltip")


class TestNarrowAndWideViewports(ServedSiteTestCase):
    """CSS responsive fix (site/assets/style.css): S-75/S-76 already cover
    the dashboard (admin) and submit page (member) at 390px; these fill in
    the remaining page/role combinations, plus a desktop check that the top
    bar did not start wrapping at normal widths."""

    def assert_no_h_scroll_390(self, path, msg):
        page = self.new_page(viewport={"width": 390, "height": 844})
        self.goto(page, path)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        self.assertLessEqual(overflow, 1, f"{msg} scrolls horizontally at 390px (overflow={overflow}px)")
        self.assert_clean(page, msg)

    def test_S88_dashboard_member_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        self.assert_no_h_scroll_390("index.html?as=bryan", "member dashboard 390px")

    def test_S89_timeline_admin_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        self.assert_no_h_scroll_390("timeline.html?as=charlie", "admin timeline 390px")

    def test_S90_timeline_member_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        self.assert_no_h_scroll_390("timeline.html?as=bryan", "member timeline 390px")

    def test_S91_submission_admin_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        self.assert_no_h_scroll_390("submission.html?as=charlie&id=bryan/2026-09-03-data-memo", "admin submission page 390px")

    def test_S92_submission_member_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        self.assert_no_h_scroll_390("submission.html?as=bryan&id=bryan/2026-09-03-data-memo", "member submission page 390px")

    def test_S93_submit_admin_no_horizontal_scroll_at_390(self):
        self.write_data(SAMPLE)
        self.assert_no_h_scroll_390("submit.html?as=charlie&assignment=A2", "admin submit page 390px")

    def test_S94_desktop_topbar_single_row_at_1440(self):
        self.write_data(SAMPLE)
        page = self.new_page(viewport={"width": 1440, "height": 900})
        self.goto(page, "index.html?as=charlie")
        tops = page.eval_on_selector_all(
            ".topbar .inner > *", "els => els.map(e => Math.round(e.getBoundingClientRect().top))"
        )
        self.assertGreater(len(tops), 1, "expected brand/nav/viewer as direct children of .topbar .inner")
        # Sub-pixel/line-height differences between children (the two-line
        # .brand vs. single-line .nav/.viewer) can put their tops a couple
        # of px apart even on one visual row; only a real wrap (the >760px
        # media query firing early) would push a child tens of px down.
        self.assertLessEqual(
            max(tops) - min(tops), 4, f"topbar children should share one row at 1440px, got tops {tops}"
        )
        self.assert_clean(page, "desktop topbar single row")


class TestEmptyTextFix(ServedSiteTestCase):
    """index.html's conditional emptyText (fix #6): S-26 already covers the
    unfiltered, zero-submission case ("No submissions yet."); this covers
    the filtered-to-zero-rows case with non-empty data, which must instead
    blame the filters."""

    def test_S95_admin_filtered_empty_state_says_nothing_matches(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        # Prof. Crain has no submissions in the sample data.
        page.select_option("#f-person", "prof-crain")
        text = page.locator("#table").inner_text()
        self.assertIn("Nothing matches these filters.", text)
        self.assertNotIn("No submissions yet.", text)
        self.assert_clean(page, "admin filtered empty state")


class TestNewAdversarialCases(ServedSiteTestCase):
    """Cases outside the seven round-one fixes, probed fresh for this pass.
    Each either confirms the site already handles the case, or is left
    failing to document a real finding (see the QA report)."""

    def test_S96_member_id_with_hyphen_through_submit_flow(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "submit.html?as=prof-crain&assignment=A2")
        page.fill("#s-title", "Hyphen Id Test")
        today = page.evaluate("new Date().toISOString().slice(0,10)")
        tree = page.locator("#s-tree").inner_text()
        self.assertIn("prof-crain", tree)
        git = page.locator("#s-git").inner_text()
        self.assertIn(f"submissions/prof-crain/{today}-hyphen-id-test", git)
        script = page.locator("#s-script").inner_text()
        self.assertIn("--as prof-crain", script)
        msg = page.locator("#s-msg").inner_text()
        self.assertIn("Prof. Crain: Hyphen Id Test (A2)", msg)
        self.assert_clean(page, "member id with hyphen through submit flow")

    def test_S97_empty_files_list_on_timeline_and_detail_page(self):
        data = clone(SAMPLE)
        sub = clone(data["submissions"][0])
        sub["id"] = "bryan/2026-09-09-no-files"
        sub["folder"] = "2026-09-09-no-files"
        sub["title"] = "No Files Test"
        sub["files"] = []
        sub["review"] = None
        sub["status"] = "submitted"
        data["submissions"].append(sub)
        self.write_data(data)

        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        rows = page.locator("#table table.list tbody tr")
        self.assertEqual(rows.count(), len(data["submissions"]))
        self.assert_clean(page, "timeline with empty-files submission")

        page2 = self.new_page()
        self.goto(page2, f"submission.html?as=charlie&id={sub['id']}")
        self.assertIn("No files beyond submission.md.", page2.locator(".page").inner_text())
        self.assertEqual(page2.locator(".card-head:has-text('Files') .small.muted").inner_text(), "0")
        self.assert_clean(page2, "detail page with empty files list")

    def test_S98_review_reviewer_not_in_members_json(self):
        data = clone(SAMPLE)
        target = next(s for s in data["submissions"] if s.get("review"))
        idx = data["submissions"].index(target)
        data["submissions"][idx] = clone(target)
        data["submissions"][idx]["review"]["reviewer"] = "Guest TA"
        target_id = data["submissions"][idx]["id"]
        self.write_data(data)

        page = self.new_page()
        self.goto(page, f"submission.html?as=charlie&id={target_id}")
        head = page.locator(".card-head:has-text('Review thread')").inner_text()
        self.assertIn("Guest TA", head)
        self.assert_clean(page, "reviewer not in members.json (detail page)")

        page2 = self.new_page()
        self.goto(page2, "index.html?as=charlie")
        self.assertIn("Guest TA", page2.locator("table.list").inner_text())
        self.assert_clean(page2, "reviewer not in members.json (admin table)")

    def test_S99_comment_author_not_in_members_json(self):
        data = clone(SAMPLE)
        target = next(s for s in data["submissions"] if s.get("review") and s["review"]["comments"])
        idx = data["submissions"].index(target)
        data["submissions"][idx] = clone(target)
        data["submissions"][idx]["review"]["comments"][0]["author"] = "Random TA"
        target_id = data["submissions"][idx]["id"]
        self.write_data(data)

        page = self.new_page()
        self.goto(page, f"submission.html?as=charlie&id={target_id}")
        first_item = page.locator(".thread li").first
        self.assertIn("Random TA", first_item.inner_text())
        self.assertEqual(first_item.locator(".avatar").inner_text(), "RT")
        self.assertEqual(first_item.locator(".avatar.admin").count(), 0, "an unknown author should not get the admin badge")
        self.assert_clean(page, "comment author not in members.json")

    def test_S100_initials_edge_cases_do_not_crash(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        result = page.evaluate("[window.Tracker.initials(''), window.Tracker.initials('Solo')]")
        self.assertEqual(result, ["", "S"])
        self.assert_clean(page, "initials edge cases")

    def test_S101_very_long_title_in_tooltip_and_coverage_grid(self):
        data = clone(SAMPLE)
        long_title = "A " + "very " * 40 + "long submission title"
        bad = clone([s for s in data["submissions"] if s["member"] == "kayla" and s["assignment"] == "Data collection memo"][0])
        bad["id"] = "kayla/2026-09-09-long-title"
        bad["folder"] = "2026-09-09-long-title"
        bad["title"] = long_title
        bad["submitted"] = bad["updated"] = "2026-09-09"
        data["submissions"].append(bad)
        self.write_data(data)

        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        title_attr = page.eval_on_selector(f"a.cell[title='{long_title}']", "el => el.getAttribute('title')")
        self.assertEqual(title_attr, long_title)
        self.assert_clean(page, "long title coverage grid")

        page2 = self.new_page()
        self.goto(page2, "timeline.html?as=charlie")
        page2.locator(f"rect.hit[data-id='{bad['id']}']").hover()
        page2.wait_for_timeout(150)
        self.assertIn(long_title, page2.locator("#tip").inner_text())
        self.assert_clean(page2, "long title timeline tooltip")

    def test_S102_as_param_uppercase_and_url_encoded(self):
        self.write_data(SAMPLE)
        page = self.new_page()
        self.goto(page, "index.html?as=BRYAN")
        self.assertIn(
            "All submissions", page.locator("h1").inner_text(),
            "an uppercase id must not case-insensitively match; it should fall back like any unknown id",
        )
        self.assert_clean(page, "uppercase ?as=")

        page2 = self.new_page()
        self.goto(page2, "index.html?as=bry%61n")
        self.assertIn(
            "Your submissions", page2.locator("h1").inner_text(),
            "a percent-encoded id that decodes to a real member id should match normally",
        )
        self.assert_clean(page2, "url-encoded ?as=")

    def test_S103_two_same_day_submissions_both_clickable(self):
        import urllib.parse

        data = clone(SAMPLE)
        base = clone(next(s for s in data["submissions"] if s["member"] == "aanika"))
        first = clone(base)
        first.update(id="aanika/2026-09-20-first", folder="2026-09-20-first", title="Same Day First",
                      submitted="2026-09-20", updated="2026-09-20", review=None, status="submitted")
        second = clone(base)
        second.update(id="aanika/2026-09-20-second", folder="2026-09-20-second", title="Same Day Second",
                       submitted="2026-09-20", updated="2026-09-20", review=None, status="submitted")
        data["submissions"] += [first, second]
        self.write_data(data)

        page = self.new_page()
        self.goto(page, "timeline.html?as=charlie")
        self.assertEqual(page.locator(f"rect.hit[data-id='{first['id']}']").count(), 1)
        self.assertEqual(page.locator(f"rect.hit[data-id='{second['id']}']").count(), 1)
        self.assert_clean(page, "overlapping same-day marks render")

        for target_id in (first["id"], second["id"]):
            p = self.new_page()
            self.goto(p, "timeline.html?as=charlie")
            with p.expect_navigation():
                p.locator(f"rect.hit[data-id='{target_id}']").dispatch_event("click")
            self.assertIn(
                f"id={urllib.parse.quote(target_id, safe='')}", p.url,
                f"the hit rect for {target_id} should navigate to its own submission even though it "
                "fully overlaps the other same-day mark",
            )

    def test_S106_two_same_day_marks_both_reachable_by_a_real_click(self):
        """Regression for a real finding: two submissions from the same
        person on the same day with no revision used to produce
        pixel-identical timeline hit-rectangles (same x, same width, same
        lane), so a real mouse click could only ever land on whichever one
        was drawn last and the other mark was unreachable from the chart.
        timeline.html now spreads marks that land within 12px of each other
        vertically inside the lane, each with its own hit rectangle. This
        test clicks at the on-screen centre of each submission's own hit
        rectangle in turn and expects each to navigate to itself (see
        test_S103 for the per-element click-handler check, which does not
        depend on real hit-testing). The click is wrapped in
        expect_navigation because a bare mouse.click followed by
        wait_for_load_state returns before the click's navigation commits,
        leaving page.url stale even when the click hit the right element."""
        import urllib.parse

        data = clone(SAMPLE)
        base = clone(next(s for s in data["submissions"] if s["member"] == "aanika"))
        first = clone(base)
        first.update(id="aanika/2026-09-21-first", folder="2026-09-21-first", title="Same Day Real Click First",
                      submitted="2026-09-21", updated="2026-09-21", review=None, status="submitted")
        second = clone(base)
        second.update(id="aanika/2026-09-21-second", folder="2026-09-21-second", title="Same Day Real Click Second",
                       submitted="2026-09-21", updated="2026-09-21", review=None, status="submitted")
        data["submissions"] += [first, second]
        self.write_data(data)

        for target in (first, second):
            p = self.new_page()
            self.goto(p, "timeline.html?as=charlie")
            box = p.eval_on_selector(f"rect.hit[data-id='{target['id']}']", "el => el.getBoundingClientRect()")
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            with p.expect_navigation():
                p.mouse.click(cx, cy)
            self.assertIn(
                f"id={urllib.parse.quote(target['id'], safe='')}", p.url,
                f"a real click centered on {target['id']}'s own hit rectangle should open its own "
                "submission, even though another same-day mark fully overlaps it",
            )

    def test_S104_index_json_missing_members_key_shows_friendly_card(self):
        data = clone(SAMPLE)
        del data["members"]
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        self.assertIn("Could not load the tracker", page.content())
        self.assertEqual(page._page_errors, [], "a missing 'members' key should be caught by T.fail(), not thrown as an uncaught exception")

    def test_S105_index_json_missing_members_key_shows_friendly_card(self):
        data = clone(SAMPLE)
        del data["members"]
        self.write_data(data)
        page = self.new_page()
        self.goto(page, "index.html?as=charlie")
        self.assertIn("Could not load the tracker", page.content())
        self.assertEqual(page._page_errors, [], "a missing 'members' key should be caught by T.fail(), not thrown as an uncaught exception")


if __name__ == "__main__":
    unittest.main()
