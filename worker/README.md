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

1. Sign up or log in at <https://dash.cloudflare.com> (free plan).
2. **Workers & Pages**, **Create**, **Create Worker**. Give it a name such as
   `pa07-upload` and press **Deploy** (it deploys a hello-world first).
3. **Edit code**. Replace everything in the editor with the contents of
   [`upload.js`](upload.js), then **Deploy**.
4. Back on the worker's page, **Settings**, **Variables and Secrets**. Add:

   | name | type | value |
   |---|---|---|
   | `GITHUB_TOKEN` | Secret | the token from step 1 |
   | `GITHUB_REPO` | Text | `weinsteincharles27-del/PA-07-Project-Tracker` |
   | `GROUP_PASSCODE` | Secret | a passcode you will give the group |
   | `ALLOWED_ORIGIN` | Text | `https://weinsteincharles27-del.github.io` |

   Save after each one (the worker redeploys itself).
5. Copy the worker's URL from its overview page. It looks like
   `https://pa07-upload.<your-account>.workers.dev`.

## 3. Point the site at it

Put that URL into `members.json`:

```json
"upload_url": "https://pa07-upload.<your-account>.workers.dev",
```

Commit and push. Once the site rebuilds, the Submit page shows a passcode
field and an **Upload** button, and members never see GitHub.

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
