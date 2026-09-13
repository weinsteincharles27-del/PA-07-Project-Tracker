#!/usr/bin/env python3
"""Render the tracker with sample data and screenshot every page with Playwright.

    python3 scripts/mockup.py            # writes mockups/*.png
    python3 scripts/mockup.py --serve    # also keep the sample site running for a look

The site folder is copied to a scratch directory with the sample index swapped
in, served over a local HTTP port, and captured at 1440px wide. Nothing under
site/ or submissions/ is touched.
"""
import argparse
import functools
import http.server
import os
import shutil
import socket
import sys
import tempfile
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
OUT = os.path.join(REPO, "mockups")

SHOTS = [
    # (file name, url path, description)
    ("01-dashboard-admin.png",   "index.html?as=charlie",   "Dashboard as an admin: everyone's work"),
    ("02-dashboard-member.png",  "index.html?as=bryan",     "Dashboard as a member: only their own work"),
    ("03-timeline-admin.png",    "timeline.html?as=charlie", "Timeline, one lane per person"),
    ("04-timeline-member.png",   "timeline.html?as=kiley",  "Timeline as a member: their lane only"),
    ("05-submission-review.png", "submission.html?as=prof-crain&id=bryan%2F2026-09-03-data-memo", "A submission with its review thread, as Prof. Crain"),
    ("06-submit.png",            "submit.html?as=aanika&assignment=A4", "The submit form, as a member"),
    ("07-no-access.png",         "submission.html?as=max&id=bryan%2F2026-09-03-data-memo", "A member opening someone else's submission"),
]


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true", help="keep serving the sample site after the screenshots")
    ap.add_argument("--width", type=int, default=1440)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is not installed: pip install playwright && playwright install chromium")

    tmp = tempfile.mkdtemp(prefix="tracker-mockup-")
    root = os.path.join(tmp, "site")
    shutil.copytree(SITE, root)
    shutil.copy(os.path.join(SITE, "data", "sample-index.json"), os.path.join(root, "data", "index.json"))
    httpd, port = serve(root)
    base = f"http://127.0.0.1:{port}/"
    os.makedirs(OUT, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": args.width, "height": 900}, device_scale_factor=2, color_scheme="light")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        for name, path, desc in SHOTS:
            page.goto(base + path, wait_until="networkidle")
            page.wait_for_selector(".page h1, .page h2")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=os.path.join(OUT, name), full_page=True)
            print(f"{name:28s} {desc}")
        # One interaction shot: type into the submit form so the generated output is visible.
        page.goto(base + "submit.html?as=bode&assignment=A3", wait_until="networkidle")
        page.fill("#s-title", "Cleaned turnout dataset")
        page.fill("#s-notes", "Two cycles only; 2018 still being checked.")
        page.set_input_files("#s-files", [
            {"name": "turnout.csv", "mimeType": "text/csv", "buffer": b"district,year,turnout\nPA-07,2020,0.71\n"},
            {"name": "codebook.md", "mimeType": "text/markdown", "buffer": b"# Codebook\n"},
        ])
        page.screenshot(path=os.path.join(OUT, "08-submit-filled.png"), full_page=True)
        print(f"{'08-submit-filled.png':28s} The submit form filled in, showing what gets created")
        browser.close()
        if errors:
            print("\nBrowser errors:\n  " + "\n  ".join(errors), file=sys.stderr)
            sys.exit(1)

    if args.serve:
        print(f"\nSample site running at {base}index.html (Ctrl+C to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    httpd.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
