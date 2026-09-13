# Upload endpoint

`upload.js` is the small service that lets people submit from the website
instead of through GitHub. The Submit page posts the form to it; it checks the
group passcode and writes the files into this repo as git blobs (one commit
per submission, authored as the member). The publish workflow then rebuilds
the site, so the submission shows up on the dashboard about a minute later.

It runs on Cloudflare Workers, which is free at this scale (100,000 requests a
day) and needs no server of your own. Setup is done in two browser tabs, no
tools to install. About ten minutes.

## 1. A GitHub token the worker can commit with

1. On GitHub, open **Settings** (your profile), then **Developer settings**,
   **Personal access tokens**, **Fine-grained tokens**, **Generate new token**.
2. Name it `pa07-tracker-upload`. Expiration: a year is fine (you will get a
   reminder email before it lapses).
3. Repository access: **Only select repositories**, pick `PA-07-Project-Tracker`.
4. Permissions, Repository permissions: **Contents: Read and write**. Nothing else.
5. Generate, and copy the token. It is shown once.

## 2. The worker

The worker is connected to this repo on Cloudflare (Workers & Pages, the
`pa-07-project-tracker` worker, Settings, Build). Every push to `main`
redeploys it. `wrangler.toml` in the repo root tells Cloudflare what to run:
`worker/upload.js`, with the plain settings (repo, branch, allowed origin,
site URL) as variables.

The two secrets are set once in the dashboard and survive redeploys: on the
worker's page, **Settings**, **Variables and Secrets**, add

| name | type | value |
|---|---|---|
| `GITHUB_TOKEN` | Secret | the token from step 1 |
| `GROUP_PASSCODE` | Secret | a passcode you will give the group |

The endpoint is `https://pa-07-project-tracker.weinsteincharles27.workers.dev/upload`.
Opening the worker's address in a browser just redirects to the site.

If you ever set it up from scratch without the git connection: Workers &
Pages, Create Worker, Edit code, paste `upload.js`, Deploy, then add all of
`GITHUB_TOKEN`, `GITHUB_REPO`, `GROUP_PASSCODE`, `ALLOWED_ORIGIN`, `SITE_URL`
under Variables and Secrets.

## 3. Point the site at it

`members.json` carries the endpoint:

```json
"upload_url": "https://pa-07-project-tracker.weinsteincharles27.workers.dev/upload",
```

Once the site rebuilds, the Submit page shows a passcode field and an
**Upload** button, and members never see GitHub.

## Checking it works

Open the Submit page, pick a name, fill in the form with a small test file and
the passcode, and press Upload. You should see "Uploaded" with the folder
name and a link to the commit, and the dashboard should list it a minute
later. If it fails, the message on the page says why (wrong passcode, missing
setting, GitHub error), and the worker's **Logs** tab on Cloudflare shows the
details.

## Changing the passcode or the token

Edit the secret on the worker's **Variables and Secrets** page. Nothing in the
repo changes. If a token expires, uploads fail with "GitHub 401"; make a new
token and replace the secret.

## What it will not do

- It does not check who is typing: anyone with the passcode can submit as any
  member. That is the trade-off for not making people create accounts. If
  that matters, give each member their own passcode by changing the check in
  `upload.js` to look the member up in a `PASSCODES` JSON secret.
- Files are capped at 25 MB each and 20 per submission. GitHub's own limit is
  100 MB per file, so raise `MAX_FILE_BYTES` in `upload.js` if you need to.
- Reviews still go through GitHub's editor from the submission page; only the
  two admins write those, and they have GitHub accounts.
