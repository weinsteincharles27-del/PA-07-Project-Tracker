/* Upload endpoint for the PA-07 tracker.
 *
 * Runs as a Cloudflare Worker. The site's Submit page posts a multipart form
 * here (member, passcode, assignment, title, notes, body, files). The worker
 * checks the passcode, then writes the submission straight into the GitHub
 * repo through the Git Data API: one blob per file, a new tree, a commit, and
 * a ref update. The publish workflow then rebuilds the site.
 *
 * Environment (Settings > Variables and Secrets on the worker):
 *   GITHUB_TOKEN     fine-grained token with Contents: read and write (secret)
 *   GITHUB_REPO      owner/name, e.g. weinsteincharles27-del/PA-07-Project-Tracker
 *   GITHUB_BRANCH    optional, default main
 *   GROUP_PASSCODE   the passcode members type on the Submit page (secret)
 *   ALLOWED_ORIGIN   the site's origin, e.g. https://weinsteincharles27-del.github.io
 *
 * See worker/README.md for the setup steps. No build step, no dependencies.
 */

const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_FILES = 20;
const API = "https://api.github.com";

export default {
  async fetch(request, env) {
    return handle(request, env, fetch);
  },
};

export async function handle(request, env, fetchImpl) {
  const cors = corsHeaders(env, request);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (request.method !== "POST") return json({ error: "POST a multipart form here" }, 405, cors);
  for (const key of ["GITHUB_TOKEN", "GITHUB_REPO", "GROUP_PASSCODE"]) {
    if (!env[key]) return json({ error: `The worker is missing its ${key} setting` }, 500, cors);
  }

  let form;
  try {
    form = await request.formData();
  } catch (e) {
    return json({ error: "Expected multipart form data" }, 400, cors);
  }
  const field = (k) => String(form.get(k) ?? "").replace(/[\r\n]+/g, " ").trim();

  if (field("passcode") !== env.GROUP_PASSCODE) return json({ error: "That passcode is not right" }, 403, cors);
  const memberId = field("member");
  if (!/^[a-z0-9][a-z0-9-]{0,39}$/.test(memberId)) return json({ error: "Pick who you are" }, 400, cors);
  const title = field("title"), assignment = field("assignment"), notes = field("notes");
  const body = String(form.get("body") ?? "").trim();
  if (!assignment) return json({ error: "Which assignment is this for?" }, 400, cors);
  if (!title) return json({ error: "Give it a title" }, 400, cors);

  const files = form.getAll("files").filter((f) => typeof f !== "string" && f.size > 0);
  if (!files.length) return json({ error: "Attach at least one file" }, 400, cors);
  if (files.length > MAX_FILES) return json({ error: `At most ${MAX_FILES} files per submission` }, 400, cors);
  for (const f of files) {
    if (f.size > MAX_FILE_BYTES) return json({ error: `${f.name} is over 25 MB` }, 413, cors);
  }

  const gh = github(env, fetchImpl);
  const branch = env.GITHUB_BRANCH || "main";

  // The roster is the source of truth for who can submit and what to call them.
  let members;
  try {
    const roster = await gh(`contents/members.json?ref=${encodeURIComponent(branch)}`);
    members = JSON.parse(fromBase64(roster.content)).members;
  } catch (e) {
    return json({ error: `Could not read members.json from the repo: ${e.message}` }, 502, cors);
  }
  const member = members.find((m) => m.id === memberId);
  if (!member) return json({ error: `${memberId} is not in members.json` }, 400, cors);

  const today = new Date().toISOString().slice(0, 10);
  const folder = await freeFolder(gh, branch, memberId, `${today}-${slug(title)}`);
  const dir = `submissions/${memberId}/${folder}`;
  const md = `---\ntitle: ${title}\nassignment: ${assignment}\n${notes ? `notes: ${notes}\n` : ""}---\n${body ? body + "\n" : ""}`;

  // Blobs first (they are branch-independent), then tree, commit, ref.
  const entries = [{ path: `${dir}/submission.md`, sha: (await gh("git/blobs", { content: md, encoding: "utf-8" })).sha }];
  const used = new Set(["submission.md"]);
  for (const f of files) {
    const name = uniqueName(safeName(f.name), used);
    const blob = await gh("git/blobs", { content: toBase64(await f.arrayBuffer()), encoding: "base64" });
    entries.push({ path: `${dir}/${name}`, sha: blob.sha });
  }
  const message = `${member.name}: ${title} (${assignment})`;
  const author = { name: member.name, email: `${memberId}@tracker.invalid`, date: new Date().toISOString() };

  let commit;
  for (let attempt = 0; attempt < 3; attempt++) {
    const head = (await gh(`git/ref/heads/${branch}`)).object.sha;
    const base = await gh(`git/commits/${head}`);
    const tree = await gh("git/trees", {
      base_tree: base.tree.sha,
      tree: entries.map((e) => ({ path: e.path, mode: "100644", type: "blob", sha: e.sha })),
    });
    commit = await gh("git/commits", { message, tree: tree.sha, parents: [head], author });
    try {
      await gh(`git/refs/heads/${branch}`, { sha: commit.sha }, "PATCH");
      break;
    } catch (e) {
      // Someone else pushed in between; rebuild on the new head.
      if (attempt === 2 || !/not a fast forward|422/.test(e.message)) throw e;
      commit = null;
    }
  }
  if (!commit) return json({ error: "The repo moved while uploading; please try again" }, 409, cors);

  return json({
    ok: true,
    folder: dir,
    files: entries.slice(1).map((e) => e.path.slice(dir.length + 1)),
    commit: commit.sha,
    commit_url: `https://github.com/${env.GITHUB_REPO}/commit/${commit.sha}`,
    message,
  }, 200, cors);
}

// A GitHub API caller bound to the repo. Throws with the API's message on failure.
function github(env, fetchImpl) {
  return async (path, payload, method) => {
    const res = await fetchImpl(`${API}/repos/${env.GITHUB_REPO}/${path}`, {
      method: method || (payload ? "POST" : "GET"),
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "User-Agent": "pa07-tracker-upload",
        ...(payload ? { "Content-Type": "application/json" } : {}),
      },
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const text = await res.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (e) { data = { message: text }; }
    if (!res.ok) throw new Error(`GitHub ${res.status} on ${path}: ${data.message || text}`);
    return data;
  };
}

// The folder the site would create, with -2, -3 appended if it already exists.
async function freeFolder(gh, branch, memberId, base) {
  for (let n = 1; n < 50; n++) {
    const name = n === 1 ? base : `${base}-${n}`;
    try {
      await gh(`contents/submissions/${memberId}/${encodeURIComponent(name)}?ref=${encodeURIComponent(branch)}`);
    } catch (e) {
      if (/GitHub 404/.test(e.message)) return name;
      throw e;
    }
  }
  throw new Error("Too many submissions with this title today");
}

export function slug(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "submission";
}
export function safeName(name) {
  const base = String(name).split(/[\\/]/).pop().replace(/[\x00-\x1f]/g, "").trim();
  const cleaned = base.replace(/^\.+/, "").replace(/\s+/g, " ");
  return cleaned || "file";
}
function uniqueName(name, used) {
  let candidate = name, n = 2;
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name, ext = dot > 0 ? name.slice(dot) : "";
  while (used.has(candidate)) candidate = `${stem}-${n++}${ext}`;
  used.add(candidate);
  return candidate;
}
function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
function fromBase64(b64) {
  const binary = atob(String(b64).replace(/\s/g, ""));
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}
function corsHeaders(env, request) {
  const origin = request.headers.get("Origin") || "";
  const allowed = env.ALLOWED_ORIGIN || "*";
  const ok = allowed === "*" || origin === allowed || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  return {
    "Access-Control-Allow-Origin": ok ? (origin || allowed) : allowed,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}
function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...headers } });
}
