/* Shared runtime for the tracker pages: loads data/index.json, resolves who is
   viewing, filters what they may see, and renders the top bar. */
window.Tracker = (function () {
  const STATUS = {
    "submitted":         { label: "Awaiting review",   sym: "○", color: "var(--st-submitted)" },
    "in-review":         { label: "In review",         sym: "◐", color: "var(--st-in-review)" },
    "changes-requested": { label: "Changes requested", sym: "!",      color: "var(--st-changes-requested)" },
    "approved":          { label: "Approved",          sym: "✓", color: "var(--st-approved)" },
  };
  const ORDER = ["submitted", "in-review", "changes-requested", "approved"];
  // The known entry for a status, or a muted placeholder for anything else
  // (a hand-edited index.json, say), so bad data renders instead of crashing.
  const statusOf = (status) => STATUS[status] || { label: status, sym: "?", color: "var(--muted)" };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const today = () => new Date().toISOString().slice(0, 10);
  const parseDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); };
  const fmtDate = (iso, opts) => iso ? parseDate(iso).toLocaleDateString("en-US", Object.assign({ month: "short", day: "numeric", timeZone: "UTC" }, opts || {})) : "";
  const fmtDateLong = (iso) => fmtDate(iso, { year: "numeric" });
  const daysBetween = (a, b) => Math.round((parseDate(b) - parseDate(a)) / 86400000);
  const fmtSize = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "submission";
  const initials = (name) => name.replace(/^Prof\.\s*/, "").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  async function load() {
    const params = new URLSearchParams(location.search);
    const res = await fetch("data/index.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`Could not load data/index.json (${res.status}). Run scripts/build.py first.`);
    const data = await res.json();

    data.memberById = Object.fromEntries(data.members.map((m) => [m.id, m]));
    // Assignments are whatever people typed; the distinct names drive the
    // coverage grid, the filters, and the submit page's suggestions.
    data.assignmentNames = [...new Set(data.submissions.map((s) => s.assignment).filter(Boolean))].sort((a, b) => a.localeCompare(b));

    let viewerId = params.get("as");
    if (!viewerId) { try { viewerId = localStorage.getItem("viewer"); } catch (e) { viewerId = null; } }
    if (!data.memberById[viewerId]) viewerId = (data.members.find((m) => m.role === "admin") || data.members[0]).id;
    try { localStorage.setItem("viewer", viewerId); } catch (e) { /* private mode */ }

    data.viewer = data.memberById[viewerId];
    data.isAdmin = data.viewer.role === "admin";
    // The visibility rule: admins see everyone, members see only their own work.
    data.visible = data.isAdmin ? data.submissions : data.submissions.filter((s) => s.member === viewerId);
    data.today = today();
    data.github = data.repo ? `https://github.com/${data.repo}` : "";
    data.blobUrl = (path) => data.github ? `${data.github}/blob/${data.branch}/${path}` : "#";
    data.treeUrl = (path) => data.github ? `${data.github}/tree/${data.branch}/${path}` : "#";

    renderTopbar(data);
    document.title = `${document.title.split(" | ")[0]} | ${data.group}`;
    return data;
  }

  function withViewer(href, data) {
    const url = new URL(href, location.href);
    url.searchParams.set("as", data.viewer.id);
    return url.pathname.split("/").pop() + url.search;
  }

  function renderTopbar(data) {
    const el = document.querySelector(".topbar .inner");
    if (!el) return;
    const here = location.pathname.split("/").pop() || "index.html";
    const link = (href, label) => `<a href="${withViewer(href, data)}" class="${here === href ? "active" : ""}">${label}</a>`;
    el.innerHTML = `
      <div class="brand"><span class="name">${esc(data.group)}</span><span class="sub">Submission tracker</span></div>
      <nav class="nav">${link("index.html", "Dashboard")}${link("timeline.html", "Timeline")}${link("submit.html", "Submit")}</nav>
      <div class="viewer">
        <label for="viewer-select">Viewing as</label>
        <select id="viewer-select">${data.members.map((m) => `<option value="${m.id}" ${m.id === data.viewer.id ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select>
        <span class="role ${data.isAdmin ? "admin" : ""}">${data.isAdmin ? "Admin" : "Member"}</span>
      </div>`;
    el.querySelector("#viewer-select").addEventListener("change", (e) => {
      const url = new URL(location.href);
      url.searchParams.set("as", e.target.value);
      if (url.searchParams.has("id")) {
        // A member switching away from their own submission lands on the dashboard.
        const sub = data.submissions.find((s) => s.id === url.searchParams.get("id"));
        const m = data.memberById[e.target.value];
        if (sub && m.role !== "admin" && sub.member !== m.id) { url.pathname = url.pathname.replace(/[^/]*$/, "index.html"); url.searchParams.delete("id"); }
      }
      location.href = url.toString();
    });
  }

  function chip(status) {
    const s = statusOf(status);
    return `<span class="chip" style="--c:${s.color}"><span class="sym">${s.sym}</span>${esc(s.label)}</span>`;
  }
  function personChip(data, id) { return `<span class="chip person">${esc(data.memberById[id]?.name || id)}</span>`; }
  function assignmentChip(data, name) { return `<span class="chip assignment">${esc(name || "no assignment")}</span>`; }
  function detailHref(data, sub) { return withViewer(`submission.html?id=${encodeURIComponent(sub.id)}`, data); }

  // Submitted files. They are served next to the site (build.py --sync-files
  // mirrors submissions/ into site/), so a file's repo path is also its URL.
  const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
  function fileKind(name) {
    const ext = (name.split(".").pop() || "").toLowerCase();
    return ext === "pdf" ? "pdf" : IMAGE_EXT.has(ext) ? "image" : "other";
  }
  function fileUrl(f) { return f.path.split("/").map(encodeURIComponent).join("/"); }
  function fileLinks(files) {
    return (files || []).map((f) => fileKind(f.name) === "other"
      ? `<a class="filebtn" href="${fileUrl(f)}" target="_blank" rel="noopener" title="${esc(f.name)}, opens in a new tab">${esc(f.name)}</a>`
      : `<button type="button" class="filebtn ${fileKind(f.name)}" data-path="${esc(f.path)}" data-name="${esc(f.name)}" title="Open ${esc(f.name)}">${esc(f.name)}</button>`).join(" ");
  }
  function fileViewer() {
    let v = document.getElementById("file-viewer");
    if (v) return v;
    v = document.createElement("div");
    v.id = "file-viewer"; v.className = "file-viewer"; v.hidden = true;
    v.innerHTML = `
      <div class="file-viewer-box" role="dialog" aria-modal="true" aria-label="File viewer">
        <div class="file-viewer-head">
          <span class="viewer-name mono"></span>
          <a class="btn small viewer-open" target="_blank" rel="noopener">Open in new tab</a>
          <a class="btn small viewer-dl">Download</a>
          <button type="button" class="btn small viewer-close" aria-label="Close">Close</button>
        </div>
        <div class="file-viewer-body"></div>
      </div>`;
    document.body.appendChild(v);
    v.addEventListener("click", (e) => { if (e.target === v) closeViewer(); });
    v.querySelector(".viewer-close").addEventListener("click", closeViewer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !v.hidden) closeViewer(); });
    return v;
  }
  function openFile(f) {
    const v = fileViewer(), url = fileUrl(f), kind = fileKind(f.name);
    v.querySelector(".viewer-name").textContent = f.name;
    v.querySelector(".viewer-open").href = url;
    const dl = v.querySelector(".viewer-dl"); dl.href = url; dl.download = f.name;
    v.querySelector(".file-viewer-body").innerHTML = kind === "image"
      ? `<img src="${url}" alt="${esc(f.name)}">`
      : `<iframe src="${url}" title="${esc(f.name)}"></iframe>`;
    v.hidden = false;
    document.body.classList.add("file-viewer-open");
  }
  function closeViewer() {
    const v = document.getElementById("file-viewer");
    if (!v) return;
    v.hidden = true;
    v.querySelector(".file-viewer-body").innerHTML = "";
    document.body.classList.remove("file-viewer-open");
  }
  function wireFileButtons(root) {
    root.querySelectorAll("button.filebtn").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      openFile({ path: b.dataset.path, name: b.dataset.name });
    }));
  }

  function submissionTable(data, subs, opts) {
    opts = opts || {};
    const rows = subs.map((s) => `
      <tr data-href="${detailHref(data, s)}">
        ${opts.showPerson ? `<td>${esc(data.memberById[s.member]?.name || s.member)}</td>` : ""}
        <td class="title"><a href="${detailHref(data, s)}">${esc(s.title)}</a><div class="small muted">${esc(s.notes || "")}</div></td>
        <td>${assignmentChip(data, s.assignment)}</td>
        <td class="files-cell">${fileLinks(s.files) || '<span class="muted">none</span>'}</td>
        <td class="date">${fmtDate(s.submitted)}</td>
        <td class="date">${s.updated !== s.submitted ? fmtDate(s.updated) : '<span class="muted">same</span>'}</td>
        <td>${chip(s.status)}</td>
        <td class="ink2">${esc(s.review?.reviewer || "")}</td>
      </tr>`);
    const empty = `<tr class="empty"><td colspan="${opts.showPerson ? 8 : 7}">${esc(opts.emptyText || "No submissions yet.")}</td></tr>`;
    return `<table class="list">
      <thead><tr>${opts.showPerson ? "<th>Person</th>" : ""}<th>Submission</th><th>Assignment</th><th>Files</th><th>Submitted</th><th>Updated</th><th>Status</th><th>Reviewer</th></tr></thead>
      <tbody>${rows.length ? rows.join("") : empty}</tbody></table>`;
  }

  function wireRowLinks(root) {
    root.querySelectorAll("tr[data-href]").forEach((tr) => tr.addEventListener("click", (e) => {
      if (e.target.closest("a, button")) return;
      location.href = tr.dataset.href;
    }));
    wireFileButtons(root);
  }

  function copyText(text, btn) {
    const done = () => { if (btn) { const old = btn.textContent; btn.textContent = "Copied"; setTimeout(() => (btn.textContent = old), 1400); } };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, done);
    else done();
  }

  function fail(err) {
    const page = document.querySelector(".page");
    if (page) page.innerHTML = `<div class="card"><h2>Could not load the tracker</h2><p class="ink2">${esc(err.message)}</p><p class="small muted">Serve the site folder over HTTP (for example <code>python3 -m http.server 8000 -d site</code>) after running <code>python3 scripts/build.py</code>.</p></div>`;
    console.error(err);
  }

  return { STATUS, ORDER, statusOf, esc, today, parseDate, fmtDate, fmtDateLong, daysBetween, fmtSize, slug, initials,
           load, withViewer, chip, personChip, assignmentChip, detailHref, submissionTable, wireRowLinks, copyText, fail,
           fileKind, fileUrl, fileLinks, openFile, closeViewer, wireFileButtons };
})();
