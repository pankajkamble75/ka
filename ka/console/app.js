/* Knowledge Console — vanilla JS, hash-routed. Talks only to /api/knowledge-acquisition. */
const API = '/api/knowledge-acquisition';
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pill = (s, cls = '') => `<span class="pill ${esc(s)} ${cls}">${esc(s)}</span>`;
const scopePill = (k) => `<span class="pill scope">${esc(k)}</span>`;
const when = (iso) => iso ? new Date(iso).toLocaleString() : '—';
const who = () => localStorage.getItem('ka.user') || 'console-user';
// [block plan-02]
const token = () => { try { return localStorage.getItem('ka.token') || ''; } catch { return ''; } };
const authHeaders = () => (token() ? { Authorization: 'Bearer ' + token() } : {});
function ensureTokenField() {
  // the token field must exist even when the API refuses us, or there is no way to enter one
  if ($('#tok')) return;
  $('#nav').innerHTML = `<h4>You</h4><input id="who" value="${esc(who())}"><label>Access token</label><input id="tok" type="password" value="${esc(token())}" placeholder="KA_ACCESS_TOKEN">`;
  $('#who').addEventListener('change', (e) => { localStorage.setItem('ka.user', e.target.value); });
  $('#tok').addEventListener('change', (e) => { try { localStorage.setItem('ka.token', e.target.value.trim()); } catch { /* ignore */ } toast('Access token saved'); render(); });
}
// [/block plan-02]

let TOAST_T;
function toast(msg, err = false) {
  const t = $('#toast'); t.innerHTML = `<div class="toast ${err ? 'err' : ''}">${esc(msg)}</div>`;
  clearTimeout(TOAST_T); TOAST_T = setTimeout(() => (t.innerHTML = ''), err ? 7000 : 3500);
}
async function api(path, opts = {}) {
  const r = await fetch(API + path, { headers: { 'Content-Type': 'application/json', ...authHeaders() }, ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) throw new Error('Access token required or wrong — paste it under "You" in the sidebar.');
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
async function form(path, fd) {
  const r = await fetch(API + path, { method: 'POST', body: fd, headers: authHeaders() });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) throw new Error('Access token required or wrong — paste it under "You" in the sidebar.');
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

/* ------------------------------------------------------------------ routing */
const routes = [
  [/^#?\/?$/, dashboard],
  [/^#\/dashboard$/, dashboard],
  [/^#\/add$/, addView],
  [/^#\/nuggets(?:\?(.*))?$/, nuggetsView],
  [/^#\/browse(?:\?(.*))?$/, browseView],
  [/^#\/images(?:\?(.*))?$/, imagesView],
  [/^#\/nugget\/([^/]+)$/, nuggetView],
  [/^#\/conflict\/([^/]+)$/, conflictView],
  [/^#\/source\/([^/]+)$/, sourceView],
  [/^#\/mission\/([^/]+)$/, missionView],
  [/^#\/change\/([^/]+)$/, changeView],
  [/^#\/scope\/([A-Z_]+)\/([^/]+)(?:\/([a-z-]+))?$/, (t, i) => { location.hash = `#/browse?scope=${t}|${i}`; return ''; }],
];
const TAB_LABELS = { '#/add': '1 · Add knowledge', '#/nuggets': '2 · Knowledge nuggets', '#/browse': '3 · Browse by scope', '#/dashboard': '4 · Dashboard', '#/images': '5 · Images' };
function tabOf(hash) { const base = (hash || '#/').split('?')[0]; return base === '#/' || base === '#' ? '#/dashboard' : (TAB_LABELS[base] ? base : null); }
let lastTab = null;
try { lastTab = sessionStorage.getItem('ka.lastTab'); } catch { /* private mode */ }

async function render() {
  const main = $('#main');
  const h = location.hash || '#/';
  const tab = tabOf(h);
  if (tab) { lastTab = h; try { sessionStorage.setItem('ka.lastTab', h); } catch { /* ignore */ } }
  for (const [re, fn] of routes) {
    const m = h.match(re);
    if (m) {
      try { main.innerHTML = await fn(...m.slice(1)); } catch (e) { main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
      if (!tab) {
        const back = lastTab || '#/nuggets';
        const label = TAB_LABELS[tabOf(back)] || 'Knowledge nuggets';
        main.insertAdjacentHTML('afterbegin', `<div class="backbar"><a href="${esc(back)}">← Back to ${esc(label)}</a></div>`);
      }
      bind(main); break;
    }
  }
  await nav();
}
window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
/* Never a blank page: surface script or API failures in the main pane. */
function fail(msg) { const m = document.getElementById('main'); if (m) m.innerHTML = `<div class="empty">Knowledge Console could not start.<br><span class="mono">${esc(msg)}</span><br><br>Is the backend running on this host and port? <a href="${API}/healthz">${API}/healthz</a></div>`; }
window.addEventListener('error', (e) => fail(e.message || String(e)));
window.addEventListener('unhandledrejection', (e) => fail((e.reason && e.reason.message) || String(e.reason)));

/* ------------------------------------------------------------------ nav: four tabs */
async function nav() {
  const h = location.hash || '#/';
  ensureTokenField();
  const on = (p) => (h === p || h.startsWith(p + '?') || (p === '#/dashboard' && h === '#/') ? 'active' : '');
  const detail = /^#\/(nugget|conflict|source|mission|change)\//.test(h);
  const from = detail ? tabOf(lastTab || '#/nuggets') : null;
  const onD = (p) => (from === p ? 'active' : '');
  $('#nav').innerHTML = `
    <a href="#/add" class="${on('#/add') || onD('#/add')}">1 · Add knowledge</a>
    <a href="#/nuggets" class="${on('#/nuggets') || onD('#/nuggets')}">2 · Knowledge nuggets</a>
    <a href="#/browse" class="${on('#/browse') || onD('#/browse')}">3 · Browse by scope</a>
    <a href="#/dashboard" class="${on('#/dashboard') || onD('#/dashboard')}">4 · Dashboard</a>
    <a href="#/images" class="${on('#/images') || onD('#/images')}">5 · Images</a>
    <h4>You</h4><input id="who" value="${esc(who())}" title="Your name, recorded on decisions">
    <label>Access token</label><input id="tok" type="password" value="${esc(token())}" placeholder="KA_ACCESS_TOKEN" title="Required from non-loopback addresses">`;
  $('#who').addEventListener('change', (e) => { localStorage.setItem('ka.user', e.target.value); toast('Acting as ' + e.target.value); });
  $('#tok').addEventListener('change', (e) => { try { localStorage.setItem('ka.token', e.target.value.trim()); } catch { /* ignore */ } toast('Access token saved'); render(); });
}

/* ------------------------------------------------------------------ pages */
function nuggetRows(rows, extra = '') {
  if (!rows.length) return `<div class="empty">Nothing here.</div>`;
  return `<table><tr><th>Nugget</th><th>Statement</th><th>Scope</th><th>Status</th><th>Authority</th>${extra ? '<th></th>' : ''}</tr>${rows.map((n) =>
    `<tr><td><a href="#/nugget/${encodeURIComponent(n.ref)}">${esc(n.ref)}</a><div class="small muted">${esc(n.title)}</div></td><td>${esc(n.statement)}</td><td>${scopePill(n.scope)}</td>
     <td>${pill(n.status)}${n.conflict_open ? ' ' + pill('conflict', 'halt') : ''}</td><td class="small">${esc(n.authority)}</td>${extra ? `<td>${extra(n)}</td>` : ''}</tr>`).join('')}</table>`;
}

const decideBtns = (ref) => `<span class="actions"><button class="primary" data-act="decide" data-ref="${esc(ref)}" data-outcome="APPROVE">Approve</button><button data-act="decide" data-ref="${esc(ref)}" data-outcome="REJECT">Reject</button></span>`;

function proposalRows(ps) {
  if (!ps.length) return `<div class="empty">None.</div>`;
  return `<table><tr><th>Proposal</th><th>Knowledge</th><th>Elements</th><th>Status</th><th></th></tr>${ps.map((p) =>
    `<tr><td><a href="#/change/${p.id}">${p.id}</a><div class="small muted">${when(p.created_at)}</div></td><td>${(p.knowledge_change_ids || []).map((r) => `<a href="#/nugget/${encodeURIComponent(r)}">${esc(r)}</a>`).join(', ')}</td>
     <td class="small">${(p.affected_element_ids || []).map(esc).join('<br>')}</td><td>${pill(p.status)}${p.requires_approval ? ' ' + pill('needs approval', 'warn') : ''}</td>
     <td class="actions">${p.status === 'READY' ? `<button class="primary" data-act="prop" data-id="${p.id}" data-do="approve">Approve</button>` : ''}${p.status === 'APPROVED' ? `<button class="primary" data-act="prop" data-id="${p.id}" data-do="apply">Apply</button>` : ''}${['READY', 'PROPOSED', 'FAILED'].includes(p.status) ? `<button data-act="prop" data-id="${p.id}" data-do="reject">Reject</button>` : ''}</td></tr>`).join('')}</table>`;
}

async function changeView(id) {
  const { proposal: p, executions } = await api(`/graph-changes/${id}`);
  const s = p.impact_summary || {};
  return `<div class="crumbs"><a href="#/dashboard">Dashboard</a> / graph change ${p.id}</div><h1>${p.id} ${pill(p.status)}</h1><p class="sub">${esc(p.reason)}</p>
  <div class="actions">${p.status === 'READY' ? `<button class="primary" data-act="prop" data-id="${p.id}" data-do="approve">Approve</button>` : ''}
  ${p.status === 'APPROVED' ? `<button class="primary" data-act="prop" data-id="${p.id}" data-do="apply">Apply</button>` : ''}
  ${['READY', 'PROPOSED', 'FAILED'].includes(p.status) ? `<button data-act="prop" data-id="${p.id}" data-do="reject">Reject</button><button data-act="prop" data-id="${p.id}" data-do="validate">Re-validate</button>` : ''}
  ${executions.filter((e) => e.status === 'APPLIED').map((e) => `<button class="danger" data-act="rollback" data-id="${e.id}">Roll back ${e.id}</button>`).join('')}</div>
  <h2>Impact analysis</h2><div class="tiles">${['affected_domains', 'affected_instances', 'affected_graph_nodes', 'affected_graph_edges', 'affected_rules', 'affected_processes', 'inherited_descendants', 'overridden_descendants'].map((k) =>
    `<div class="tile ${k === 'overridden_descendants' && s[k] ? 'warn' : ''}"><div class="k">${k.replace(/_/g, ' ')}</div><div class="v">${s[k] ?? 0}</div></div>`).join('')}</div>
  <h2>Inheritance effects</h2>${p.inheritance_effects.length ? `<table><tr><th>Descendant</th><th>State</th><th>Action</th><th>Note</th></tr>${p.inheritance_effects.map((e) =>
    `<tr><td>${scopePill(e.scope.scope_type + ':' + e.scope.scope_id)}</td><td>${pill(e.inheritance_state, e.inheritance_state === 'OVERRIDDEN' ? 'warn' : 'ok')}</td><td>${esc(e.action)}</td><td class="muted">${esc(e.note)}</td></tr>`).join('')}</table>` : '<div class="empty">No descendants.</div>'}
  <h2>Element changes</h2>${p.changes.map((c) => `<div class="card"><b>${esc(c.operation)}</b> ${esc(c.element_kind)} <span class="mono">${esc(c.graph_id)} / ${esc(c.element_id)}</span>
    <div class="diff"><div class="before"><b>Before</b><pre class="small">${esc(JSON.stringify(c.before, null, 1))}</pre></div><div class="after"><b>After</b><pre class="small">${esc(JSON.stringify(c.after, null, 1))}</pre></div></div></div>`).join('')}
  <h2>Validation</h2><table><tr><th>Element</th><th>OK</th><th>Detail</th></tr>${p.validation_results.map((r) => `<tr><td class="mono">${esc(r.element_id)}</td><td>${pill(r.ok ? 'ok' : 'FAILED')}</td><td>${esc(r.detail)}</td></tr>`).join('')}</table>
  <h2>Executions</h2>${executions.length ? `<table><tr><th>Execution</th><th>Status</th><th>Started</th><th>Completed</th><th>Error</th></tr>${executions.map((e) => `<tr><td class="mono">${e.id}${e.rollback_of ? ` (rollback of ${e.rollback_of})` : ''}</td><td>${pill(e.status)}</td><td>${when(e.started_at)}</td><td>${when(e.completed_at)}</td><td class="muted">${esc(e.error || '')}</td></tr>`).join('')}</table>` : '<div class="empty">Not applied yet.</div>'}`;
}

function auditTable(audit) {
  if (!audit.length) return '<div class="empty">No history.</div>';
  return `<table><tr><th>When</th><th>Who</th><th>What</th><th>Why</th><th>Affected</th></tr>${[...audit].reverse().map((a) => `<tr><td class="small">${when(a.when)}</td><td>${esc(a.who)}</td><td class="mono">${esc(a.what)}</td><td class="small muted">${esc(a.why)}</td><td class="small">${a.affected_objects.map((o) => o.match(/^KN-/) ? `<a href="#/nugget/${encodeURIComponent(o)}">${esc(o)}</a>` : esc(o)).join(', ')}</td></tr>`).join('')}</table>`;
}

async function nuggetView(ref) {
  ref = decodeURIComponent(ref);
  const d = await api(`/nugget/${encodeURIComponent(ref)}`);
  const n = d.nugget, L = d.lineage;
  const canDecide = ['PENDING_REVIEW', 'CONFLICT'].includes(n.status);
  const step = (label, html) => `<div class="step"><div class="dot"></div><div class="body"><b>${label}</b>${html}</div></div>`;
  return `<div class="crumbs"><a href="#/nuggets">Knowledge nuggets</a> / <a href="#/browse?scope=${n.scope_type}|${encodeURIComponent(n.scope_id)}">${esc(n.scope_id)}</a> / ${esc(n.canonical_id)}</div>
  <h1>${esc(n.title)}</h1><div class="sub">${pill(n.status)} ${scopePill(n.scope_type + ':' + n.scope_id)} <span class="pill">v${n.version}</span> <span class="pill">${esc(n.knowledge_type)}</span> <span class="pill">${esc(n.authority_type)} · rank ${n.authority_rank}</span> <span class="pill">confidence ${n.confidence}</span>${n.analysis.conflict_open ? ' ' + pill('conflict', 'halt') : ''}</div>
  <div class="card"><h3>Current statement</h3><p style="font-size:var(--fs-15)">${esc(n.statement)}</p><div class="small muted">Normalized: <span class="mono">${esc(n.normalized_meaning)}</span></div>
  ${d.inherited_value ? `<div class="quote">Inherited value — ${esc(d.inherited_value.scope)} → ${esc(d.inherited_value.statement)} (<a href="#/nugget/${encodeURIComponent(d.inherited_value.ref)}">${esc(d.inherited_value.ref)}</a>)</div>` : ''}</div>
  <div class="actions">
    ${canDecide ? decideBtns(n.ref) : ''}${n.analysis.conflict_open ? `<a href="#/conflict/${encodeURIComponent(n.ref)}"><button class="primary">Resolve conflict</button></a>` : ''}
    <button data-act="show" data-target="revise">Propose Correction</button><button data-act="show" data-target="evidence">Add Evidence</button><button data-act="show" data-target="comment">Add Comment</button>
    <button data-act="show" data-target="compare">Compare Version</button>${d.sources[0] ? `<a href="#/source/${d.sources[0].id}"><button>View Source</button></a>` : ''}
    <button data-act="show" data-target="usage">View Graph Usage</button><a href="#/add"><button>Research This</button></a>
    ${canDecide ? `<button data-act="show" data-target="rescope">Propose Scope Change</button>` : ''}
  </div>
  <div id="revise" class="card" hidden><h3>Propose correction → new version</h3><label>Corrected statement</label><textarea id="rv-stmt">${esc(n.statement)}</textarea><label>Reason</label><input id="rv-reason"><div class="actions"><button class="primary" data-act="revise" data-cid="${esc(n.canonical_id)}">Submit as candidate v${(d.version_history.at(-1)?.version || n.version) + 1}</button></div></div>
  <div id="evidence" class="card" hidden><h3>Add evidence</h3><label>Note</label><textarea id="ev-text"></textarea><div class="actions"><button class="primary" data-act="evidence" data-ref="${esc(n.ref)}" data-type="${n.scope_type}" data-id="${esc(n.scope_id)}">Attach</button></div></div>
  <div id="comment" class="card" hidden><h3>Add comment</h3><textarea id="cm-text"></textarea><div class="actions"><button class="primary" data-act="comment" data-ref="${esc(n.ref)}">Comment</button></div></div>
  <div id="rescope" class="card" hidden><h3>Propose scope change</h3><div class="row"><div><label>Type</label><select id="rs-type"><option>STRUCTURE</option><option>PARENT_DOMAIN</option><option>DOMAIN</option><option>INSTANCE</option></select></div><div><label>Id</label><input id="rs-id"></div><div><label>Reason</label><input id="rs-reason"></div><button class="primary" data-act="decide" data-ref="${esc(n.ref)}" data-outcome="CHANGE_SCOPE">Re-scope</button></div><label class="small" style="text-transform:none;letter-spacing:0"><input type="checkbox" id="rs-widen" style="width:auto"> widen visibility if the new scope needs it</label></div>
  <div id="compare" class="card" hidden><h3>Compare versions</h3><div class="row"><div><label>A</label><select id="cmp-a">${d.version_history.map((h) => `<option ${h.version === Math.max(1, n.version - 1) ? 'selected' : ''}>${h.version}</option>`).join('')}</select></div><div><label>B</label><select id="cmp-b">${d.version_history.map((h) => `<option ${h.version === n.version ? 'selected' : ''}>${h.version}</option>`).join('')}</select></div><button data-act="compare" data-cid="${esc(n.canonical_id)}">Compare</button></div><div id="cmp-out"></div></div>
  <div id="usage" class="card" hidden><h3>Graph usage</h3>${d.graph_usage.length ? `<table><tr><th>Graph</th><th>Element</th><th>Kind</th><th>Scope</th><th>Inheritance</th><th>Change</th></tr>${d.graph_usage.map((u) => `<tr><td class="mono">${esc(u.graph_id)}</td><td class="mono">${esc(u.element_id)}</td><td>${esc(u.element_kind)}</td><td>${scopePill(u.scope.scope_type + ':' + u.scope.scope_id)}</td><td>${pill(u.inheritance_state)}</td><td><a href="#/change/${u.graph_change_id}">${esc(u.graph_change_id || '')}</a></td></tr>`).join('')}</table>` : '<div class="empty">Not materialized in any graph (yet).</div>'}</div>
  <div class="grid2">
    <div class="card"><h3>Version history</h3><table><tr><th>Version</th><th>Status</th><th>Statement</th><th>Approved</th></tr>${d.version_history.map((h) => `<tr><td><a href="#/nugget/${encodeURIComponent(h.ref)}">v${h.version}</a></td><td>${pill(h.status)}</td><td class="small">${esc(h.statement)}</td><td class="small">${h.approved_by ? esc(h.approved_by) + ' · ' + when(h.approved_at) : '—'}</td></tr>`).join('')}</table>
      <dl class="kv" style="margin-top:12px"><dt>Effective from</dt><dd>${when(n.effective_from)}</dd><dt>Effective to</dt><dd>${when(n.effective_to)}</dd><dt>Supersedes</dt><dd>${n.supersedes ? `<a href="#/nugget/${encodeURIComponent(n.supersedes)}">${esc(n.supersedes)}</a>` : '—'}</dd><dt>Superseded by</dt><dd>${n.superseded_by ? `<a href="#/nugget/${encodeURIComponent(n.superseded_by)}">${esc(n.superseded_by)}</a>` : '—'}</dd><dt>Created</dt><dd>${esc(n.created_by)} · ${when(n.created_at)}</dd><dt>Channel</dt><dd>${esc(n.channel)}</dd><dt>Tags</dt><dd>${n.tags.map((t) => `<span class="pill">${esc(t)}</span>`).join(' ') || '—'}</dd></dl></div>
    <div class="card"><h3>Lineage</h3><div class="lineage">
      ${step('Sources', d.sources.map((s) => `<div><a href="#/source/${s.id}">${esc(s.title)}</a> <span class="small muted">${esc(s.source_type)} · ${esc(s.authority_type)}</span></div>`).join('') || '<span class="muted">none</span>')}
      ${step('Evidence', d.evidence.map((e) => `<div class="quote small">${esc(e.locator || '')} — ${esc(e.excerpt)}</div>`).join('') || '<span class="muted">none</span>')}
      ${L.research_runs.length ? step('Research', L.research_runs.map((r) => `<div><a href="#/mission/${r.mission_id}">${r.mission_id}</a> · ${r.run_id} · ${esc(r.agent_id)}</div>`).join('')) : ''}
      ${L.corrections.length ? step('Corrections', L.corrections.map((c) => `<div>${c.id} by ${esc(c.submitted_by)}: ${esc(c.what_is_incorrect)} → ${esc(c.correct_value)}</div>`).join('')) : ''}
      ${step('Candidate', `<div>${esc(n.ref)} · analyzed ${when(n.analysis.analyzed_at)}${n.analysis.scope_decision ? `<div class="small muted">Scope decision: ${esc(n.analysis.scope_decision.scope)} (${n.analysis.scope_decision.confidence})</div>` : ''}</div>`)}
      ${step('Governance', d.governance.map((g) => `<div>${pill(g.outcome, g.outcome.includes('REJECT') || g.outcome === 'KEEP_EXISTING' ? 'halt' : 'ok')} by ${esc(g.decided_by)} · ${when(g.decided_at)}${g.automatic ? ' · automatic' : ''}<div class="small muted">${esc(g.reason)}</div></div>`).join('') || '<span class="muted">no decision yet</span>')}
      ${step('Graph changes', d.graph_changes.map((p) => `<div><a href="#/change/${p.id}">${p.id}</a> ${pill(p.status)} <span class="small mono">${p.affected_element_ids.map(esc).join(', ')}</span></div>`).join('') || '<span class="muted">none</span>')}
      ${step('Materialized as', L.materialized_as.map((m) => `<div class="mono small">${esc(m.graph_id)} / ${esc(m.element_id)} (${esc(m.element_kind)})</div>`).join('') || '<span class="muted">not in a graph</span>')}
    </div></div>
  </div>
  <h2>Relationships</h2>${d.relationships.length ? `<table><tr><th>Type</th><th>Other</th><th>Confidence</th><th>Explanation</th></tr>${d.relationships.map((r) => `<tr><td>${pill(r.relationship_type, r.relationship_type === 'CONTRADICTS' ? 'halt' : '')}</td><td><a href="#/nugget/${encodeURIComponent(r.other)}">${esc(r.other)}</a></td><td>${r.confidence}</td><td class="small muted">${esc(r.explanation)}</td></tr>`).join('')}</table>` : '<div class="empty">No related knowledge.</div>'}
  <h2>Used by descendants</h2>${d.used_by_descendants.length ? `<table><tr><th>Scope</th><th>Element</th><th>Inheritance</th></tr>${d.used_by_descendants.map((u) => `<tr><td>${scopePill(u.scope.scope_type + ':' + u.scope.scope_id)}</td><td class="mono">${esc(u.graph_id)} / ${esc(u.element_id)}</td><td>${pill(u.inheritance_state)}</td></tr>`).join('')}</table>` : '<div class="empty">None.</div>'}
  <h2>Comments</h2>${n.comments.length ? n.comments.map((c) => `<div class="quote"><b>${esc(c.by)}</b> <span class="small muted">${when(c.at)}</span><br>${esc(c.text)}</div>`).join('') : '<div class="empty">No comments.</div>'}
  <h2>Audit</h2>${auditTable(d.audit)}`;
}

async function conflictView(ref) {
  ref = decodeURIComponent(ref);
  const d = await api(`/conflicts/${encodeURIComponent(ref)}`);
  if (!d.conflicts.length) return `<h1>No open conflict</h1><p><a href="#/nugget/${encodeURIComponent(ref)}">Back to ${esc(ref)}</a></p>`;
  const c = d.conflicts[0], x = c.explanation, llm = x.llm || {};
  const side = (title, n, srcs, scope, eff, auth) => `<div class="card"><h3>${title}</h3><p style="font-size:var(--fs-15)"><a href="#/nugget/${encodeURIComponent(n.ref)}">${esc(n.ref)}</a> — ${esc(n.statement)}</p>
    <dl class="kv"><dt>Scope</dt><dd>${scopePill(scope)}</dd><dt>Status</dt><dd>${pill(n.status)}</dd><dt>Authority</dt><dd>${esc(auth[0])} (rank ${auth[1]})</dd><dt>Effective</dt><dd>${when(eff[0])} → ${when(eff[1])}</dd><dt>Sources</dt><dd>${srcs.map((s) => `<a href="#/source/${s.id}">${esc(s.title)}</a>`).join(', ') || '—'}</dd></dl></div>`;
  return `<div class="crumbs"><a href="#/nuggets?view=conflicts">Knowledge nuggets</a> / conflict</div><h1>Conflict resolution</h1><p class="sub">The LLM may recommend. It does not establish enterprise truth (§33).</p>
  <div class="grid2">${side('Existing knowledge', c.existing, c.existing_sources, c.existing_scope, c.existing_effective, c.authority_comparison.existing)}
  ${side('New candidate', c.candidate, c.candidate_sources, c.proposed_scope, c.candidate_effective, c.authority_comparison.candidate)}</div>
  <div class="card"><h3>Explanation</h3><dl class="kv"><dt>Detected as</dt><dd>${pill(x.relationship, 'halt')} (confidence ${x.confidence})</dd><dt>Why they conflict</dt><dd>${esc(llm.why_conflict || x.explanation)}</dd>
    <dt>Both contextually valid?</dt><dd>${x.both_valid === null || x.both_valid === undefined ? 'unclear' : x.both_valid ? 'possibly' : 'no'}</dd><dt>Suggested resolution</dt><dd><b>${esc(x.suggested_resolution || '—')}</b> ${llm.rationale ? `<span class="muted">— ${esc(llm.rationale)}</span>` : ''}</dd></dl></div>
  <h2>Actions</h2><div class="actions">
    <button data-act="decide" data-ref="${esc(ref)}" data-outcome="KEEP_EXISTING" data-existing="${esc(c.existing.ref)}">Keep Existing</button>
    <button class="primary" data-act="decide" data-ref="${esc(ref)}" data-outcome="ACCEPT_NEW" data-existing="${esc(c.existing.ref)}">Accept New</button>
    <button data-act="show" data-target="merge">Merge…</button>
    <button data-act="decide" data-ref="${esc(ref)}" data-outcome="BOTH_VALID_ADD_CONTEXT" data-existing="${esc(c.existing.ref)}">Both Valid — Add Context</button>
    <button data-act="show" data-target="rescope">Change Scope…</button>
    <button data-act="decide" data-ref="${esc(ref)}" data-outcome="REQUEST_MORE_RESEARCH">Request More Research</button>
    <button class="danger" data-act="decide" data-ref="${esc(ref)}" data-outcome="REJECT">Reject Candidate</button>
    <a href="#/nugget/${encodeURIComponent(ref)}"><button>Add Comment</button></a></div>
  <label>Reason (recorded on the decision)</label><input id="decide-reason" placeholder="Why this resolution?">
  <div id="merge" class="card" hidden><h3>Merged statement</h3><textarea id="merge-stmt">${esc(c.candidate.statement)}</textarea><div class="actions"><button class="primary" data-act="decide" data-ref="${esc(ref)}" data-outcome="MERGE" data-existing="${esc(c.existing.ref)}">Merge into ${esc(c.existing.canonical_id)} as a new version</button></div></div>
  <div id="rescope" class="card" hidden><h3>Change scope</h3><div class="row"><div><label>Type</label><select id="rs-type"><option>STRUCTURE</option><option>PARENT_DOMAIN</option><option>DOMAIN</option><option>INSTANCE</option></select></div><div><label>Id</label><input id="rs-id"></div><button class="primary" data-act="decide" data-ref="${esc(ref)}" data-outcome="CHANGE_SCOPE">Re-scope candidate</button></div><label class="small" style="text-transform:none;letter-spacing:0"><input type="checkbox" id="rs-widen" style="width:auto"> widen visibility if the new scope needs it</label></div>`;
}

async function sourceView(id) {
  const d = await api(`/sources/${id}`);
  const s = d.source;
  return `<div class="crumbs">Sources / ${esc(s.id)}</div><h1>${esc(s.title)}</h1><div class="sub"><span class="pill">${esc(s.source_type)}</span> <span class="pill">${esc(s.authority_type)}</span> <span class="pill">${esc(s.visibility)}</span> ${s.scope ? scopePill(s.scope.scope_type + ':' + s.scope.scope_id) : ''} ${pill(s.extraction_status, s.extraction_status === 'EXTRACTED' ? 'ok' : 'warn')}</div>
  <dl class="kv card"><dt>Location</dt><dd>${esc(s.original_location || s.original_filename || '—')}</dd><dt>Owner</dt><dd>${esc(s.owner || '—')}</dd><dt>Author</dt><dd>${esc(s.author || '—')}</dd><dt>Ingested</dt><dd>${when(s.ingested_at)}</dd><dt>Effective date</dt><dd>${esc(s.effective_date || '—')}</dd><dt>Checksum</dt><dd class="mono">${esc(s.checksum)}</dd><dt>Content version</dt><dd>${s.content_version}</dd><dt>Channel</dt><dd>${esc(s.channel)}</dd></dl>
  <h2>Knowledge extracted <span class="muted">${d.nuggets.length}</span></h2>${nuggetRows(d.nuggets)}
  <h2>Versions</h2>${d.versions.map((v) => `<div class="card"><b>v${v.version}</b> ${pill(v.extraction_status, v.extraction_status === 'EXTRACTED' ? 'ok' : 'warn')} <span class="small muted">${when(v.created_at)} · ${v.byte_size} bytes · ${esc(v.media_type)} ${v.extraction_note ? '· ' + esc(v.extraction_note) : ''}</span><div class="quote small">${esc((v.text || '').slice(0, 3000))}${(v.text || '').length > 3000 ? '…' : ''}</div></div>`).join('')}`;
}

async function missionView(id) {
  const d = await api(`/research/missions/${id}`);
  const m = d.mission;
  return `<div class="crumbs"><a href="#/browse?scope=${m.scope_type}|${encodeURIComponent(m.scope_id)}">${esc(m.scope_id)}</a> / research</div><h1>${esc(m.objective)}</h1>
  <div class="sub">${pill(m.status)} ${scopePill(m.scope_type + ':' + m.scope_id)} <span class="pill">${esc(m.trigger)}</span> <span class="pill">visibility ≥ ${esc(m.permitted_visibility)}</span> · by ${esc(m.created_by)} · ${when(m.created_at)}</div>
  ${m.research_questions.length ? `<div class="card"><h3>Research questions</h3><ul>${m.research_questions.map((q) => `<li>${esc(q)}</li>`).join('')}</ul></div>` : ''}
  <div class="actions"><button class="primary" data-act="run-mission" data-id="${m.mission_id}">Run again</button></div>
  <h2>Candidate nuggets <span class="muted">${d.candidates.length}</span></h2>${nuggetRows(d.candidates, (n) => ['PENDING_REVIEW', 'CONFLICT'].includes(n.status) ? decideBtns(n.ref) : '')}
  <h2>Research runs</h2>${d.runs.map((r) => `<div class="card small"><b>${r.run_id}</b> ${pill(r.status)} · agent ${esc(r.agent_id)} · model ${esc(r.model || '—')} · ${when(r.started_at)} → ${when(r.completed_at)}<br>${r.sources_examined.length} sources examined · ${r.evidence_created.length} evidence · ${r.candidate_nuggets_created.length} candidates · tokens ${esc(JSON.stringify(r.token_usage))} · cost $${r.cost}${r.notes ? `<div class="muted">${esc(r.notes)}</div>` : ''}${r.errors.length ? `<div class="quote">${esc(r.errors.join('\n'))}</div>` : ''}</div>`).join('') || '<div class="empty">Not run yet.</div>'}
  <h2>Sources discovered</h2>${d.sources_discovered.length ? `<table><tr><th>Source</th><th>Type</th><th>Authority</th></tr>${d.sources_discovered.map((s) => `<tr><td><a href="#/source/${s.id}">${esc(s.title)}</a></td><td>${esc(s.source_type)}</td><td class="small">${esc(s.authority_type)}</td></tr>`).join('')}</table>` : '<div class="empty">None recorded.</div>'}`;
}

async function addView() {
  const { scopes } = await api('/scopes');
  const { authorities } = await api('/vocab');
  const scopeSel = (id) => `<select id="${id}">${scopes.map((s) => `<option value="${s.scope_type}|${esc(s.scope_id)}">${esc(s.name)} (${s.scope_type.toLowerCase().replace('_', ' ')})</option>`).join('')}</select>`;
  const authSel = (id, def) => `<select id="${id}">${authorities.map((a) => `<option ${a === def ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select>`;
  return `<div class="crumbs">Knowledge</div><h1>Add knowledge</h1><p class="sub">Upload · Paste · Write · Link · Connect. Everything lands as raw, immutable source material and becomes candidate nuggets for governance — nothing is active until approved.</p>
  <div class="grid2">
    <div class="card"><h3>Upload</h3><label>File (PDF, Word, PowerPoint, spreadsheet, Markdown, text)</label><input type="file" id="up-file"><label>Scope</label>${scopeSel('up-scope')}<label>Authority</label>${authSel('up-auth', 'Project Documentation')}<div class="actions"><button class="primary" data-act="upload">Upload & extract</button></div></div>
    <div class="card"><h3>Paste</h3><label>Title</label><input id="pa-title" value="Pasted text"><label>Text or Markdown</label><textarea id="pa-text"></textarea><label>Scope</label>${scopeSel('pa-scope')}<label>Authority</label>${authSel('pa-auth', 'User Knowledge')}<div class="actions"><button class="primary" data-act="paste">Paste & extract</button></div></div>
    <div class="card"><h3>Write a note</h3><label>Title</label><input id="no-title" value="Note"><label>Note</label><textarea id="no-text" placeholder="Refunds above $1,000 require manager approval at this store."></textarea><label>Scope</label>${scopeSel('no-scope')}<div class="actions"><button class="primary" data-act="note">Save & extract</button></div></div>
    <div class="card"><h3>Link</h3><label>URL (web page, GitHub, documentation)</label><input id="li-url" placeholder="https://…"><label>Scope</label>${scopeSel('li-scope')}<label>Authority</label>${authSel('li-auth', 'External Reference')}<div class="actions"><button class="primary" data-act="link">Fetch & extract</button></div></div>
  </div><div id="add-result"></div>`;
}


const scopeOptions = (scopes, selected = '') => scopes.map((s) => `<option value="${s.scope_type}|${esc(s.scope_id)}" ${`${s.scope_type}|${s.scope_id}` === selected ? 'selected' : ''}>${esc(s.name)} · ${s.scope_type.toLowerCase().replace('_', ' ')}</option>`).join('');

/* TAB 1 — Add knowledge: Upload / Paste / Write / Link, plus Research and Correct (the other two channels). */
async function addView() {
  const { scopes } = await api('/scopes');
  const { authorities } = await api('/vocab');
  const scopeSel = (id) => `<select id="${id}">${scopeOptions(scopes)}</select>`;
  const authSel = (id, def) => `<select id="${id}">${authorities.map((a) => `<option ${a === def ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select>`;
  return `<div class="crumbs">1 · Add knowledge</div><h1>Add knowledge</h1>
  <p class="sub">Add content; the engine extracts candidate nuggets, resolves them against existing knowledge (duplicates, contradictions, specializations), and suggests a scope. Candidates then wait in <a href="#/nuggets">Knowledge nuggets</a> to be applied.</p>
  <div class="grid2">
    <div class="card"><h3>Upload</h3><label>File (PDF, Word, PowerPoint, spreadsheet, Markdown, text)</label><input type="file" id="up-file"><label>Scope</label>${scopeSel('up-scope')}<label>Authority</label>${authSel('up-auth', 'Project Documentation')}<div class="actions"><button class="primary" data-act="upload">Upload & resolve</button></div></div>
    <div class="card"><h3>Paste</h3><label>Title</label><input id="pa-title" value="Pasted text"><label>Text or Markdown</label><textarea id="pa-text"></textarea><label>Scope</label>${scopeSel('pa-scope')}<label>Authority</label>${authSel('pa-auth', 'User Knowledge')}<div class="actions"><button class="primary" data-act="paste">Paste & resolve</button></div></div>
    <div class="card"><h3>Write a note</h3><label>Title</label><input id="no-title" value="Note"><label>Note</label><textarea id="no-text" placeholder="Refunds above $1,000 require manager approval at this store."></textarea><label>Scope</label>${scopeSel('no-scope')}<div class="actions"><button class="primary" data-act="note">Save & resolve</button></div></div>
    <div class="card"><h3>Link</h3><label>URL (web page, GitHub, documentation)</label><input id="li-url" placeholder="https://…"><label>Scope</label>${scopeSel('li-scope')}<label>Authority</label>${authSel('li-auth', 'External Reference')}<div class="actions"><button class="primary" data-act="link">Fetch & resolve</button></div></div>
    <div class="card"><h3>Research</h3><p class="small muted">Research agents gather evidence and propose candidates. They never change knowledge or the graph.</p><label>Scope</label>${scopeSel('rm-scope')}<label>Objective</label><textarea id="rm-obj" placeholder="Research current Visa dispute processing rules and identify anything that conflicts with Merchant Acquiring knowledge."></textarea><label>Questions (one per line)</label><textarea id="rm-q"></textarea><div class="actions"><button class="primary" data-act="mission">Start research</button></div></div>
    <div class="card"><h3>Correct existing knowledge</h3><p class="small muted">What the Enterprise Console sends on "Correct this". Becomes a candidate revision — the graph changes only after approval.</p>
      <label>Nugget ref (or graph element below)</label><input id="co-ref" placeholder="KN-002:v1"><div class="row"><div><label>Graph id</label><input id="co-graph" placeholder="merchant-acquiring"></div><div><label>Element id</label><input id="co-el" placeholder="r.refunds_above_500…"></div></div>
      <label>What is incorrect?</label><input id="co-what"><label>Correct value / meaning</label><textarea id="co-value"></textarea><label>Reason</label><input id="co-reason"><label>Supporting note / URL</label><div class="row"><input id="co-note" placeholder="note"><input id="co-url" placeholder="https://…"></div>
      <label>Scope (optional)</label><select id="co-scope"><option value="">Let the engine suggest</option>${scopeOptions(scopes)}</select><div class="actions"><button class="primary" data-act="correct">Submit correction</button></div></div>
  </div><div id="add-result"></div><div id="co-result"></div>`;
}

/* TAB 2 — Knowledge nuggets: review, resolve, apply to a scope. */
async function nuggetsView(qs) {
  const p = new URLSearchParams(qs || '');
  const view = p.get('view') || 'pending';
  const [{ nuggets }, { scopes }] = await Promise.all([api('/nuggets'), api('/scopes')]);
  const pendingSet = ['PENDING_REVIEW', 'CONFLICT', 'ANALYZED', 'CANDIDATE'];
  const sets = {
    pending: nuggets.filter((n) => pendingSet.includes(n.status) && !n.conflict_open),
    conflicts: nuggets.filter((n) => n.conflict_open || n.status === 'CONFLICT'),
    active: nuggets.filter((n) => n.status === 'ACTIVE'),
    history: nuggets.filter((n) => ['SUPERSEDED', 'REJECTED', 'OBSOLETE', 'ARCHIVED'].includes(n.status)),
    all: nuggets,
  };
  const rows = sets[view] || sets.pending;
  const tab = (k, label) => `<a href="#/nuggets?view=${k}" class="${view === k ? 'active' : ''}">${label} <span class="muted">${sets[k].length}</span></a>`;
  const applyCell = (n) => {
    if (n.conflict_open) return `<a href="#/conflict/${encodeURIComponent(n.ref)}"><button class="primary">Resolve conflict</button></a>`;
    if (!pendingSet.includes(n.status)) return `<a href="#/nugget/${encodeURIComponent(n.ref)}">Details</a>`;
    return `<div class="row"><select class="apply-scope">${scopeOptions(scopes, n.scope.replace(':', '|'))}</select><button class="primary" data-act="apply" data-ref="${esc(n.ref)}">Apply</button><button data-act="decide" data-ref="${esc(n.ref)}" data-outcome="REJECT">Reject</button></div>
            <label class="small" style="text-transform:none;letter-spacing:0"><input type="checkbox" class="widen" style="width:auto"> widen visibility if the new scope needs it</label>
            ${n.suggested_resolution ? `<div class="small muted">Suggested: ${esc(n.suggested_resolution)}</div>` : ''}`;
  };
  return `<div class="crumbs">2 · Knowledge nuggets</div><h1>Knowledge nuggets</h1>
  <p class="sub">Candidates extracted from your content. <b>Apply</b> approves a nugget at the chosen scope — domain, instance or parent domain — makes it the active governed version, and compiles it into that scope's graph through a Graph Change Proposal. Nothing is applied without this step.</p>
  <div class="tabs">${tab('pending', 'Pending')}${tab('conflicts', 'Conflicts')}${tab('active', 'Active')}${tab('history', 'History')}${tab('all', 'All')}</div>
  ${rows.length ? `<table><tr><th>Nugget</th><th>Statement</th><th>Current scope</th><th>Status</th><th>Authority</th><th style="min-width:340px">Apply to</th></tr>${rows.map((n) =>
    `<tr><td><a href="#/nugget/${encodeURIComponent(n.ref)}">${esc(n.ref)}</a><div class="small muted">${esc(n.title)}</div></td><td>${esc(n.statement)}<div class="small muted">${esc(n.knowledge_type)} · ${esc(n.channel.toLowerCase())}</div></td>
     <td>${scopePill(n.scope)}</td><td>${pill(n.status)}${n.conflict_open ? ' ' + pill('conflict', 'halt') : ''}</td><td class="small">${esc(n.authority)}</td><td>${applyCell(n)}</td></tr>`).join('')}</table>` : '<div class="empty">Nothing here. <a href="#/add">Add knowledge</a> to create candidates.</div>'}
  <div id="apply-result"></div>`;
}

/* TAB 3 — Browse by scope: pull nuggets for a domain / instance / parent domain, inherited and own. */
async function browseView(qs) {
  const p = new URLSearchParams(qs || '');
  const { scopes } = await api('/scopes');
  const sel = p.get('scope') || (scopes.find((s) => s.scope_type === 'DOMAIN') ? `DOMAIN|${scopes.find((s) => s.scope_type === 'DOMAIN').scope_id}` : (scopes[0] ? `${scopes[0].scope_type}|${scopes[0].scope_id}` : ''));
  const q = p.get('q') || '';
  const types = ['STRUCTURE', 'PARENT_DOMAIN', 'DOMAIN', 'INSTANCE'];
  const typeFilter = p.get('type') || '';
  let body = '';
  if (typeFilter) {
    const hits = (await api(`/search?q=${encodeURIComponent(q)}&filter=${encodeURIComponent({ STRUCTURE: 'Structure', PARENT_DOMAIN: 'Domain', DOMAIN: 'Domain', INSTANCE: 'Instance' }[typeFilter])}`)).hits
      .filter((h) => h.kind === 'nugget' && h.scope.startsWith(typeFilter + ':'));
    body = `<h2>All ${typeFilter.toLowerCase().replace('_', ' ')} knowledge <span class="muted">${hits.length}</span></h2>${hits.length ? `<table><tr><th>Nugget</th><th>Statement</th><th>Scope</th><th>Status</th></tr>${hits.map((h) => `<tr><td><a href="#/nugget/${encodeURIComponent(h.id)}">${esc(h.id)}</a></td><td>${esc(h.snippet)}</td><td>${scopePill(h.scope)}</td><td>${pill(h.status)}</td></tr>`).join('')}</table>` : '<div class="empty">No knowledge at this level.</div>'}`;
  } else if (sel) {
    const [t, id] = sel.split('|');
    const d = await api(`/scopes/${t}/${encodeURIComponent(id)}/dashboard`);
    const filt = (rows) => q ? rows.filter((n) => (n.statement + ' ' + n.title).toLowerCase().includes(q.toLowerCase())) : rows;
    const { nuggets } = await api(`/scopes/${t}/${encodeURIComponent(id)}/knowledge`);
    const { sources } = await api(`/scopes/${t}/${encodeURIComponent(id)}/sources`);
    const { missions } = await api(`/research/missions?scope_type=${t}&scope_id=${encodeURIComponent(id)}`);
    const isInst = t === 'INSTANCE';
    body = `
      ${isInst ? `<h2>Inherited from parents</h2>${nuggetRows(filt(d.inherited))}<h2>Instance-specific</h2>${nuggetRows(filt(d.instance_specific))}<h2>Overrides</h2>${nuggetRows(filt(d.overrides))}${d.extensions.length ? `<h2>Extensions</h2>${nuggetRows(filt(d.extensions))}` : ''}`
               : `<h2>Active knowledge by area</h2>${Object.entries(d.knowledge_by_graph_group).map(([g, rows]) => filt(rows).length ? `<h3>${esc(g)} <span class="muted">${filt(rows).length}</span></h3>${nuggetRows(filt(rows))}` : '').join('') || '<div class="empty">No active knowledge yet.</div>'}
                  ${d.instances_using.length ? `<h2>Instances inheriting this</h2>${d.instances_using.map((s) => `<a class="pill scope" href="#/browse?scope=${s.scope_type}|${encodeURIComponent(s.scope_id)}">${esc(s.scope_id)}</a> `).join('')}` : ''}`}
      <h2>Pending here <span class="muted">${nuggets.filter((n) => ['PENDING_REVIEW', 'CONFLICT'].includes(n.status)).length}</span></h2>${nuggetRows(filt(nuggets.filter((n) => ['PENDING_REVIEW', 'CONFLICT'].includes(n.status))), (n) => n.conflict_open ? `<a href="#/conflict/${encodeURIComponent(n.ref)}">Resolve</a>` : decideBtns(n.ref))}
      <h2>Sources <span class="muted">${sources.length}</span></h2>${sources.length ? `<table><tr><th>Source</th><th>Type</th><th>Authority</th><th>Extraction</th></tr>${sources.map((s) => `<tr><td><a href="#/source/${s.id}">${esc(s.title)}</a></td><td>${esc(s.source_type)}</td><td class="small">${esc(s.authority_type)}</td><td>${pill(s.extraction_status, s.extraction_status === 'EXTRACTED' ? 'ok' : 'warn')}</td></tr>`).join('')}</table>` : '<div class="empty">None.</div>'}
      ${missions.length ? `<h2>Research missions</h2><table><tr><th>Mission</th><th>Objective</th><th>Status</th><th>Candidates</th></tr>${missions.map((m) => `<tr><td><a href="#/mission/${m.mission_id}">${m.mission_id}</a></td><td>${esc(m.objective)}</td><td>${pill(m.status)}</td><td class="num">${m.candidate_refs.length}</td></tr>`).join('')}</table>` : ''}`;
  } else body = '<div class="empty">No scopes registered yet — register one on the Dashboard.</div>';
  return `<div class="crumbs">3 · Browse by scope</div><h1>Browse knowledge</h1><p class="sub">Pull the knowledge nuggets of one domain, instance or parent domain — what it holds itself and what it inherits.</p>
  <div class="row"><div><label>Scope</label><select id="br-scope">${scopeOptions(scopes, sel)}</select></div><div><label>Filter text</label><input id="br-q" value="${esc(q)}" placeholder="refund, approval, KYC…"></div><button class="primary" data-act="browse">Show</button></div>
  <div class="filters">${types.map((t) => `<button class="${typeFilter === t ? 'on' : ''}" data-act="browse-type" data-t="${t}">All ${t.toLowerCase().replace('_', ' ')}s</button>`).join('')}<button class="${!typeFilter ? 'on' : ''}" data-act="browse-type" data-t="">One scope</button></div>${body}`;
}

/* TAB 4 — Dashboard: status of the knowledge acquisition engine. */
async function dashboard() {
  const d = await api('/dashboard');
  const n = d.nuggets, g = d.graph, q = d.queues, a = d.attention;
  const kv = (obj) => Object.keys(obj).length ? `<table>${Object.entries(obj).sort((x, y) => y[1] - x[1]).map(([k, v]) => `<tr><td>${pill(k)}</td><td class="num">${v}</td></tr>`).join('')}</table>` : '<div class="empty">—</div>';
  return `<div class="crumbs">4 · Dashboard</div><h1>Knowledge acquisition engine</h1>
  <p class="sub">Acquire → Govern → Know → Compile → Graph → Operate → Observe/Correct. Provider <b>${esc(d.provider)}</b> · adapter <b>${esc(d.adapter)}</b> · storage <span class="mono">${esc(d.storage)}</span></p>
  <div class="tiles">
    <div class="tile"><div class="k">Sources</div><div class="v">${d.sources.total}</div></div>
    <div class="tile"><div class="k">Nuggets (all versions)</div><div class="v">${n.total}</div></div>
    <div class="tile ok"><div class="k">Active</div><div class="v">${n.by_status.ACTIVE || 0}</div></div>
    <div class="tile ${q.pending_governance ? 'warn' : ''}"><div class="k">Pending</div><div class="v">${q.pending_governance}</div></div>
    <div class="tile ${q.conflicts ? 'halt' : ''}"><div class="k">Conflicts</div><div class="v">${q.conflicts}</div></div>
    <div class="tile ${q.graph_impact ? 'warn' : ''}"><div class="k">Awaiting propagation</div><div class="v">${q.graph_impact}</div></div>
    <div class="tile ${q.failed_propagation ? 'halt' : ''}"><div class="k">Failed propagation</div><div class="v">${q.failed_propagation}</div></div>
    <div class="tile"><div class="k">Graph elements with lineage</div><div class="v">${g.elements_with_lineage}</div></div>
    <div class="tile"><div class="k">Research runs</div><div class="v">${d.research.runs}</div></div>
    <div class="tile"><div class="k">Research cost</div><div class="v">$${d.research.cost_usd}</div></div>
    <div class="tile ${d.corrections.pending ? 'warn' : ''}"><div class="k">Corrections pending</div><div class="v">${d.corrections.pending}</div></div>
    <div class="tile ${q.promotions ? 'warn' : ''}"><div class="k">Promotion proposals</div><div class="v">${q.promotions}</div></div>
  </div>
  <h2>Scopes</h2><table><tr><th>Scope</th><th>Type</th><th class="num">Active</th><th class="num">Pending</th></tr>${d.scopes.map((s) => `<tr><td><a href="#/browse?scope=${s.scope_type}|${encodeURIComponent(s.scope_id)}">${esc(s.name)}</a></td><td>${scopePill(s.scope_type)}</td><td class="num">${s.active}</td><td class="num">${s.pending}</td></tr>`).join('')}</table>
  <div class="card" style="margin-top:12px"><h3>Register a scope</h3><div class="row"><div><label>Type</label><select id="sc-type"><option>STRUCTURE</option><option>PARENT_DOMAIN</option><option selected>DOMAIN</option><option>INSTANCE</option></select></div><div><label>Id</label><input id="sc-id" placeholder="merchant-acquiring"></div><div><label>Name</label><input id="sc-name" placeholder="Merchant Acquiring"></div><div><label>Parent (key)</label><input id="sc-parent" placeholder="PARENT_DOMAIN:payment-processing"></div><button class="primary" data-act="register-scope">Register</button></div></div>
  <div class="grid2">
    <div class="card"><h3>Nuggets by status</h3>${kv(n.by_status)}</div>
    <div class="card"><h3>Active by scope type</h3>${kv(n.active_by_scope_type)}</div>
    <div class="card"><h3>Active by authority</h3>${kv(n.active_by_authority)}</div>
    <div class="card"><h3>By acquisition channel</h3>${kv(n.by_channel)}</div>
    <div class="card"><h3>Graph change proposals</h3>${kv(g.proposals_by_status)}</div>
    <div class="card"><h3>Sources by type</h3>${kv(d.sources.by_type)}</div>
  </div>
  <h2>Needs attention</h2>
  ${a.conflicts.length ? `<h3>Conflicts</h3>${nuggetRows(a.conflicts, (x) => `<a href="#/conflict/${encodeURIComponent(x.ref)}">Resolve</a>`)}` : ''}
  ${a.pending_governance.length ? `<h3>Pending governance</h3>${nuggetRows(a.pending_governance, (x) => decideBtns(x.ref))}` : ''}
  ${(a.graph_impact.length || a.failed_propagation.length) ? `<h3>Graph change proposals waiting</h3>${proposalRows([...a.graph_impact, ...a.failed_propagation])}` : ''}
  ${a.promotions.length ? `<h3>Promotion proposals</h3><table><tr><th>Statement</th><th>Target</th><th>Instances</th><th></th></tr>${a.promotions.map((p) => `<tr><td>${esc(p.statement)}</td><td>${scopePill(p.target_scope.scope_type + ':' + p.target_scope.scope_id)}</td><td>${p.instance_ids.join(', ')}</td><td class="actions"><button class="primary" data-act="promote" data-id="${p.id}" data-approve="1">Promote</button><button data-act="promote" data-id="${p.id}" data-approve="0">Reject</button></td></tr>`).join('')}</table>` : ''}
  ${a.acquisition_requests.length ? `<h3>Graph gaps reported by the runtime</h3><table><tr><th>Scope</th><th>Question</th><th>Gap</th></tr>${a.acquisition_requests.map((r) => `<tr><td>${scopePill(r.scope.scope_type + ':' + r.scope.scope_id)}</td><td>${esc(r.question)}</td><td>${esc(r.gap_description)}</td></tr>`).join('')}</table>` : ''}
  ${!Object.values(q).some((v) => v) ? '<div class="empty">All queues are empty.</div>' : ''}
  <div class="actions"><button data-act="detect-promotions">Detect repeated instance patterns</button></div>
  <h2>Recent activity</h2>${auditTable(d.recent_audit.slice().reverse())}
  <h2>Recent events</h2><table><tr><th>When</th><th>Event</th><th>Ids</th></tr>${d.recent_events.map((e) => `<tr><td class="small">${when(e.at)}</td><td class="mono">${esc(e.name)}</td><td class="small muted">${esc(Object.entries(e).filter(([k]) => !['event_id', 'name', 'at'].includes(k)).map(([k, v]) => `${k}=${v}`).join(' '))}</td></tr>`).join('')}</table>`;
}


/* TAB 5 — Images: paste screenshots, get "image #N" to cite in conversation. */
async function imagesView(qs) {
  const p = new URLSearchParams(qs || '');
  const focus = parseInt(p.get('image') || '0', 10);
  const { images } = await api('/images');
  const card = (r) => `<div class="card img-card ${r.number === focus ? 'focus' : ''}" id="image-${r.number}">
    <div class="row" style="align-items:center"><h3 style="margin:0;flex:1">image #${r.number}</h3>${r.width ? `<span class="small muted" style="flex:0 0 auto">${r.width}×${r.height} · ${(r.bytes / 1024).toFixed(0)} KB</span>` : `<span class="small muted" style="flex:0 0 auto">${(r.bytes / 1024).toFixed(0)} KB</span>`}</div>
    <a href="${API}/images/${r.number}" target="_blank"><img src="${API}/images/${r.number}" alt="image #${r.number}" style="max-width:100%;max-height:360px;border:1px solid var(--rule);border-radius:6px;margin:8px 0;display:block"></a>
    <input class="img-caption" data-n="${r.number}" value="${esc(r.caption)}" placeholder="Caption (what to look at)">
    <div class="small muted" style="margin-top:6px">${esc(r.name)} · ${when(new Date(r.created_at * 1000).toISOString())}<br><span class="mono">${esc(r.path)}</span></div>
    <div class="actions"><button data-act="copy" data-text="image #${r.number}">Copy “image #${r.number}”</button><button data-act="copy" data-text="${esc(r.path)}">Copy path</button><button data-act="copy" data-text="${location.origin}/console/#/images?image=${r.number}">Copy link</button><button class="danger" data-act="img-delete" data-n="${r.number}">Delete</button></div></div>`;
  setTimeout(() => { const z = $('#paste-zone'); if (z) z.focus(); const f = $(`#image-${focus}`); if (f) f.scrollIntoView({ block: 'center' }); }, 0);
  return `<div class="crumbs">5 · Images</div><h1>Images</h1>
  <p class="sub">Paste a screenshot here (Ctrl+V, ⌘V on a Mac), drop it, or choose a file. Each one gets a number you can cite in conversation — “look at image #3” — and whoever helps opens it by its server path. Deleted numbers are never reused. Images are not knowledge and never enter governance.</p>
  <div id="paste-zone" class="empty" tabindex="0" style="outline:none;cursor:text;padding:32px">Click here, then paste · or drop images · <label style="display:inline;text-transform:none;letter-spacing:0;font-size:inherit;color:var(--accent);cursor:pointer">choose files<input type="file" id="img-files" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden></label>
    <div class="small muted" style="margin-top:8px">PNG, JPEG, WebP or GIF, up to 10 MB each.</div></div>
  <label>Caption for the next image (optional)</label><input id="img-next-caption" placeholder="e.g. Nuggets tab — Apply button misaligned">
  <div id="img-status" class="small muted" style="margin:8px 0"></div>
  <div id="img-grid">${images.length ? images.map(card).join('') : '<div class="empty">No images yet. Paste one with Ctrl+V.</div>'}</div>`;
}

async function addImages(files) {
  const list = [...files].filter((f) => f && f.type.startsWith('image/'));
  const st = $('#img-status');
  if (!list.length) { if (st) st.textContent = 'Nothing to add: paste or drop an image.'; return; }
  const added = [];
  for (const f of list) {
    try {
      const data = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.onerror = rej; r.readAsDataURL(f); });
      const { image } = await api('/images', { method: 'POST', body: { name: f.name || 'pasted image', caption: $('#img-next-caption')?.value || '', data } });
      added.push(image.number);
    } catch (e) { toast(e.message, true); }
  }
  if (added.length) { toast(`Saved as ${added.map((n) => 'image #' + n).join(', ')} — cite that number in the conversation`); location.hash = `#/images?image=${added[added.length - 1]}`; render(); }
}
document.addEventListener('paste', (e) => {
  if (!location.hash.startsWith('#/images')) return;
  const files = [...(e.clipboardData?.items || [])].filter((i) => i.kind === 'file').map((i) => i.getAsFile());
  if (files.length) { e.preventDefault(); addImages(files); }
});
document.addEventListener('dragover', (e) => { if (location.hash.startsWith('#/images')) e.preventDefault(); });
document.addEventListener('drop', (e) => { if (!location.hash.startsWith('#/images')) return; e.preventDefault(); addImages(e.dataTransfer?.files || []); });
document.addEventListener('change', (e) => { if (e.target && e.target.id === 'img-files') addImages(e.target.files); });
document.addEventListener('change', async (e) => {
  const t = e.target; if (!t || !t.classList.contains('img-caption')) return;
  try { await api(`/images/${t.dataset.n}/caption`, { method: 'POST', body: { caption: t.value } }); toast(`Caption saved for image #${t.dataset.n}`); } catch (err) { toast(err.message, true); }
});

/* ------------------------------------------------------------------ actions */
function bind(root) {
  root.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', (e) => act(e.currentTarget).catch((err) => toast(err.message, true))));
  const q = $('#br-q'); if (q) q.addEventListener('keydown', (e) => { if (e.key === 'Enter') act($('[data-act="browse"]')); });
}
async function act(b) {
  const a = b.dataset.act;
  const reason = () => $('#decide-reason')?.value || $('#rs-reason')?.value || '';
  if (a === 'show') { const t = $('#' + b.dataset.target); t.hidden = !t.hidden; return; }
  if (a === 'decide') {
    const body = { outcome: b.dataset.outcome, by: who(), reason: reason(), existing_ref: b.dataset.existing || null };
    if (b.dataset.outcome === 'MERGE') body.merged_statement = $('#merge-stmt').value;
    if (b.dataset.outcome === 'CHANGE_SCOPE') { body.new_scope_type = $('#rs-type').value; body.new_scope_id = $('#rs-id').value; body.widen_visibility = !!$('#rs-widen')?.checked; }
    const r = await api(`/nugget/${encodeURIComponent(b.dataset.ref)}/decide`, { method: 'POST', body });
    toast(`${r.decision.outcome} → ${r.nugget.status}`);
    if (location.hash.startsWith('#/conflict/')) location.hash = `#/nugget/${encodeURIComponent(b.dataset.ref)}`; else render();
    return;
  }
  if (a === 'prop') { const r = await api(`/graph-changes/${b.dataset.id}/${b.dataset.do}`, { method: 'POST', body: { by: who(), reason: '' } }); toast(`${b.dataset.id}: ${r.execution ? r.execution.status : r.proposal.status}`); render(); return; }
  if (a === 'rollback') { if (!confirm('Roll back this applied change?')) return; await api(`/graph-executions/${b.dataset.id}/rollback`, { method: 'POST', body: { by: who(), reason: 'console rollback' } }); toast('Rolled back'); render(); return; }
  if (a === 'promote') { await api(`/promotions/${b.dataset.id}/decide`, { method: 'POST', body: { approve: b.dataset.approve === '1', by: who(), reason: '' } }); toast('Promotion decided'); render(); return; }
  if (a === 'revise') { const r = await api(`/nuggets/${b.dataset.cid}/propose-revision`, { method: 'POST', body: { statement: $('#rv-stmt').value, by: who(), reason: $('#rv-reason').value } }); toast(`Candidate ${r.candidate.ref} created`); location.hash = `#/nugget/${encodeURIComponent(r.candidate.ref)}`; return; }
  if (a === 'comment') { await api(`/nugget/${encodeURIComponent(b.dataset.ref)}/comment`, { method: 'POST', body: { by: who(), text: $('#cm-text').value } }); toast('Comment added'); render(); return; }
  if (a === 'evidence') {
    const r = await api('/sources/note', { method: 'POST', body: { text: $('#ev-text').value, title: `Evidence for ${b.dataset.ref}`, owner: who(), scope_type: b.dataset.type, scope_id: b.dataset.id, extract: false } });
    toast(`Evidence recorded as source ${r.source.id}`); render(); return;
  }
  if (a === 'compare') { const r = await api(`/nuggets/${b.dataset.cid}/compare?a=${$('#cmp-a').value}&b=${$('#cmp-b').value}`); $('#cmp-out').innerHTML = Object.keys(r.diff).length ? `<table><tr><th>Field</th><th>${r.a}</th><th>${r.b}</th></tr>${Object.entries(r.diff).map(([k, [x, y]]) => `<tr><td>${esc(k)}</td><td class="before">${esc(JSON.stringify(x))}</td><td class="after">${esc(JSON.stringify(y))}</td></tr>`).join('')}</table>` : '<div class="empty">Identical.</div>'; return; }
  if (a === 'mission') { const [st, sid] = $('#rm-scope').value.split('|'); const r = await api('/research/missions', { method: 'POST', body: { scope_type: st, scope_id: sid, objective: $('#rm-obj').value, questions: $('#rm-q').value.split('\n').filter(Boolean), by: who() } }); toast(`Mission ${r.mission.status}: ${r.mission.candidate_refs.length} candidates`); location.hash = `#/mission/${r.mission.mission_id}`; return; }
  if (a === 'apply') {
    const [st, sid] = b.closest('tr').querySelector('.apply-scope').value.split('|');
    const widen = !!b.closest('tr').querySelector('.widen')?.checked;
    const r = await api(`/nugget/${encodeURIComponent(b.dataset.ref)}/apply`, { method: 'POST', body: { by: who(), scope_type: st, scope_id: sid, widen_visibility: widen } });
    toast(r.applied ? `Applied ${r.nugget.ref} at ${r.nugget.scope}` : `Not applied: ${r.note}`, !r.applied);
    const out = $('#apply-result'); if (out) out.innerHTML = `<div class="card"><h3>${r.applied ? 'Applied' : 'Not applied'} — <a href="#/nugget/${encodeURIComponent(r.nugget.ref)}">${esc(r.nugget.ref)}</a> ${pill(r.nugget.status)} ${scopePill(r.nugget.scope)}</h3>${r.steps.map((s) => `<div class="small">${esc(JSON.stringify(s))}</div>`).join('')}${(r.proposals || []).map((p) => `<div class="small">Graph change <a href="#/change/${p.id}">${p.id}</a> ${pill(p.status)}${p.requires_approval ? ' ' + pill('needs approval', 'warn') : ''} → ${p.affected_element_ids.map(esc).join(', ')}</div>`).join('')}${r.note ? `<div class="quote">${esc(r.note)}</div>` : ''}</div>`;
    setTimeout(render, 600); return;
  }
  if (a === 'copy') { try { await navigator.clipboard.writeText(b.dataset.text); toast(`Copied: ${b.dataset.text}`); } catch { prompt('Copy:', b.dataset.text); } return; }
  if (a === 'img-delete') { if (!confirm(`Delete image #${b.dataset.n}? Its number will not be reused.`)) return; await api(`/images/${b.dataset.n}/delete`, { method: 'POST' }); toast(`Deleted image #${b.dataset.n}`); render(); return; }
  if (a === 'browse') { location.hash = `#/browse?scope=${encodeURIComponent($('#br-scope').value)}&q=${encodeURIComponent($('#br-q').value)}`; return; }
  if (a === 'browse-type') { const p = new URLSearchParams(location.hash.split('?')[1] || ''); location.hash = `#/browse?scope=${encodeURIComponent($('#br-scope').value)}&q=${encodeURIComponent($('#br-q').value)}&type=${b.dataset.t}`; return; }
  if (a === 'detect-promotions') { const { scopes } = await api('/scopes'); let n = 0; for (const s of scopes.filter((s) => s.scope_type !== 'INSTANCE')) { n += (await api(`/promotions/detect/${s.scope_type}/${encodeURIComponent(s.scope_id)}`, { method: 'POST' })).proposals.length; } toast(`${n} promotion proposal(s)`); render(); return; }
  if (a === 'run-mission') { const r = await api(`/research/missions/${b.dataset.id}/run`, { method: 'POST' }); toast(`Run ${r.run.status}`); render(); return; }
  if (a === 'register-scope') {
    const [pt, pid] = ($('#sc-parent').value || ':').split(':');
    await api('/scopes', { method: 'POST', body: { scope_type: $('#sc-type').value, scope_id: $('#sc-id').value, name: $('#sc-name').value || null, parent_type: pt || null, parent_id: pid || null } });
    toast('Scope registered'); render(); return;
  }
  const split = (id) => { const [t, s] = $('#' + id).value.split('|'); return { scope_type: t, scope_id: s }; };
  const show = (r) => { $('#add-result').innerHTML = `<h2>Ingested: <a href="#/source/${r.source.id}">${esc(r.source.title)}</a> ${pill(r.extraction_status, r.extraction_status === 'EXTRACTED' ? 'ok' : 'warn')} ${r.extraction_note ? `<span class="muted small">${esc(r.extraction_note)}</span>` : ''}</h2><h3>Resolved into ${r.candidates.length} candidate nugget(s)</h3>${nuggetRows(r.candidates, (n) => n.conflict_open ? `<a href="#/conflict/${encodeURIComponent(n.ref)}">Resolve conflict</a>` : pill(n.status))}<p><a href="#/nuggets"><button class="primary">Go to Knowledge nuggets to apply them →</button></a></p>`; bind($('#add-result')); toast(`${r.candidates.length} candidate nuggets`); };
  if (a === 'upload') { const f = $('#up-file').files[0]; if (!f) throw new Error('Choose a file'); const fd = new FormData(); fd.append('file', f); const s = split('up-scope'); fd.append('scope_type', s.scope_type); fd.append('scope_id', s.scope_id); fd.append('owner', who()); fd.append('authority', $('#up-auth').value); show(await form('/sources/upload', fd)); return; }
  if (a === 'paste') { show(await api('/sources/paste', { method: 'POST', body: { text: $('#pa-text').value, title: $('#pa-title').value, owner: who(), ...split('pa-scope'), authority: $('#pa-auth').value, markdown: $('#pa-text').value.trimStart().startsWith('#') } })); return; }
  if (a === 'note') { show(await api('/sources/note', { method: 'POST', body: { text: $('#no-text').value, title: $('#no-title').value, owner: who(), ...split('no-scope') } })); return; }
  if (a === 'link') { show(await api('/sources/link', { method: 'POST', body: { url: $('#li-url').value, owner: who(), ...split('li-scope'), authority: $('#li-auth').value } })); return; }
  if (a === 'correct') {
    const f = $('#co-file').files[0];
    let r;
    const sc = $('#co-scope').value ? $('#co-scope').value.split('|') : [null, null];
    if (f) { const fd = new FormData(); fd.append('file', f); for (const [k, v] of Object.entries({ graph_id: $('#co-graph').value, element_id: $('#co-el').value, nugget_ref: $('#co-ref').value, what_is_incorrect: $('#co-what').value, correct_value: $('#co-value').value, reason: $('#co-reason').value, by: who() })) if (v) fd.append(k, v); r = await form('/corrections/upload', fd); }
    else r = await api('/corrections', { method: 'POST', body: { graph_id: $('#co-graph').value || null, element_id: $('#co-el').value || null, nugget_ref: $('#co-ref').value || null, what_is_incorrect: $('#co-what').value, correct_value: $('#co-value').value, reason: $('#co-reason').value, comments: $('#co-comments').value || null, by: who(), note: $('#co-note').value || null, url: $('#co-url').value || null, suggested_scope_type: sc[0], suggested_scope_id: sc[1] } });
    const c = r.correction;
    $('#co-result').innerHTML = `<div class="card"><h3>Correction ${c.id} — ${pill(c.status)}</h3><dl class="kv"><dt>Resolved lineage</dt><dd>${c.resolved_lineage.map((x) => `<a href="#/nugget/${encodeURIComponent(x)}">${esc(x)}</a>`).join(', ') || 'none (new knowledge)'}</dd><dt>Suggested scope</dt><dd>${scopePill(c.suggested_scope.scope_type + ':' + c.suggested_scope.scope_id)} <span class="small muted">${esc(c.scope_rationale)}</span></dd><dt>Candidate</dt><dd><a href="#/nugget/${encodeURIComponent(c.candidate_ref)}">${esc(c.candidate_ref)}</a> — awaiting governance</dd></dl></div>`;
    toast('Correction submitted to governance'); return;
  }
}
