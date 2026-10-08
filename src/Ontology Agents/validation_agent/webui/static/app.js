// Ontology Review web UI: a thin client over the OVA review API.
// It renders what the engine and policy decided; it never computes findings or verdicts.
"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { meta: null, session: null, step: "intake", assessment: null, focusFinding: null, busy: false };

// ------------------------------------------------------------------ helpers
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function localName(iri) {
  const s = String(iri || "");
  const m = s.replace(/[#/:]+$/, "").match(/[^#/:]+$/);
  return m ? m[0] : s;
}
function isIri(s) { return /^(https?:|urn:|file:)/.test(String(s || "")); }
function iriBtn(iri, label) {
  if (!isIri(iri)) return `<code>${esc(iri)}</code>`;
  return `<button class="iri" data-iri="${esc(iri)}" title="${esc(iri)}">${esc(label || localName(iri))}</button>`;
}
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* not JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}
const postJson = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const sid = () => state.session.session_id;
const stepDef = (id) => state.meta.steps.find((s) => s.id === id);

// Minimal, safe Markdown: escape first, then format.
function md(text) {
  const blocks = String(text || "").split(/```/);
  return blocks.map((block, i) => {
    if (i % 2 === 1) {
      const body = block.replace(/^[a-z]*\n/, "");
      return `<pre><code>${esc(body.trimEnd())}</code></pre>`;
    }
    const lines = esc(block).split("\n");
    let html = "", inList = false;
    for (const raw of lines) {
      const line = raw.trim();
      const li = line.match(/^[-*] (.*)$/);
      if (li) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(li[1])}</li>`; continue; }
      if (inList) { html += "</ul>"; inList = false; }
      if (!line) continue;
      const h = line.match(/^#{1,4} (.*)$/);
      html += h ? `<p><b>${inline(h[1])}</b></p>` : `<p>${inline(line)}</p>`;
    }
    if (inList) html += "</ul>";
    return html;
  }).join("");
}
function inline(s) {
  return s
    .replace(/`([^`]+)`/g, (_, c) => isIri(c.replace(/&amp;/g, "&")) ? iriBtn(c.replace(/&amp;/g, "&")) : `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>");
}

// ------------------------------------------------------------------ boot
async function boot() {
  state.meta = await api("/api/meta");
  $("#f-level").insertAdjacentHTML("beforeend", state.meta.levels.map((l) => `<option>${esc(l)}</option>`).join(""));
  const pol = state.meta.policies.map((p) => `<option>${esc(p)}</option>`).join("");
  $("#f-policy").innerHTML = pol;
  $("#run-policy").innerHTML = pol;
  if (state.meta.policies.includes("registry-default-v1")) $("#f-policy").value = "registry-default-v1";
  $("#samples").innerHTML = state.meta.samples.map((s) =>
    `<button class="sample" data-sample="${esc(s.id)}"><b>${esc(s.file)}</b><span>${esc(s.title)}${s.shapes ? " · with shapes" : ""} · declared ${esc(s.declared)}</span></button>`).join("");
  const a = state.meta.assistant;
  $("#brand-sub").textContent = `Ontology Validation Agent ${state.meta.engine} · assistant ${a.mode === "live" ? a.model : "offline"}`;
  // Deep link: /?sample=rail&step=custom[&ask=question] opens a sample at a step.
  const params = new URLSearchParams(location.search);
  if (params.get("sample")) {
    const fd = new FormData(); fd.append("sample", params.get("sample"));
    await createSession(fd);
    if (params.get("step")) await goto(params.get("step"));
    if (params.get("ask")) await ask(params.get("ask"));
    return;
  }
  const saved = sessionStorageGet("ova-session");
  if (saved) {
    try { state.session = await api(`/api/sessions/${saved}`); return enterWorkspace(sessionStorageGet("ova-step") || "intake"); }
    catch (_) { sessionStorageSet("ova-session", null); }
  }
  showIntake();
}
function sessionStorageGet(k) { try { return sessionStorage.getItem(k); } catch (_) { return null; } }
function sessionStorageSet(k, v) { try { v === null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (_) { /* storage blocked */ } }

function showIntake() {
  $("#intake").hidden = false; $("#workspace").hidden = true; $("#run-bar").hidden = true;
  state.session = null; sessionStorageSet("ova-session", null);
}

async function createSession(formData) {
  $("#f-submit").disabled = true; $("#f-msg").textContent = "";
  document.body.style.cursor = "progress";
  try {
    state.session = await api("/api/sessions", { method: "POST", body: formData });
    sessionStorageSet("ova-session", sid());
    await enterWorkspace("intake");
  } catch (e) { $("#f-msg").textContent = e.message; }
  finally { $("#f-submit").disabled = false; document.body.style.cursor = ""; }
}

async function enterWorkspace(step) {
  $("#intake").hidden = true; $("#workspace").hidden = false; $("#run-bar").hidden = false;
  renderRunBar();
  await goto(step);
}

function renderRunBar() {
  const s = state.session;
  $("#run-source").textContent = s.source;
  $("#run-source").title = `${s.source} · run ${s.run_id}`;
  const v = $("#run-verdict"); v.textContent = s.verdict; v.className = `pill v-${s.verdict}`;
  $("#run-policy").value = s.policy;
  $("#dl-md").href = `/api/sessions/${sid()}/report.md`;
  $("#dl-json").href = `/api/sessions/${sid()}/report.json`;
  renderAssistantStatus(s.assistant);
}

// ------------------------------------------------------------------ stepper
function renderStepper() {
  const groups = { 0: "Submission", 1: "Automated · can block", 5: "Assisted · judgement", 7: "Decision" };
  $("#steps").innerHTML = state.session.steps.map((s) => {
    const def = stepDef(s.id);
    const head = groups[s.n] !== undefined ? `<li class="group">${groups[s.n]}</li>` : "";
    const statusText = { clear: "clear", attention: "needs attention", blocked: "blocking", "not-run": "not run", done: "done" }[s.status] || s.status;
    return `${head}<li><button class="step-btn st-${s.status} ${s.id === state.step ? "active" : ""}" data-step="${s.id}" aria-current="${s.id === state.step ? "step" : "false"}">
      <span class="step-n">${s.n}</span>
      <span class="step-label">${esc(def.title)}<small>${statusText}${s.signed ? ' · <span class="signed">reviewed ✓</span>' : ""}</small></span>
    </button></li>`;
  }).join("");
}

async function goto(step) {
  state.step = step; state.focusFinding = null;
  sessionStorageSet("ova-step", step);
  renderStepper();
  $("#stage").innerHTML = `<p class="muted">Loading…</p>`;
  state.assessment = await api(`/api/sessions/${sid()}/steps/${step}`);
  renderStage();
  renderFooter();
  await loadTranscript();
  $("#stage").scrollTop = 0;
}

async function refreshOverview(steps) {
  if (steps) state.session.steps = steps;
  renderStepper();
}

// ------------------------------------------------------------------ stage
function renderStage() {
  const a = state.assessment, def = a.step;
  const statusText = { clear: "Clear", attention: "Needs attention", blocked: "Blocking", "not-run": "Not run", done: "Done" }[a.status] || a.status;
  let html = `<div class="step-head"><div><div class="eyebrow">Step ${def.n} of 7</div><h1>${esc(def.title)}</h1></div>
    <span class="status-tag status-${a.status}">${statusText}</span></div>
    <p class="purpose">${esc(def.purpose)}</p>`;
  if (def.benefit) html += `<div class="tradeoffs"><div><b>Strength</b>${esc(def.benefit)}</div><div><b>Limit</b>${esc(def.limit)}</div></div>`;
  html += ({ intake: intakeView, automated: automatedView, triage: triageView, expert: expertView, verdict: verdictView })[def.kind](a);
  $("#stage").innerHTML = html;
}

function stat(value, label) { return `<div class="stat"><b>${esc(value)}</b><span>${esc(label)}</span></div>`; }

function intakeView(a) {
  const l = a.load;
  if (!l.loaded) {
    return `<div class="card"><h3>The document does not parse</h3><p>${esc(l.error)}</p>
      <p class="muted">Every other check is skipped until it parses (SYN-01). Ask the assistant for help reading the error.</p></div>`;
  }
  const p = a.profile, c = p.counts;
  const mismatch = p.declared_level && p.declared_level !== p.spectrum_level;
  let html = `<div class="card"><h3>Submission <span class="muted">${esc(l.format)} · ${l.triples} triples</span></h3>
    <dl class="card-dl"><dt>Source</dt><dd>${esc(l.source)}</dd><dt>Content hash</dt><dd><code>${esc(l.hash)}</code></dd>
    <dt>Shapes</dt><dd>${a.shapes ? esc(a.shapes.source) + (a.shapes.loaded ? ` · ${a.shapes.triples} triples` : ` · does not parse: ${esc(a.shapes.error)}`) : "none supplied"}</dd>
    <dt>Imports</dt><dd>${l.imports.missing.length ? l.imports.missing.map(esc).join(", ") + " (not fetched)" : "none"}</dd>
    <dt>Policy</dt><dd>${esc(a.policy.id)}: ${esc(a.policy.description)}</dd>
    <dt>Run</dt><dd><code>${esc(a.run_id)}</code> · engine ${esc(a.versions.engine)} · catalogue ${esc(a.versions.catalogue)}</dd></dl></div>`;
  html += `<div class="card"><h3>Measured profile <span class="muted">${mismatch ? "differs from the declared level" : ""}</span></h3>
    <div class="stats">${stat(p.spectrum_level, "measured level")}${stat(p.declared_level || "—", "declared level")}${stat(p.expressivity, "expressivity")}
    ${Object.entries(p.owl_profiles).map(([k, v]) => stat(v.in_profile ? "yes" : "no", `OWL 2 ${k}`)).join("")}</div>
    <ul>${p.spectrum_evidence.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
    ${p.notes.length ? `<p class="muted">${p.notes.map(esc).join("<br>")}</p>` : ""}</div>`;
  html += `<div class="card"><h3>Size</h3><div class="stats">
    ${stat(c.classes, "classes")}${stat(c.object_properties, "object properties")}${stat(c.datatype_properties, "datatype properties")}
    ${stat(c.individuals, "individuals")}${stat(c.skos_concepts, "SKOS concepts")}${stat(c.logical_axioms, "logical axioms")}
    ${stat(c.axiom_richness, "axioms per class")}${stat(c.labels, "labels")}</div></div>`;
  const rc = a.run_counts;
  html += `<div class="card"><h3>Checks <span class="muted">${rc.passed} passed · ${rc.failed} with findings · ${rc.info} info · ${rc.skipped} skipped · ${rc["not-applicable"]} not applicable</span></h3>
    ${a.not_run.length ? `<div class="table-wrap"><table><tr><th>check</th><th>status</th><th>reason</th></tr>
    ${a.not_run.map((r) => `<tr><td>${esc(r.check_id)} ${esc(r.title)}</td><td><span class="run-status rs-${r.status}">${esc(r.status)}</span></td><td>${esc(r.reason)}</td></tr>`).join("")}</table></div>`
      : `<p class="muted">Every S1a check applies to this submission.</p>`}</div>`;
  return html;
}

function findingCard(f, opts = {}) {
  const ev = f.evidence || {};
  const evLines = [];
  if (ev.triples) evLines.push(...ev.triples);
  for (const [k, v] of Object.entries(ev)) if (k !== "triples") evLines.push(`${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  const related = (f.related || []).filter(isIri).map((r) => iriBtn(r)).join(" ");
  const mark = opts.mark;
  return `<div class="finding f-${f.severity} ${f.status === "waived" ? "waived" : ""} ${state.focusFinding === f.finding_id ? "selected" : ""}" data-finding="${esc(f.finding_id)}">
    <div class="f-top"><span class="sev sev-${f.severity}">${esc(f.severity)}</span>
      <span class="f-check">${esc(f.check_id)} ${esc(f.title)}</span><span class="f-id">${esc(f.finding_id)}</span>
      ${f.status !== "confirmed" ? `<span class="run-status rs-skipped">${esc(f.status)}</span>` : ""}</div>
    <div class="f-msg">${esc(f.message)}</div>
    <div class="f-top">${iriBtn(f.focus, f.focus_label)} ${related ? `<span class="muted">related</span> ${related}` : ""}</div>
    <details><summary>Fix and evidence</summary><p>${esc(f.fix_hint)}</p>${evLines.length ? `<pre class="evidence">${esc(evLines.join("\n"))}</pre>` : ""}</details>
    <div class="f-actions">
      <button class="btn small" data-ask="${esc(f.finding_id)}">Ask assistant</button>
      <button class="btn small ghost" data-askfix="${esc(f.finding_id)}">How to fix?</button>
      ${opts.marks ? markControls(f.finding_id, mark) : ""}
    </div></div>`;
}

function markControls(fid, mark) {
  const m = mark || {};
  return `<span class="mark-row f-actions">${state.meta.marks.map((k) =>
    `<button class="btn small ${m.mark === k ? "on" : ""}" data-mark="${k}" data-fid="${esc(fid)}">${k}</button>`).join("")}
    <input type="text" placeholder="comment for the curator" value="${esc(m.comment || "")}" data-comment="${esc(fid)}" aria-label="Comment on ${esc(fid)}"></span>`;
}

function automatedView(a) {
  const c = a.counts;
  let html = `<div class="card"><h3>Checks in this layer <span class="muted">${c.blocker} blocker · ${c.major} major · ${c.minor} minor · ${c.info} info${a.waived ? ` · ${a.waived} waived` : ""}</span></h3>
    <div class="table-wrap"><table><tr><th>check</th><th>status</th><th class="num">findings</th><th>severity</th></tr>
    ${a.checks.map((r) => `<tr><td><b>${esc(r.check_id)}</b> ${esc(r.title)}<br><span class="muted">${esc(r.reason || r.detects)}</span></td>
      <td><span class="run-status rs-${r.status}">${esc(r.status)}</span></td><td class="num">${r.findings}</td><td>${esc(r.severity)}</td></tr>`).join("")}
    </table></div></div>`;
  html += a.findings.length
    ? `<h2>Findings (${a.findings.length})</h2>${a.findings.map((f) => findingCard(f)).join("")}`
    : `<div class="card"><p>No findings in this layer.${a.status === "not-run" ? " None of its checks applied or ran; see step 0 for why." : ""}</p></div>`;
  return html;
}

function triageView(a) {
  if (!a.total) return `<div class="card"><p>Nothing to triage: no blocker, major or minor finding remains.</p></div>`;
  const marks = state.assessment.marks || {};
  let html = `<div class="card"><h3>Progress <span class="muted">${a.marked} of ${a.total} findings marked</span></h3>
    <div class="stats">${stat(a.entities, "entities with findings")}${stat(a.total, "findings")}
    ${state.meta.marks.map((m) => stat(a.by_mark[m], m)).join("")}</div>
    <p class="muted">Grouped by entity, worst first. Ask the assistant to explain any finding; mark it <b>agree</b>, <b>dispute</b> or <b>unsure</b>. Disputed and unsure findings go to expert review.</p></div>`;
  html += a.clusters.map((cl) => `<div class="cluster"><div class="cluster-head"><span class="sev sev-${cl.worst}">${esc(cl.worst)}</span>
      ${iriBtn(cl.focus, cl.focus_label)} <span class="muted">${cl.findings.length} finding(s): ${cl.checks.map(esc).join(", ")}</span></div>
      ${cl.findings.map((f) => findingCard(f, { marks: true, mark: marks[f.finding_id] })).join("")}</div>`).join("");
  return html;
}

function expertView(a) {
  let html = `<div class="card"><h3>Business-fit checklist <span class="muted">${a.answered} of ${a.checklist.length} answered</span></h3>
    ${a.checklist.map((q) => {
      const ans = q.answer || {};
      return `<div class="checklist-item"><b>${esc(q.id)}</b> ${esc(q.question)}
        <div class="answers">${state.meta.answers.map((v) => `<button class="btn small ${ans.answer === v ? "on" : ""}" data-check="${esc(q.id)}" data-answer="${v}">${v}</button>`).join("")}</div>
        <input type="text" style="width:100%" placeholder="note" value="${esc(ans.comment || "")}" data-checknote="${esc(q.id)}" aria-label="Note for ${esc(q.id)}"></div>`;
    }).join("")}</div>`;
  html += `<h2>Judgement calls from triage (${a.disputed.length})</h2>`;
  html += a.disputed.length
    ? a.disputed.map((f) => findingCard(f, { marks: true, mark: f.review })).join("")
    : `<div class="card"><p class="muted">No finding was disputed or marked unsure in triage.</p></div>`;
  if (!a.judgement_checks.length) html += `<p class="muted">Stage S1a has no LLM- or human-adjudicated checks; those (is-a overload, OntoClean, synonyms) arrive in S1b.</p>`;
  return html;
}

function verdictView(a) {
  const d = a.decision, r = a.record;
  const final = r.final;
  const marks = Object.values(r.marks || {});
  let html = `<div class="verdict-card v-${d.verdict}"><div class="eyebrow">Verdict under ${esc(d.policy)}</div>
    <div class="big">${esc(d.verdict)}</div><ul>${d.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  html += `<div class="card"><h3>Counts</h3><div class="stats">${Object.entries(d.counts).map(([k, v]) => stat(v, k)).join("")}${stat(d.waived.length, "waived")}</div></div>`;
  if (a.waived.length) html += `<h2>Waived</h2>${a.waived.map((f) => findingCard(f)).join("")}`;
  html += `<div class="card"><h3>Review record</h3>
    <p>${marks.length} finding marks (${state.meta.marks.map((m) => `${marks.filter((x) => x.mark === m).length} ${m}`).join(", ")}),
    ${Object.keys(r.checklist || {}).length} of ${state.meta.checklist.length} checklist answers,
    ${Object.keys(r.signoffs || {}).length} steps marked reviewed.</p>
    <p class="muted">Reviewer input is recorded with the report for the curator. It does not change the verdict: only fixing the ontology or a policy waiver does.</p></div>`;
  html += `<div class="card"><h3>Sign-off</h3>${final
    ? `<p><b>${esc(final.reviewer)}</b> ${final.decision === "endorse" ? "endorsed" : "escalated"} the <b>${esc(final.verdict)}</b> verdict at ${esc(final.at)}${final.note ? `: ${esc(final.note)}` : ""}.</p>`
    : ""}
    <form class="final-form" id="final-form">
      <input type="text" name="reviewer" placeholder="Reviewer name" required value="${esc(final?.reviewer || "")}" aria-label="Reviewer name">
      <div class="answers">${state.meta.final_decisions.map((v, i) => `<label><input type="radio" name="decision" value="${v}" ${(final ? final.decision === v : i === 0) ? "checked" : ""}> ${v === "endorse" ? "Endorse the verdict" : "Escalate to the curator"}</label>`).join(" ")}</div>
      <textarea name="note" rows="2" placeholder="Note (optional)">${esc(final?.note || "")}</textarea>
      <div><button class="btn primary" type="submit">Record sign-off</button>
      <a class="btn ghost" href="/api/sessions/${sid()}/report.md" download>Download report</a></div></form></div>`;
  return html;
}

function renderFooter() {
  const idx = state.meta.steps.findIndex((s) => s.id === state.step);
  $("#prev").disabled = idx <= 0;
  $("#next").hidden = idx >= state.meta.steps.length - 1;
  const so = state.assessment.signoff;
  $("#signoff").innerHTML = state.step === "verdict" ? "" : so
    ? `<span class="signed">Reviewed ✓ ${so.status === "needs-work" ? "(needs work)" : ""}</span> <button class="btn small ghost" data-signoff="needs-work">Needs work</button>`
    : `<button class="btn small" data-signoff="done">Mark step reviewed</button> <button class="btn small ghost" data-signoff="needs-work">Needs work</button>`;
}

// ------------------------------------------------------------------ assistant
function renderAssistantStatus(a) {
  const mode = $("#assistant-mode");
  mode.textContent = a.mode === "live" ? a.model : "offline · deterministic";
  mode.className = `mode ${a.mode}`;
  $("#assist-status").textContent = `Assistant: ${a.mode === "live" ? `${a.model}, ${a.calls}/${a.max_calls} calls` : "offline simulator (set OVA_ASSISTANT_MODEL for Claude)"} · critic corrections: ${a.critic_corrections ?? 0}`;
}

async function loadTranscript() {
  const def = stepDef(state.step);
  $("#assistant-sub").textContent = `Step ${def.n}: ${def.title}`;
  const t = await api(`/api/sessions/${sid()}/chat/${state.step}`);
  const box = $("#transcript");
  box.innerHTML = t.messages.length ? "" : `<p class="empty-chat">Ask about anything on this step: a finding, a check, an entity, or the verdict. Answers are grounded in the engine's results; the assistant cannot change findings or the verdict.</p>`;
  for (const m of t.messages) appendMessage(m);
  $("#chips").innerHTML = def.questions.map((q) => `<button class="chip" data-chip="${esc(q)}">${esc(q)}</button>`).join("");
  renderAssistantStatus(t.assistant);
  setContext(null);
}

function appendMessage(m) {
  const box = $("#transcript");
  const el = document.createElement("div");
  if (m.role === "user") {
    el.className = "msg user";
    el.innerHTML = `${m.finding_id ? `<span class="ctx">about ${esc(m.finding_id)}</span>` : ""}${esc(m.text)}`;
  } else {
    el.className = "msg bot";
    const tools = (m.tool_calls || []).map((c) => `${c.tool}${c.ok ? "" : " ✕"}`).join(", ");
    el.innerHTML = md(m.answer) +
      ((m.corrections || []).length ? `<div class="critic"><b>Critic:</b> ${m.corrections.map(esc).join(" ")}</div>` : "") +
      `<div class="meta">${esc(m.model)}${tools ? ` · tools: ${esc(tools)}` : ""}</div>`;
  }
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}

function setContext(fid) {
  state.focusFinding = fid;
  $("#context-pill").hidden = !fid;
  if (fid) $("#context-text").textContent = `About finding ${fid}`;
  document.querySelectorAll(".finding").forEach((el) => el.classList.toggle("selected", el.dataset.finding === fid));
}

async function ask(question) {
  if (!question.trim() || state.busy) return;
  state.busy = true; $("#ask").disabled = true;
  appendMessage({ role: "user", text: question, finding_id: state.focusFinding });
  const typing = document.createElement("div");
  typing.className = "typing"; typing.textContent = "Assistant is looking it up…";
  $("#transcript").appendChild(typing);
  try {
    const r = await postJson(`/api/sessions/${sid()}/chat`, { step: state.step, message: question, finding_id: state.focusFinding });
    typing.remove();
    appendMessage({ role: "assistant", ...r });
    renderAssistantStatus(r.assistant);
  } catch (e) {
    typing.remove();
    appendMessage({ role: "assistant", answer: `Error: ${e.message}`, model: "—" });
  } finally { state.busy = false; $("#ask").disabled = false; }
}

// ------------------------------------------------------------------ entity card
async function showEntity(iri) {
  const dlg = $("#entity-dialog");
  $("#entity-title").textContent = localName(iri);
  $("#entity-body").innerHTML = `<p class="muted">Loading…</p>`;
  dlg.showModal();
  try {
    const c = await api(`/api/sessions/${sid()}/entity?iri=${encodeURIComponent(iri)}`);
    $("#entity-title").textContent = c.label;
    const rows = [["IRI", `<code>${esc(c.iri)}</code>`]];
    const list = (k, title, asIri = true) => c[k] && rows.push([title, c[k].map((v) => asIri && isIri(v) ? iriBtn(v) : esc(v)).join(", ")]);
    list("types", "types"); list("labels", "labels", false); list("definitions", "definition", false);
    list("parents", "parents"); list("children", "children"); list("equivalent", "equivalent to");
    list("disjoint_with", "disjoint with"); list("restrictions", "restrictions", false);
    list("domain", "domain"); list("range", "range"); list("used_as_domain_of", "domain of");
    let html = `<dl class="card-dl">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
    if (c.findings) html += `<h3 style="margin-top:12px">Findings</h3><ul>${c.findings.map((f) => `<li><b>${esc(f.finding_id)}</b> ${esc(f.check_id)} <span class="sev sev-${f.severity}">${esc(f.severity)}</span> ${esc(f.message)}</li>`).join("")}</ul>`;
    html += `<p><button class="btn small" data-askentity="${esc(c.iri)}">Ask the assistant about ${esc(c.label)}</button></p>`;
    $("#entity-body").innerHTML = html;
  } catch (e) { $("#entity-body").innerHTML = `<p>${esc(e.message)}</p>`; }
}

// ------------------------------------------------------------------ events
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, a");
  if (!t) return;
  const d = t.dataset;
  try {
    if (d.sample) {
      const fd = new FormData(); fd.append("sample", d.sample); fd.append("policy", $("#f-policy").value);
      if ($("#f-level").value) fd.append("declared_level", $("#f-level").value);
      await createSession(fd);
    } else if (d.step) { await goto(d.step); }
    else if (d.iri) { await showEntity(d.iri); }
    else if (d.ask) { setContext(d.ask); await ask(`Explain ${d.ask}: why was it reported and what does it mean?`); }
    else if (d.askfix) { setContext(d.askfix); await ask(`How do I fix ${d.askfix}?`); }
    else if (d.askentity) { $("#entity-dialog").close(); await ask(`Tell me about \`${d.askentity}\` and its findings.`); }
    else if (d.chip) { await ask(d.chip); }
    else if (d.mark) {
      const input = document.querySelector(`[data-comment="${CSS.escape(d.fid)}"]`);
      const current = (state.assessment.marks || {})[d.fid];
      const mark = current && current.mark === d.mark ? null : d.mark;
      const r = await postJson(`/api/sessions/${sid()}/marks`, { finding_id: d.fid, mark, comment: input ? input.value : "" });
      await refreshOverview(r.steps);
      await reloadAssessment();
    } else if (d.check) {
      const note = document.querySelector(`[data-checknote="${CSS.escape(d.check)}"]`);
      const r = await postJson(`/api/sessions/${sid()}/checklist`, { id: d.check, answer: d.answer, comment: note ? note.value : "" });
      await refreshOverview(r.steps);
      await reloadAssessment();
    } else if (d.signoff) {
      const r = await postJson(`/api/sessions/${sid()}/signoff`, { step: state.step, status: d.signoff, note: "" });
      await refreshOverview(r.steps);
      if (d.signoff === "done") { const i = state.meta.steps.findIndex((s) => s.id === state.step); await goto(state.meta.steps[Math.min(i + 1, 7)].id); }
      else await reloadAssessment();
    } else if (t.id === "prev" || t.id === "next") {
      const i = state.meta.steps.findIndex((s) => s.id === state.step);
      await goto(state.meta.steps[i + (t.id === "next" ? 1 : -1)].id);
    } else if (t.id === "new-review") { showIntake(); }
    else if (t.id === "entity-close") { $("#entity-dialog").close(); }
    else if (t.id === "context-clear") { setContext(null); }
  } catch (e) { alert(e.message); }
});

// Comments are saved when the field loses focus (only if the finding already has a mark).
document.addEventListener("change", async (ev) => {
  const el = ev.target;
  try {
    if (el.dataset.comment) {
      const fid = el.dataset.comment, current = (state.assessment.marks || {})[fid];
      if (current) await postJson(`/api/sessions/${sid()}/marks`, { finding_id: fid, mark: current.mark, comment: el.value });
    } else if (el.dataset.checknote) {
      const q = state.assessment.checklist?.find((x) => x.id === el.dataset.checknote);
      if (q && q.answer) await postJson(`/api/sessions/${sid()}/checklist`, { id: q.id, answer: q.answer.answer, comment: el.value });
    } else if (el.id === "run-policy" && state.session) {
      const fd = new FormData(); fd.append("policy", el.value);
      state.session = await api(`/api/sessions/${sid()}/rerun`, { method: "POST", body: fd });
      sessionStorageSet("ova-session", sid());
      renderRunBar(); await goto(state.step);
    }
  } catch (e) { alert(e.message); }
});

async function reloadAssessment() {
  const scroll = $("#stage").scrollTop;
  state.assessment = await api(`/api/sessions/${sid()}/steps/${state.step}`);
  renderStage(); renderFooter(); $("#stage").scrollTop = scroll;
  setContext(state.focusFinding);
}

$("#intake-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  if (!$("#f-file").files.length) { $("#f-msg").textContent = "Choose an ontology file, or open a sample below."; return; }
  if (!$("#f-shapes").files.length) fd.delete("shapes");
  if (!fd.get("declared_level")) fd.delete("declared_level");
  await createSession(fd);
});

document.addEventListener("submit", async (ev) => {
  if (ev.target.id !== "final-form") return;
  ev.preventDefault();
  const fd = new FormData(ev.target);
  try {
    await postJson(`/api/sessions/${sid()}/final`, { reviewer: fd.get("reviewer"), decision: fd.get("decision"), note: fd.get("note") || "" });
    state.session = await api(`/api/sessions/${sid()}`);
    await refreshOverview(state.session.steps);
    await reloadAssessment();
  } catch (e) { alert(e.message); }
});

$("#composer").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const q = $("#question").value; $("#question").value = "";
  ask(q);
});
$("#question").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); $("#composer").requestSubmit(); }
});

boot().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p style="padding:16px">Failed to start: ${esc(e.message)}</p>`); });
