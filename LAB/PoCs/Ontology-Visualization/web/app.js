/* SIP ontology viewer (PoC). Vanilla JS over SIP's generic operation route. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { project: null, principal: null, view: null, selected: null, seed: null,
                expanded: new Set() };
const HIER = new Set(["subClassOf", "broader"]);
const SEV = { blocker: "B", major: "M", minor: "m", info: "i" };

cytoscape.use(cytoscapeDagre);

// ------------------------------------------------------------------ API
async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { "Content-Type": "application/json",
    "X-SIP-Principal": state.principal || "val", ...(opts.headers || {}) } });
  const text = await r.text();
  const body = text ? JSON.parse(text) : null;
  if (!r.ok) throw new Error((body && body.detail) || r.statusText);
  return body;
}
const op = (name, body = {}) =>
  api(`/projects/${encodeURIComponent(state.project)}/ops/${name}`,
      { method: "POST", body: JSON.stringify(body) });

function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), err ? 6000 : 2500);
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const local = (iri) => iri.split(/[#/]/).pop();
const checked = (name) => [...document.querySelectorAll(`input[name=${name}]:checked`)]
  .map((i) => i.value);

// ------------------------------------------------------------------ graph
const cy = cytoscape({
  container: $("cy"), wheelSensitivity: 0.25, minZoom: 0.05, maxZoom: 3,
  style: [
    { selector: "node", style: {
        shape: "round-rectangle", "background-color": "data(color)", label: "data(text)",
        "text-wrap": "wrap", "text-valign": "center", "font-size": 11, color: "#1d2430",
        width: "data(w)", height: "data(h)", "border-width": 1, "border-color": "#8a94a6",
        "min-zoomed-font-size": 6 } },
    { selector: "node[kind = 'concept']", style: { shape: "ellipse" } },
    { selector: "node[?seed]", style: { "border-width": 4, "font-weight": "bold" } },
    { selector: "node[state = 'staged_add']", style: { "border-color": "#2e7d32", "border-width": 3 } },
    { selector: "node[state = 'staged_del']", style: { "border-color": "#c62828", "border-width": 3,
        "border-style": "dashed", opacity: 0.8 } },
    { selector: "node[state = 'modified']", style: { "border-color": "#b26a00", "border-width": 3 } },
    { selector: "node[?unsat]", style: { "background-color": "#ffebee" } },
    { selector: "node[?deprecated]", style: { "font-style": "italic", opacity: 0.7 } },
    { selector: "node:selected", style: { "overlay-color": "#3949ab", "overlay-opacity": 0.15,
        "overlay-padding": 6 } },
    { selector: "edge", style: {
        width: 1.4, "line-color": "#5c6b80", "target-arrow-color": "#5c6b80",
        "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": 0.9,
        label: "data(text)", "font-size": 9, color: "#5c6b80", "text-rotation": "autorotate",
        "text-background-color": "#fff", "text-background-opacity": 0.85,
        "text-background-padding": 1, "min-zoomed-font-size": 7 } },
    { selector: "edge[kind = 'subClassOf'], edge[kind = 'broader']",
      style: { "target-arrow-shape": "triangle-backcurve", "target-arrow-fill": "hollow" } },
    { selector: "edge[kind = 'equivalentClass']", style: { width: 3, "target-arrow-shape": "none" } },
    { selector: "edge[kind = 'restriction']", style: { "line-style": "dashed" } },
    { selector: "edge[kind = 'optional']", style: { "line-style": "dashed", "line-dash-pattern": [2, 4],
        "line-color": "#9aa5b5", "target-arrow-color": "#9aa5b5", color: "#7d8899" } },
    { selector: "edge[kind = 'objectProperty']", style: { "line-color": "#7b5ea7",
        "target-arrow-color": "#7b5ea7", color: "#7b5ea7", "target-arrow-shape": "vee" } },
    { selector: "edge[kind = 'disjointWith']", style: { "line-style": "dotted",
        "target-arrow-shape": "none" } },
    { selector: "edge[state = 'staged_add']", style: { "line-color": "#2e7d32",
        "target-arrow-color": "#2e7d32", color: "#2e7d32", width: 2.4 } },
    { selector: "edge[state = 'staged_del']", style: { "line-color": "#c62828",
        "target-arrow-color": "#c62828", color: "#c62828", "line-style": "dashed", width: 2.4 } },
    { selector: "edge[?inferred]", style: { "line-color": "#1565c0", "target-arrow-color": "#1565c0",
        color: "#1565c0", "line-style": "dotted", width: 2 } },
    { selector: ".faded", style: { opacity: 0.18 } },
  ],
});

function nodeText(e) {
  const s = e.sip, pre = { staged_add: "+ ", staged_del: "− ", modified: "~ " }[s.state] || "";
  const lines = [pre + e.name + (s.unsatisfiable ? " ⊥" : "")];
  const meta = [];
  if (s.worstSeverity) meta.push(`⚠${SEV[s.worstSeverity] || "?"}${s.findingCount > 1 ? "×" + s.findingCount : ""}`);
  if (s.cq && (s.cq.pass.length || s.cq.fail.length))
    meta.push(`CQ ✓${s.cq.pass.length} ✗${s.cq.fail.length}`);
  if (s.complexCount) meta.push(`◆${s.complexCount}`);
  if (s.hidden) meta.push(`+${s.hidden}`);
  if (meta.length) lines.push(meta.join("  "));
  return lines.join("\n");
}

function toElements(view) {
  const els = [];
  for (const e of view.entityTypes) {
    const text = nodeText(e);
    const longest = Math.max(...text.split("\n").map((l) => l.length));
    els.push({ group: "nodes", data: {
      id: e.id, text, kind: e.kind, color: e.color, seed: e.sip.seed, state: e.sip.state,
      unsat: e.sip.unsatisfiable, deprecated: e.sip.deprecated,
      w: Math.max(70, Math.min(230, longest * 6.6 + 18)), h: text.includes("\n") ? 40 : 28 } });
  }
  for (const r of view.relationships) {
    const s = r.sip, pre = { staged_add: "+ ", staged_del: "− " }[s.state] || "";
    let text = HIER.has(r.kind) ? "" : r.kind === "equivalentClass" ? "≡" :
      r.kind === "disjointWith" ? "disjoint" : r.name;
    if (s.inferred) text = "inferred";
    els.push({ group: "edges", data: { id: r.id, source: r.from, target: r.to, kind: r.kind,
      text: (pre + text).trim(), state: s.state, inferred: s.inferred } });
  }
  return els;
}

// Layered layout: generalisation points up (subclass/broader edges rank parents above
// children); every other edge is fed to dagre *reversed* through temporary layout-only
// edges, so what a class refers to (restriction fillers, ranges) sits below it instead of
// crowding its superclasses. The temporary edges are removed right after the run.
function layout(opts = {}) {
  const tmp = cy.edges().filter((e) => !HIER.has(e.data("kind")) && !e.data("inferred"))
    .map((e) => ({ group: "edges", classes: "layout-only",
                   data: { id: "L|" + e.id(), source: e.target().id(), target: e.source().id() } }));
  const added = cy.add(tmp);
  const sub = cy.nodes().union(cy.edges().filter((e) =>
    HIER.has(e.data("kind")) || e.hasClass("layout-only")));
  sub.layout({ name: "dagre", rankDir: "BT", nodeSep: 14, rankSep: 60, edgeSep: 6,
               edgeWeight: (e) => (e.hasClass("layout-only") ? 1 : 4),
               animate: false, fit: true, padding: 30, ...opts }).run();
  cy.remove(added);
  // keep labels readable: never fit below MIN_READABLE zoom; centre on the seed instead
  if (cy.zoom() < MIN_READABLE && state.seed) {
    cy.zoom(MIN_READABLE);
    cy.center(cy.getElementById(state.seed));
  }
}
const MIN_READABLE = 0.85;

function render(view, { merge = false, around = null } = {}) {
  state.view = view;
  $("empty").hidden = true;
  const els = toElements(view);
  if (!merge) {
    cy.elements().remove();
    cy.add(els);
    layout();
  } else {
    const existing = new Set(cy.nodes().map((n) => n.id()));
    const fresh = els.filter((e) => e.group === "nodes" && !existing.has(e.data.id));
    for (const e of els) {
      const cur = cy.getElementById(e.data.id);
      if (cur.nonempty()) cur.data(e.data); else cy.add(e);
    }
    // keep the user's mental map: old nodes stay put, new ones ring the expanded node
    const added = cy.collection(fresh.map((e) => cy.getElementById(e.data.id)));
    if (added.nonempty() && around) {
      const c = cy.getElementById(around).position();
      const r = 110 + 12 * added.length;
      added.forEach((n, i) => {
        const a = (2 * Math.PI * i) / added.length;
        n.position({ x: c.x + r * Math.cos(a), y: c.y + r * Math.sin(a) });
      });
    }
  }
  summary(view);
  if (!$("table").hidden) table(view);
}

// ------------------------------------------------------------------ summary, table
function summary(view) {
  const st = view.sip.stats, sm = view.sip.summary || {};
  const parts = [`<b>${st.nodes}</b> nodes`, `<b>${st.edges}</b> edges`,
    `${st.truncated} held back by the cap`, `${st.guarded} guarded hubs`, `${st.ms} ms extraction`];
  if (sm.pendingCommits !== undefined && view.sip.overlays.includes("staged"))
    parts.push(`<b>${sm.pendingCommits}</b> pending commits (` +
      `+${sm.staged.staged_add}/−${sm.staged.staged_del}/~${sm.staged.modified} nodes, ` +
      `+${sm.stagedEdges.staged_add}/−${sm.stagedEdges.staged_del} edges)`);
  if (sm.inferredSource) parts.push(`${sm.inferredEdges} inferred edges (${sm.inferredSource})`);
  if (sm.unsatisfiable && sm.unsatisfiable.length)
    parts.push(`<span class="warn">${sm.unsatisfiable.length} unsatisfiable</span>`);
  if (sm.findings !== undefined) parts.push(`${sm.findings} findings`);
  if (sm.cq) parts.push(`CQs ✓${sm.cq.pass} ✗${sm.cq.fail}` +
    (sm.cq.fixedByStaged ? ` (${sm.cq.fixedByStaged} fixed by staged)` : ""));
  $("summary").innerHTML = parts.join(" &middot; ");
}

function table(view) {
  const lab = Object.fromEntries(view.entityTypes.map((e) => [e.id, e.name]));
  $("table").innerHTML =
    `<table><caption>Nodes</caption><tr><th>Name</th><th>State</th><th>Hops</th><th>Module</th>
     <th>Findings</th><th>CQ pass</th><th>CQ fail</th><th>Badges</th><th>Hidden</th></tr>` +
    view.entityTypes.map((e) => `<tr><td>${esc(e.name)}</td><td>${e.sip.state}${e.sip.unsatisfiable ? ", unsatisfiable" : ""}</td>
      <td>${e.sip.dist}</td><td>${esc(e.sip.moduleLabel)}</td><td>${e.sip.findingCount || ""}</td>
      <td>${e.sip.cq ? e.sip.cq.pass.join(", ") : ""}</td><td>${e.sip.cq ? e.sip.cq.fail.join(", ") : ""}</td>
      <td>${e.sip.complexCount || ""}</td><td>${e.sip.hidden || ""}</td></tr>`).join("") +
    `</table><table><caption>Edges</caption><tr><th>From</th><th>Kind</th><th>Label</th><th>To</th>
     <th>State</th></tr>` +
    view.relationships.map((r) => `<tr><td>${esc(lab[r.from])}</td><td>${r.kind}</td>
      <td>${esc(r.name)}</td><td>${esc(lab[r.to])}</td>
      <td>${r.sip.inferred ? "inferred" : r.sip.state}</td></tr>`).join("") + "</table>";
}

// ------------------------------------------------------------------ loading views
function params(seed, extra = {}) {
  return { seed, hops: +$("hops").value, cap: +$("cap").value, hub_limit: +$("hub").value,
           kinds: checked("kind"), overlays: checked("overlay"),
           expand: [...state.expanded], ...extra };
}

async function load(seed) {
  state.seed = seed;
  state.expanded = new Set();
  try {
    render(await op("viz.neighbourhood", params(seed)));
    select(seed);
  } catch (e) { toast(e.message, true); }
}

async function expand(iri) {
  const ent = state.view && state.view.entityTypes.find((e) => e.id === iri);
  const hidden = ent ? ent.sip.hidden : 0;
  if (ent && ent.sip.guarded !== null && ent.sip.guarded !== undefined &&
      !confirm(`${ent.name} is a hub with ${hidden} more neighbours. Expand anyway?`)) return;
  state.expanded.add(iri);
  try {
    const v = await op("viz.neighbourhood", params(iri, { hops: 1,
      cap: Math.max(+$("cap").value, hidden + 1), expand: [iri] }));
    // merge into the current view, then refresh overlays for the union
    const cur = state.view;
    const ids = new Set(cur.entityTypes.map((e) => e.id));
    const rids = new Set(cur.relationships.map((r) => r.id));
    const merged = { ...cur, entityTypes: cur.entityTypes.concat(v.entityTypes.filter((e) => !ids.has(e.id))),
      relationships: cur.relationships.concat(v.relationships.filter((r) => !rids.has(r.id))) };
    merged.entityTypes.forEach((e) => { if (e.id === iri) e.sip.hidden = 0; });
    merged.sip = { ...cur.sip, stats: { ...cur.sip.stats, nodes: merged.entityTypes.length,
      edges: merged.relationships.length } };
    render(merged, { merge: true, around: iri });
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------ panel
async function select(iri) {
  state.selected = iri;
  cy.nodes().unselect();
  cy.getElementById(iri).select();
  const e = state.view.entityTypes.find((x) => x.id === iri);
  if (!e) return;
  const s = e.sip;
  const cqs = (state.view.sip.cqs || []);
  const cqLine = (id) => {
    const q = cqs.find((c) => c.id === id) || { question: "" };
    return `<li><b>${esc(id)}</b> ${esc(q.question)} <span class="muted">${esc(q.priority || "")}</span></li>`;
  };
  let html = `<h2>${esc(e.name)}</h2><div class="iri">${esc(iri)}</div>
    <p><span class="pill ${s.state}">${s.state.replace("_", " ")}</span>
      ${s.defined ? '<span class="pill asserted">defined</span>' : ""}
      ${s.unsatisfiable ? '<span class="pill staged_del">unsatisfiable</span>' : ""}
      <span class="muted">${esc(s.moduleLabel)} &middot; ${s.instances} instances &middot; ${s.dist} hops</span></p>
    ${e.description ? `<p>${esc(e.description)}</p>` : ""}
    <p><button id="mkSeed" type="button">Centre here</button>
       <button id="expandBtn" type="button" ${s.hidden ? "" : "disabled"}>Expand (+${s.hidden})</button></p>`;
  if (s.commits && s.commits.length) {
    html += `<h3>Pending commits</h3>` + s.commits.map((c) => `<div class="commit">
      <b>${esc(c.operation)}</b> by ${esc(c.principal)}${c.machine ? " (agent)" : ""}
      <div class="iri">${esc(c.id)}</div><div class="btns">
      <button class="primary" data-accept="${esc(c.id)}">Accept</button>
      <button class="danger" data-reject="${esc(c.id)}">Reject</button></div></div>`).join("");
  }
  if (s.findings && s.findings.length) {
    html += `<h3>Findings (${s.findingCount})</h3><ul>` + s.findings.map((f) =>
      `<li class="sev-${f.severity}">⚠ ${esc(f.severity)}: ${esc(f.message)} <span class="muted">${esc(f.check)}</span></li>`).join("") + "</ul>";
  }
  if (s.cq && (s.cq.pass.length || s.cq.fail.length)) {
    html += `<h3>Competency questions</h3>`;
    if (s.cq.pass.length) html += `<div class="ok">✓ passing</div><ul>${s.cq.pass.map(cqLine).join("")}</ul>`;
    if (s.cq.fail.length) html += `<div class="bad">✗ failing</div><ul>${s.cq.fail.map(cqLine).join("")}</ul>`;
    if (s.cq.fixedByStaged.length) html += `<p class="ok">Accepting the staged commits makes ${s.cq.fixedByStaged.map(esc).join(", ")} pass.</p>`;
    if (s.cq.brokenByStaged.length) html += `<p class="bad">Accepting the staged commits breaks ${s.cq.brokenByStaged.map(esc).join(", ")}.</p>`;
  }
  if (s.attributes && s.attributes.length)
    html += `<h3>Attributes</h3><ul>${s.attributes.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`;
  if (s.complex && s.complex.length)
    html += `<h3>Axioms not drawn (${s.complexCount})</h3><ul>${s.complex.map((a) => `<li><code>${esc(a)}</code></li>`).join("")}</ul>`;
  html += `<h3>Class description</h3><div id="frame" class="muted">loading…</div>
           <h3>Individuals</h3><div id="inds" class="muted">loading…</div>`;
  $("panel").innerHTML = html;
  $("mkSeed").onclick = () => load(iri);
  $("expandBtn").onclick = () => expand(iri);
  $("panel").querySelectorAll("[data-accept]").forEach((b) => b.onclick = () => decide("accept", b.dataset.accept));
  $("panel").querySelectorAll("[data-reject]").forEach((b) => b.onclick = () => decide("reject", b.dataset.reject));
  op("browse.classFrame", { cls: iri }).then((f) => {
    const rows = Object.entries(f).filter(([, v]) => Array.isArray(v) && v.length);
    $("frame").innerHTML = rows.length ? rows.map(([k, v]) => `<div><b>${esc(k)}</b><ul>${v.map((x) =>
      `<li>${esc(x.text ?? x)}${x.inferred ? ' <span class="muted">(inferred)</span>' : ""}</li>`).join("")}</ul></div>`).join("")
      : "nothing asserted";
  }).catch((err) => { $("frame").textContent = err.message; });
  op("viz.individuals", { cls: iri, limit: 10 }).then((r) => {
    $("inds").innerHTML = r.total ? `<ul>${r.items.map((i) => `<li>${esc(i.label)}</li>`).join("")}</ul>` +
      (r.total > r.items.length ? `<span class="muted">${r.total - r.items.length} more</span>` : "")
      : "none";
  }).catch((err) => { $("inds").textContent = err.message; });
}

async function decide(kind, commit) {
  try {
    await op(`validation.${kind}`, { commit });
    toast(`commit ${kind}ed`);
    if (state.seed) { const sel = state.selected; await load(state.seed); if (sel) select(sel); }
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------ search
let hitsTimer = null, activeHit = -1;
async function search() {
  const text = $("q").value.trim();
  const ul = $("hits");
  if (text.length < 2) { ul.hidden = true; return; }
  try {
    const hits = await op("viz.search", { text, limit: 25 });
    activeHit = hits.length ? 0 : -1;
    ul.innerHTML = hits.map((h, i) => `<li role="option" data-iri="${esc(h.iri)}" class="${i === 0 ? "active" : ""}">
      <span>${esc(h.label)}</span><small>${esc(local(h.module.replace(/[#/]$/, "")))} &middot; ${h.degree} links</small></li>`).join("")
      || '<li class="muted">no match</li>';
    ul.hidden = false;
    ul.querySelectorAll("li[data-iri]").forEach((li) => li.onclick = () => pick(li.dataset.iri));
  } catch (e) { toast(e.message, true); }
}
function pick(iri) { $("hits").hidden = true; $("q").value = ""; load(iri); }

$("q").addEventListener("input", () => { clearTimeout(hitsTimer); hitsTimer = setTimeout(search, 180); });
$("q").addEventListener("keydown", (ev) => {
  const items = [...$("hits").querySelectorAll("li[data-iri]")];
  if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
    activeHit = Math.max(0, Math.min(items.length - 1, activeHit + (ev.key === "ArrowDown" ? 1 : -1)));
    items.forEach((li, i) => li.classList.toggle("active", i === activeHit));
    ev.preventDefault();
  } else if (ev.key === "Enter" && items[activeHit]) pick(items[activeHit].dataset.iri);
  else if (ev.key === "Escape") $("hits").hidden = true;
});

// ------------------------------------------------------------------ interactions
cy.on("tap", "node", (ev) => select(ev.target.id()));
cy.on("dbltap", "node", (ev) => expand(ev.target.id()));
cy.on("mouseover", "node", (ev) => {
  const e = state.view.entityTypes.find((x) => x.id === ev.target.id());
  if (!e) return;
  const nb = ev.target.closedNeighborhood();
  cy.elements().not(nb).addClass("faded");
  const t = $("tip");
  t.innerHTML = `<b>${esc(e.name)}</b> &middot; ${esc(e.sip.moduleLabel)}<br>${e.sip.state.replace("_", " ")}` +
    (e.sip.findingCount ? ` &middot; ${e.sip.findingCount} findings` : "") +
    (e.sip.hidden ? ` &middot; ${e.sip.hidden} more neighbours` : "");
  const p = ev.renderedPosition;
  t.style.left = p.x + 14 + "px"; t.style.top = p.y + 14 + "px"; t.hidden = false;
});
cy.on("mouseout", "node", () => { cy.elements().removeClass("faded"); $("tip").hidden = true; });
cy.on("mouseover", "edge", (ev) => {
  const d = ev.target.data(), t = $("tip");
  const r = state.view.relationships.find((x) => x.id === d.id);
  if (!r) return;
  t.innerHTML = `${esc(r.kind)}: <b>${esc(r.name)}</b>` + (r.sip.via ? ` (via ${esc(r.sip.via)})` : "") +
    (r.sip.inferred ? " &middot; inferred" : r.sip.state !== "asserted" ? ` &middot; ${r.sip.state}` : "");
  const p = ev.renderedPosition;
  t.style.left = p.x + 14 + "px"; t.style.top = p.y + 14 + "px"; t.hidden = false;
});
cy.on("mouseout", "edge", () => { $("tip").hidden = true; });

$("fit").onclick = () => cy.fit(undefined, 30);
$("relayout").onclick = () => layout();
$("tableBtn").onclick = () => {
  const show = $("table").hidden;
  $("table").hidden = !show;
  $("tableBtn").setAttribute("aria-pressed", String(show));
  if (show && state.view) table(state.view);
};
$("svg").onclick = async () => {
  if (!state.seed) return toast("load a view first", true);
  try {
    const svg = await op("viz.exportSVG", params(state.seed, { cap: Math.min(+$("cap").value, 80) }));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    a.download = `${local(state.seed)}.svg`;
    a.click();
  } catch (e) { toast(e.message, true); }
};
document.querySelectorAll("input[name=kind], input[name=overlay], #hops, #cap, #hub")
  .forEach((i) => i.addEventListener("change", () => state.seed && load(state.seed)));
$("project").onchange = () => { state.project = $("project").value; cy.elements().remove();
  $("empty").hidden = false; $("panel").innerHTML = '<p class="muted">Select a node.</p>'; summary0(); };
$("principal").onchange = () => { state.principal = $("principal").value; };

async function summary0() {
  try {
    const s = await op("viz.stats");
    $("summary").innerHTML = `Project <b>${esc(state.project)}</b>: ${s.nodes} classes/concepts, ` +
      `${s.edges} typed edges, ${s.badged_nodes} with undrawn axioms, max degree ${s.max_degree}` +
      (s.stagedDifferences ? " &middot; staged changes present" : "");
  } catch (e) { $("summary").textContent = e.message; }
}

// ------------------------------------------------------------------ boot
(async function boot() {
  state.principal = new URLSearchParams(location.search).get("as") || "val";
  const h = await api("/health");
  $("project").innerHTML = h.projects.map((p) => `<option>${esc(p)}</option>`).join("");
  const want = new URLSearchParams(location.search).get("project");
  state.project = want && h.projects.includes(want) ? want : h.projects[0];
  $("project").value = state.project;
  try {
    const ps = await api("/principals");
    $("principal").innerHTML = ps.filter((p) => !p.is_machine)
      .map((p) => `<option ${p.id === state.principal ? "selected" : ""}>${esc(p.id)}</option>`).join("");
  } catch { $("principal").innerHTML = `<option>${esc(state.principal)}</option>`; }
  await summary0();
  const seed = new URLSearchParams(location.search).get("seed");
  if (seed) load(seed);
})();
