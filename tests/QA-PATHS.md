# QA paths: PA-07 Project Tracker (static site)

Checklist of happy and unhappy paths identified for site/index.html (dashboard),
site/timeline.html, site/submission.html, site/submit.html, and the shared
runtime in site/assets/app.js. Each row has an id, a one-line description, and
whether an automated Playwright test covers it (see tests/test_site.py; test
method names embed the id, e.g. test_S11...). "Covered" means a test exists
and runs; it does not mean the test passes (see the QA report for failures).

## Identity, navigation, top bar

| id | description | covered |
|----|--------------|---------|
| S-01 | Nav links on the dashboard carry `?as=<viewer>` | yes |
| S-02 | Nav links on the timeline carry `?as=<viewer>` | yes |
| S-03 | Nav links on the submit page carry `?as=<viewer>` | yes |
| S-04 | Viewing-as select switches identity and reloads the page | yes |
| S-05 | Unknown `?as=` on the dashboard falls back to a default (admin) viewer, no crash | yes |
| S-06 | Unknown `?as=` on the timeline falls back without crashing | yes |
| S-07 | Unknown `?as=` on submission.html falls back without crashing | yes |
| S-08 | Unknown `?as=` on submit.html falls back without crashing | yes |
| S-09 | `?as=` containing an XSS-ish string does not execute and still falls back cleanly | yes |
| S-10 | Missing data file (`data/index.json` 404) shows the "Could not load the tracker" card on the dashboard | yes |
| S-11 | Missing data file also shows the friendly card on the timeline (same shared loader) | yes |

## Dashboard (index.html)

| id | description | covered |
|----|--------------|---------|
| S-12 | Admin dashboard shows everyone's submissions | yes |
| S-13 | Admin stat tiles: the four counts sum to the total submissions shown | yes |
| S-14 | Admin coverage grid has exactly one row per member | yes |
| S-15 | Admin coverage grid has exactly one column per assignment | yes |
| S-16 | Admin filter by person narrows the table and the "N of M" count updates | yes |
| S-17 | Admin filter by assignment narrows the table and the count updates | yes |
| S-18 | Admin filter by status narrows the table and the count updates | yes |
| S-19 | Member dashboard shows only that member's own rows | yes |
| S-20 | Member view has no "Still to submit" list (assignments are typed, not listed) and shows a short how-to card instead | yes |
| S-21 | Member "Submit work" button links to submit.html with `?as=` | yes |
| S-22 | Member with zero submissions: empty table, all assignments listed as still-to-submit, no crash | yes |
| S-23 | A submission with an assignment name nobody else has used gets its own coverage-grid column and does not crash the dashboard | yes |
| S-24 | A submission title containing `<img src=x onerror=alert(1)>` renders as literal text on the dashboard table, does not execute | yes |
| S-25 | A submission with a status value outside the four known statuses (e.g. a hand-edited index.json) | yes (fixed in round two; passes, see report) |
| S-26 | Empty state: real site/data/index.json (0 submissions), admin view renders with sensible empty text, no JS errors | yes (fixed in round two; passes, see report) |
| S-27 | Empty state: real site/data/index.json (0 submissions), member view renders with sensible empty text, no JS errors | yes |

## Timeline (timeline.html)

| id | description | covered |
|----|--------------|---------|
| S-28 | Admin sees one lane per member (all lanes) | yes |
| S-29 | Member sees only their own lane | yes |
| S-30 | One filled mark is drawn per submission | yes |
| S-31 | A revision line and hollow mark are drawn when updated != submitted | yes |
| S-32 | No revision line is drawn when updated == submitted (dates equal) | yes |
| S-33 | No due lines or "assignment due" legend entry (no assignment list); the today line is still drawn | yes |
| S-34 | A "today" line is drawn | yes |
| S-35 | Hovering a mark shows the tooltip with title, person, assignment, dates | yes |
| S-36 | Clicking a mark navigates to that submission's page | yes |
| S-37 | The table view below the chart lists the same submissions | yes |
| S-38 | Timeline with a single lane (a member's own view) renders correctly | yes |
| S-39 | A member with zero submissions: their lane renders with zero marks, no crash | yes |
| S-40 | The "today" line renders to the left of every mark when today is before all submission dates | yes |
| S-41 | A submission with an unrecognized status value | yes (fixed in round two; passes, see report) |
| S-42 | Empty state: real 0-submission data renders the timeline with no crash and sensible empty text | yes |

## Submission page (submission.html)

| id | description | covered |
|----|--------------|---------|
| S-43 | Unknown `?id=` shows "Submission not found" | yes |
| S-44 | A member opening someone else's id gets "You do not have access" | yes |
| S-45 | An admin can open any member's submission | yes |
| S-46 | A member can open their own submission | yes |
| S-47 | Page shows title, status chip, submitted/updated dates, files list | yes |
| S-48 | Review thread comments render in order, with author and date | yes |
| S-49 | Admin sees a status select plus a comment box | yes |
| S-50 | Member sees a comment box but no status select | yes |
| S-51 | "Copy as markdown" / preview on a submission with an existing review appends only a dated `##` entry | yes |
| S-52 | Preview on a submission with no review yet (`review: null`) produces full front matter (status + reviewer) plus the entry | yes |
| S-53 | A submission whose review has zero comments shows "0 comments" and does not crash | yes |
| S-54 | A submission with an unusual assignment name renders on the detail page without crashing | yes |
| S-55 | A submission title containing `<img src=x onerror=alert(1)>` renders as literal text (h1), does not execute | yes |
| S-56 | URL-encoded id (`%2F` for the slash, as used by nav links) resolves the correct submission | yes |
| S-57 | A doubled slash in `?id=` is treated as not found, not a crash | yes |
| S-58 | Dates equal (submitted == updated) shows "No revisions" on the detail page | yes |

## Submit page (submit.html)

| id | description | covered |
|----|--------------|---------|
| S-59 | `?assignment=A4` preselects that assignment | yes |
| S-60 | Any `?assignment=` value prefills the text field as given; the datalist suggests every assignment name already in use | yes |
| S-61 | Typing a title updates the folder name in "What gets created" and the submission.md preview | yes |
| S-62 | Adding files lists them in the file list and the tree | yes |
| S-63 | The download link is a `data:` URL containing the generated markdown | yes |
| S-64 | Clicking "Upload on GitHub" with an empty title focuses the title field and does not open a window | yes |
| S-65 | Clicking "Upload on GitHub" with a title opens `https://github.com/<repo>/upload/<branch>/submissions/<member>/<folder>` | yes |
| S-66 | The three tabs (On GitHub / Terminal / Helper script) toggle their panels | yes |
| S-67 | The Terminal panel's commands reflect the current form values | yes |
| S-68 | The Helper script command reflects the current form values | yes |
| S-69 | A title with quotes produces a safe slug and a correctly single-quoted shell/script command | yes |
| S-70 | A title with apostrophes is escaped correctly in shell/script commands (`'\''` pattern) | yes |
| S-71 | A title with unicode characters produces a safe (non-empty, ascii) slug | yes |
| S-72 | A very long title produces a slug capped at 40 characters | yes |
| S-73 | A title with leading/trailing spaces is trimmed before it reaches the slug/commands | yes |
| S-74 | A title that is only punctuation falls back to the default "submission" slug | yes |

## Responsiveness and dark mode

| id | description | covered |
|----|--------------|---------|
| S-75 | At 390px wide, the dashboard body does not scroll horizontally | yes (fixed in round two; passes, see report) |
| S-76 | At 390px wide, the submit page body does not scroll horizontally | yes (fixed in round two; passes, see report) |
| S-77 | Dark mode renders the dashboard with a dark background and no JS errors | yes |
| S-78 | Dark mode renders the timeline with no JS errors | yes |
| S-79 | Dark mode renders the submission page with no JS errors | yes |
| S-80 | Dark mode renders the submit page with no JS errors | yes |

## Round two: fix-specific regressions and new adversarial cases

Added after the round-one bug-fix pass (see the QA report for verdicts). S-25,
S-41, and S-26 above already exercise the `statusOf`/emptyText fixes and are
unchanged; the rows below fill in the remaining call sites and cases called
out in that review.

| id | description | covered |
|----|--------------|---------|
| S-85 | Unrecognized status: admin coverage-grid dot uses the muted fallback color and the submissions-table chip shows the raw status label with a "?" symbol | yes |
| S-86 | Unrecognized status on the submission detail page: header chip shows the raw label and "?", no crash | yes |
| S-87 | Unrecognized status on the timeline: the mark's fill is the muted fallback color and its hover tooltip shows the raw label | yes |
| S-88 | At 390px wide, the dashboard (member viewer) does not scroll horizontally | yes |
| S-89 | At 390px wide, the timeline (admin viewer) does not scroll horizontally | yes |
| S-90 | At 390px wide, the timeline (member viewer) does not scroll horizontally | yes |
| S-91 | At 390px wide, the submission detail page (admin viewer) does not scroll horizontally | yes |
| S-92 | At 390px wide, the submission detail page (member viewer) does not scroll horizontally | yes |
| S-93 | At 390px wide, the submit page (admin viewer) does not scroll horizontally | yes |
| S-94 | At 1440px wide, the top bar's brand/nav/viewer controls stay on one row (no wrap) | yes |
| S-95 | Admin dashboard: a filter combination matching zero rows shows "Nothing matches these filters." (contrast with S-26's unfiltered "No submissions yet.") | yes |
| S-96 | A member id with a hyphen (`prof-crain`) flows correctly through the submit page's folder tree, terminal commands, and helper script | yes |
| S-97 | A submission with an empty `files` list renders correctly on the timeline table and the detail page ("0", "No files beyond submission.md.") | yes |
| S-98 | A review `reviewer` not present in members.json renders as plain text on the detail page and the admin table, no crash | yes |
| S-99 | A comment `author` not present in members.json gets initials from the raw name, no admin badge, no crash | yes |
| S-100 | `T.initials()` does not crash on an empty string or a single-word name | yes |
| S-101 | A very long submission title renders in full in the coverage-grid `title` attribute and the timeline hover tooltip | yes |
| S-102 | `?as=` is case-sensitive (an uppercase id falls back like any unknown id) and percent-encoding that decodes to a real id matches normally | yes |
| S-103 | Two submissions from the same person on the same day: each hit rectangle's own click handler navigates to the right submission when activated directly (id/href wiring is correct per element) | yes |
| S-104 | `data/index.json` valid JSON missing the `members` key hits the friendly "Could not load the tracker" card, not a blank page or uncaught exception | yes |
| S-105 | `data/index.json` valid JSON missing the `members` key hits the same friendly card | yes |
| S-106 | Two same-day, same-person submissions with no revision: a real mouse click centered on either one's hit rectangle should open that submission | yes (fixed: same-day marks are stacked vertically in the lane, each with its own hit target) |

## Identified but not automated

| id | description | why not automated |
|----|--------------|---------------------|
| S-81 | Actually completing a GitHub upload/commit end to end | Requires real GitHub auth and a live repo; the site only opens a `window.open` URL, which the tests verify without following it. |
| S-82 | Verifying "Copy as markdown" / "Copy commands" actually reach the OS clipboard | Headless Chromium's clipboard permission model is unreliable in a sandboxed test run; tests instead assert the equivalent preview/`textContent` the copy button uses, which exercises the same code path. |
| S-83 | Cross-browser rendering (Firefox, WebKit) | Only Chromium is installed for this Python's Playwright in this environment; all tests run on Chromium only. |
| S-84 | Real screen-reader / accessibility tree audit | Out of scope for this pass; the timeline SVG has `role="img"` and an `aria-label`, but no full a11y audit was done. |

## File viewer

| id | path | covered |
|---|---|---|
| S-107 | Clicking a PDF button on the dashboard opens the viewer (iframe on the file, name, open and download links) without following the row link | yes |
| S-108 | Escape and the Close button hide the viewer and drop the iframe | yes |
| S-109 | A non-PDF file is a plain new-tab link, and the file is served next to the site | yes |
| S-110 | File buttons on the submission page open the viewer | yes |
| S-111 | A member can open their own PDF | yes |

## Bare folders

| id | path | covered |
|---|---|---|
| S-112 | A submission without `submission.md` shows a callout on its page with a Submit-page link for its owner | yes |
| S-113 | The same submission renders for an admin with a "no assignment" chip and appears on the dashboard | yes |

## Uploading from the site

| id | path | covered |
|---|---|---|
| S-114 | With `upload_url` configured, the Submit page shows a passcode field, an Upload button, and demotes the GitHub flow to "Other ways to submit" | yes |
| S-115 | Missing files or passcode are caught on the client; nothing is posted | yes |
| S-116 | Upload posts a multipart form (member, passcode, assignment, title, notes, files) and shows the success callout with folder, dashboard link, and commit link | yes |
| S-117 | A server error is shown in a warning callout and the form stays usable | yes |
| S-118 | Without `upload_url` the GitHub flow is unchanged | yes |

## The upload worker (run in Chromium against a fake GitHub)

| id | path | covered |
|---|---|---|
| W-01 | OPTIONS preflight returns 204 with CORS headers for the allowed origin | yes |
| W-02 | GET is rejected with 405 | yes |
| W-03 | A wrong passcode is rejected with 403 before any GitHub call | yes |
| W-04 | A member id not in members.json is rejected after reading the roster | yes |
| W-05 | Missing files, blank title or assignment, or a malformed member id are rejected | yes |
| W-06 | Happy path: roster, folder check, one blob per file plus submission.md, tree on the base tree, commit authored as the member, ref update; response carries folder, files, commit | yes |
| W-07 | An existing folder for the same title today gets a -2 suffix | yes |
| W-08 | A file over 25 MB is rejected with 413 before any GitHub call | yes |
| W-09 | Path-traversal names are reduced to the base name; duplicate names and submission.md are deduplicated | yes |
| W-10 | A foreign Origin does not get echoed in CORS; localhost is allowed for local development | yes |
| W-11 | A non-fast-forward ref update is retried on the new head | yes |
| W-12 | A missing worker setting is reported clearly | yes |
| W-13 | GET on the worker (any path but /upload) redirects to the published site | yes |
| W-14 | POST to a path other than /upload is a clear 404 naming the endpoint | yes |
| W-15 | POST and OPTIONS on /upload reach the handler (trailing slash tolerated) | yes |
| W-16 | A GitHub failure during the write steps comes back as a JSON 502 with CORS headers (never an uncaught crash) | yes |
