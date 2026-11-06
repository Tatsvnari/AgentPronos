// Renders the research record from status.json (rebuilt from the ledger on every publish) and keeps it current.
import { buildTree } from "./tree.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const fmt = n => n == null ? "—" : Number(n).toLocaleString("en-US");
const ago = ts => { if (!ts) return "never"; const s = Date.now() / 1000 - ts; return s < 90 ? "just now" : s < 5400 ? Math.round(s / 60) + " minutes ago" : s < 129600 ? Math.round(s / 3600) + " hours ago" : Math.round(s / 86400) + " days ago"; };
const hm = ts => new Date(ts * 1000).toISOString().slice(11, 16);
const day = ts => new Date(ts * 1000).toISOString().slice(0, 10);
const TAG = l => { const k = /REJECT/.test(l) ? "rej" : /OBSERV|CANDIDATE|STRONG/.test(l) ? "obs" : /SPECUL/.test(l) ? "wait" : "hyp"; return `<span class="tag ${k}">${esc((l || "").toLowerCase())}</span>`; };
let S = null, lastEvent = 0;
const WHO = a => a === "Corbel" ? "Pronos" : a;   // the agent was renamed; entries before the rename say Corbel in the raw record

function state(s) {
  const c = s.counts;
  const row = (k, v) => `<div><span>${k}</span><b>${fmt(v)}</b></div>`;
  $("state").innerHTML = row("Active hypotheses", c.active) + row("Rejected hypotheses", c.rejected) + row("Experiments", c.experiments) +
    row("Independent replications", c.replications) + row("Unresolved contradictions", c.contradictions) + row("Candidate ligands", c.ligands) +
    row("Receipts on the chain", c.receipts) + row("Vault-family proteins in the census", c.proteins) +
    `<div class="last">Last experiment: ${s.last_experiment ? ago(s.last_experiment) : "none yet"}</div>`;
}

function stream(s) {
  const ev = s.events.slice(0, 40);
  $("stream").innerHTML = ev.length ? ev.map((e, i) => `<div class="ev"><span class="t">${hm(e.ts)}<br>${day(e.ts).slice(5)}</span><span><span class="who">${esc(WHO(e.agent))}</span> · ${esc(e.text)}${e.ref ? ` <a class="ref" href="#/r/${esc(e.ref)}">${esc(e.ref)}</a>` : ""}${i === 0 ? ' <span class="cur"></span>' : ""}</span></div>`).join("")
    : `<p class="empty">Nothing has happened yet.</p>`;
  const top = ev[0] ? ev[0].ts : 0;
  if (lastEvent && top > lastEvent) dispatchEvent(new Event("vfs:event"));
  lastEvent = top;
}

const STEP = {discovery: "test", heldout: "hidden", phylo: "per-genus", replication: "replicate"};
function hyps(s) {
  if (!s.hypotheses.length) {
    $("hyps").innerHTML = `<p class="empty">No hypotheses yet. Pronos opens them itself, a question at a time, each with competing answers and at least three frozen predictions.</p>`;
    return;
  }
  const byQ = new Map();
  for (const h of s.hypotheses) { const k = h.question || h.statement; if (!byQ.has(k)) byQ.set(k, []); byQ.get(k).push(h); }
  let html = "";
  for (const [q, hs] of [...byQ.entries()].reverse()) {
    html += `<p class="q">${esc(q)}</p><table><thead><tr><th>ID</th><th>Competing answer</th><th>Steps so far</th><th>Level</th><th class="r">Confidence</th></tr></thead><tbody>${
      hs.map(h => `<tr><td class="m"><a href="#/h/${esc(h.id)}">${esc(h.id)}</a></td><td>${esc(h.statement)}</td><td class="steps">${
        (h.steps || []).map(e => `<a class="${esc(e.status)}" href="#/e/${esc(e.id)}" title="${esc(e.kind)}: ${esc(e.status)}">${esc(STEP[e.kind] || e.kind)} ${e.status === "pass" ? "✓" : e.status === "fail" ? "✗" : "?"}</a>`).join("") || `<span class="dim">${h.branch === "ligand" ? "awaits the L05 map" : "waiting"}</span>`
      }</td><td>${TAG(h.level)}</td><td class="r m"><span class="cbar"><i style="width:${(h.confidence * 100).toFixed(0)}%"></i></span>${h.confidence.toFixed(2)}</td></tr>`).join("")
    }</tbody></table>`;
  }
  $("hyps").innerHTML = `<p>Each question Pronos has asked, with its rival answers. ✓ passed a frozen test, ✗ failed one, ? was inconclusive (usually too little data). Every mark links to its experiment.</p>` + html;
}

function structures(s) {
  const st = s.structures || [];
  if (!st.length) { $("structures").innerHTML = ""; return; }
  const withLig = st.filter(x => JSON.parse(x.ligands || "[]").length);
  $("structures").innerHTML = `<h3>Released vault structures</h3><p>${st.length} entries in the Protein Data Bank carry vault-family domains. None is prokaryotic yet: the L05 phage vault is announced but not released. ${withLig.length} have a small molecule bound. <span class="tag obs">Observation</span></p>
  <table><thead><tr><th>PDB</th><th>Released</th><th>Organism</th><th class="r">Chains</th><th class="r">Res. (Å)</th><th>Bound molecules</th></tr></thead><tbody>${
    st.map(x => { const L = JSON.parse(x.ligands || "[]"); return `<tr><td class="m"><a href="https://www.rcsb.org/structure/${esc(x.id)}" rel="noopener">${esc(x.id)}</a></td><td class="m">${esc(x.released)}</td><td><i>${esc(x.organism)}</i></td><td class="r">${x.chains}</td><td class="r">${x.resolution ?? "—"}</td><td class="m">${L.map(l => `${esc(l.id)}×${l.copies}`).join(", ") || '<span class="dim">none</span>'}</td></tr>`; }).join("")
  }</tbody></table>`;
}

function ligands(s) {
  const head = `<h3>Candidate molecules</h3><p>Ranked by computed evidence only. "Similar to CoA" is fingerprint similarity to coenzyme A, a stand-in for the reported shape resemblance; "seen bound" counts released vault structures carrying the molecule. Fit to the L05 density cannot be measured until its map is public.</p><table><thead><tr><th>Candidate</th><th>Where it came from</th><th class="r">Fit to L05 map</th><th class="r">Similar to CoA</th><th class="r">Size match</th><th class="r">Seen bound</th><th>Evidence</th></tr></thead><tbody>`;
  if (!s.ligands.length) { $("ligands").innerHTML = head + `<tr><td colspan="7" class="dim">No candidates are ranked. Structural fit cannot be scored until the maps are released, and no candidate is privileged before then, including the first one proposed.</td></tr></tbody></table>`; return; }
  const L = s.ligands.map(l => ({...l, sc: JSON.parse(l.score || "{}")})).sort((a, b) => (b.sc.vault_bound > 0) - (a.sc.vault_bound > 0) || (b.sc.chemical || 0) - (a.sc.chemical || 0));
  const n = v => v == null ? '<span class="dim">—</span>' : v.toFixed(2);
  $("ligands").innerHTML = head + L.map(l => `<tr><td>${esc(l.name.length > 48 ? l.name.slice(0, 46) + "…" : l.name)}</td><td>${esc(l.origin)}</td><td class="r dim">awaits map</td><td class="r m">${n(l.sc.chemical)}</td><td class="r m">${n(l.sc.size)}</td><td class="r m">${l.sc.vault_bound ? `${l.sc.vault_bound} (×${l.sc.copies})` : "0"}</td><td>${esc(l.sc.overall || "—")}${l.sc.flags && l.sc.flags.length ? ` <span class="dim">· ${esc(l.sc.flags.join("; "))}</span>` : ""}</td></tr>`).join("") + "</tbody></table>";
}

function bars(items, cls, max) {
  return `<div class="bars">${items.map(([k, v, c]) => `<span>${esc(k)}</span><span class="b ${c || cls}" style="width:${Math.max(0.4, v / max * 100)}%"></span><span class="v">${fmt(v)}</span>`).join("")}</div>`;
}
function census(s) {
  const c = s.census, d = c.by_domain, total = c.total;
  const dc = {Bacteria: "", Archaea: "a", Eukaryota: "e"};
  const doms = ["Bacteria", "Archaea", "Eukaryota", "Viruses"].filter(k => d[k]).map(k => [k, d[k], dc[k]]);
  const pro = c.by_phylum.filter(p => p.domain !== "Eukaryota"), euk = c.by_phylum.filter(p => p.domain === "Eukaryota").slice(0, 8);
  const pmax = Math.max(...c.by_phylum.map(p => p.n));
  const reps = {}; for (const r of c.repeats) { (reps[r.domain] ||= {})[r.repeats] = r.n; }
  const repRows = Object.entries(reps).map(([dom, m]) => `<tr><td>${esc(dom)}</td>${[0,1,2,3,4,5,6,7,8,9].map(k => `<td class="r m">${m[k] ? fmt(m[k]) : '<span class="dim">·</span>'}</td>`).join("")}</tr>`).join("");
  const prok = (d.Bacteria || 0) + (d.Archaea || 0);
  $("census").innerHTML =
    `<p>${fmt(total)} vault-family proteins from ${fmt(c.species)} organisms in ${fmt(c.genera)} genera. ${fmt(prok)} are prokaryotic. UniProtKB holds no phage vault proteins, so phage vaults cannot be counted from it. <span class="tag obs">Observation</span></p>` +
    `<h3>By domain of life</h3>` + bars(doms, "", Math.max(...doms.map(x => x[1]))) +
    `<h3>Prokaryotic phyla</h3>` + bars(pro.map(p => [p.phylum, p.n, p.domain === "Archaea" ? "a" : ""]), "", Math.max(...pro.map(p => p.n), 1)) +
    `<h3>Largest eukaryotic groups</h3>` + bars(euk.map(p => [p.phylum, p.n, "e"]), "e", pmax) +
    `<h3>Annotated MVP repeat domains per protein</h3><table><thead><tr><th>Domain</th>${[0,1,2,3,4,5,6,7,8,9].map(k => `<th class="r">${k}</th>`).join("")}</tr></thead><tbody>${repRows}</tbody></table>` +
    `<p class="dim" style="font:13px var(--sans)">Counts of Pfam repeat-domain annotations, not structural repeat segments: domain annotation misses diverged repeats, so these are lower bounds. The reported L05 wall has seven repeating segments and the mammalian vault nine.</p>` +
    `<p>Prokaryotic genera split ${fmt(c.partition_prokaryote.discovery || 0)} proteins to discovery and ${fmt(c.partition_prokaryote.validation || 0)} to hidden validation.</p>`;
}

function branches(s) {
  const loc = s.census.located, n = s.census.total;
  const NOTE = {
    census: `${fmt(n)} proteins, refreshed from UniProtKB.`,
    architecture: "Pronos compares length, repeat domains and the shoulder domain between prokaryotes and eukaryotes, and between animals and other eukaryotes.",
    structure: `${fmt((s.structures || []).length)} released vault structures catalogued from the PDB, with every bound molecule; checked every six hours for new ones, including the announced L05 phage vault.`,
    ligand: "Candidates for the pocket molecule ranked daily from released structures and PubChem; competing predictions about the pocket are frozen before the L05 map is public.",
    evolution: "Alignment-free sequence similarity (k-mer profiles) across the census: do prokaryotic vaults form their own family, and do they group by phylum?",
    neighbourhoods: `${fmt(loc)} of ${fmt(n)} vault genes are located on their genome records. Analysis of the genes around them is outside this project's scope.`,
    literature: "Mining the published literature for earlier proposals is outside this project's scope; known findings are cited where Pronos's results touch them.",
    handoff: "Opens when a question needs a laboratory.",
  };
  $("branches").innerHTML = s.branches.map(b => `<li><span>${esc(b.name)}</span><span class="tag ${b.status === "running" ? "obs" : "wait"}">${esc(b.status)}</span><span class="note">${NOTE[b.id] || ""}</span></li>`).join("");
}

function list(id, items, emptyText, render) { $(id).innerHTML = items.length ? items.map(render).join("") : `<p class="empty">${emptyText}</p>`; }

function receipts(s) {
  const ch = s.chain;
  $("receipts").innerHTML = `<p>${ch.ok ? `Chain verified: ${fmt(ch.n)} receipts, head <span class="mono">${esc((ch.head || "").slice(0, 16))}</span>.` : `<b>Chain broken at ${esc(ch.broken_at)}.</b>`}</p>` +
    `<table><thead><tr><th>Receipt</th><th>When</th><th>Agent</th><th>Summary</th><th>Level</th></tr></thead><tbody>${
      s.receipts.slice(0, 30).map(r => `<tr><td class="m"><a href="#/r/${esc(r.id)}">${esc(r.id)}</a></td><td class="m">${day(r.ts)}</td><td>${esc(WHO(r.agent))}</td><td>${esc(r.summary)}</td><td>${TAG(r.level)}</td></tr>`).join("")
    }</tbody></table>`;
}

function memoryView(s) {
  const m = s.memory;
  if (!m) { $("memory").innerHTML = ""; return; }
  const asked = new Map((s.hypotheses || []).filter(h => h.question).map(h => [h.question, h]));
  const items = m.tensions.map(t => {
    const p = m.proposals.find(x => x.from_tension === t.id);
    const hs = p ? (s.hypotheses || []).filter(h => h.question === p.text) : [];
    const best = hs.length ? hs.reduce((a, b) => b.confidence > a.confidence ? b : a) : null;
    return `<div class="t"><span class="k">Tension · ${esc(t.id)}</span>${esc(t.text)}${p ? `<br><b>Question it raised:</b> ${esc(p.text)} ${best ? `<br><b>Leading answer so far:</b> <a href="#/h/${esc(best.id)}">${esc(best.statement)}</a> (${esc(best.level.toLowerCase())}, ${best.confidence.toFixed(2)})` : '<span class="dim">(queued; Pronos will freeze its answers and run it)</span>'}` : ""}</div>`;
  }).join("");
  $("memory").innerHTML = `<p class="dim" style="font:13px var(--sans)">${m.counts.findings} findings · ${m.counts.links} links between them · ${m.counts.tensions} tension${m.counts.tensions === 1 ? "" : "s"}. Any agent or model can query it: <span class="mono">python run.py memory recall "&lt;question&gt;"</span>.</p>` + (items ? `<div class="mem">${items}</div>` : "");
}

function render(s) {
  state(s); stream(s); hyps(s); memoryView(s); structures(s); ligands(s); census(s); branches(s); receipts(s);
  list("negatives", s.negatives, "None yet. Negative results will be published here in full, never deleted.", n =>
    `<p><b class="mono">${esc(n.id)}</b> · ${esc(n.hypothesis_id)} · tested: ${esc(n.tested)}. Expected: ${esc(n.expected)}. Actual: ${esc(n.actual)}. <a href="#/e/${esc(n.experiment_id)}">${esc(n.experiment_id)}</a></p>`);
  list("contras", s.contradictions, "None open.", c => `<p><b class="mono">${esc(c.id)}</b> · ${esc(c.hypothesis_id)} · ${esc(c.text)} <span class="tag ${c.status === "open" ? "hyp" : "obs"}">${esc(c.status)}</span></p>`);
  list("memo", s.memos, "The first memo is written after the first night of work.", m => { const b = JSON.parse(m.body); return `<p><span class="mono">${day(m.ts)}</span> · ${b.experiments} experiments, ${b.confidence_moves.length} confidence changes, ${b.open_contradictions.length} open contradictions, ${b.untested.length} frozen predictions still untested.</p>`; });
  list("handoffs", s.handoffs, "None yet.", h => `<p><b class="mono">${esc(h.id)}</b> · ${esc(h.hypothesis_id)}</p>`);
  $("sources").textContent = "Database versions on record: " + (Object.entries(s.sources).map(([k, v]) => k + " " + v).join("; ") || "none") + ".";
  $("updated").textContent = "Pronos is working · record published " + ago(s.generated);
  const ev = s.events[0];
  $("now-text").innerHTML = ev ? `<b>${esc(WHO(ev.agent))}</b> · ${esc(ev.text)} <span class="dim">(${ago(ev.ts)})</span>` : "Nothing yet.";
  buildTree(s.leaves);
  route();
}

/* ---------- permanent pages: #/h/H001, #/e/E001, #/r/R0001 ---------- */
function confSvg(hist) {
  if (!hist.length) return "";
  const W = 640, Hh = 140, t0 = hist[0].ts, t1 = Math.max(hist[hist.length - 1].ts, t0 + 1);
  const x = t => 30 + (t - t0) / (t1 - t0) * (W - 40), y = v => 10 + (1 - v) * (Hh - 30);
  const pts = hist.map(h => `${x(h.ts).toFixed(1)},${y(h.value).toFixed(1)}`).join(" ");
  return `<svg class="conf" viewBox="0 0 ${W} ${Hh}"><line x1="30" x2="${W - 10}" y1="${y(0.5)}" y2="${y(0.5)}" stroke="#dcd8cc"/><text x="0" y="${y(1) + 4}">1.0</text><text x="0" y="${y(0) + 4}">0.0</text><polyline fill="none" stroke="#2f7565" stroke-width="2" points="${pts}"/>${hist.map(h => `<circle cx="${x(h.ts)}" cy="${y(h.value)}" r="3" fill="#2f7565"><title>${h.value.toFixed(2)} · ${esc(h.reason)}</title></circle>`).join("")}</svg>`;
}
function route() {
  if (!S) return;
  const m = location.hash.match(/^#\/([her])\/([A-Z0-9-]+)/), main = $("main"), det = $("detail");
  if (!m) { det.hidden = true; main.hidden = false; return; }
  const [, kind, id] = m; let html = "";
  if (kind === "h") {
    const h = S.hypotheses.find(x => x.id === id);
    html = h ? `<h1 style="text-align:left">${esc(h.id)}</h1><p class="dek">${esc(h.statement)}</p><p>${TAG(h.level)} · confidence <b class="mono">${h.confidence.toFixed(2)}</b> · opened ${day(h.created)} by ${esc(WHO(h.creator))} · branch ${esc(h.branch)}</p>
      <h3>Mechanism</h3><p>${esc(h.mechanism)}</p><h3>Why a vault is necessary</h3><p>${esc(h.why_vault)}</p>${h.inside ? `<h3>Inside the vault</h3><p>${esc(h.inside)}</p>` : ""}${h.consequence ? `<h3>Predicted consequence</h3><p>${esc(h.consequence)}</p>` : ""}
      <h3>Predictions</h3><table><thead><tr><th>ID</th><th>Prediction</th><th>Kind</th><th>Frozen</th><th>Outcome</th></tr></thead><tbody>${h.predictions.map(p => `<tr><td class="m">${esc(p.id)}</td><td>${esc(p.text)}</td><td>${esc(p.kind)}</td><td class="m">${p.frozen_hash ? esc(p.frozen_hash.slice(0, 12)) + "<br>" + day(p.frozen_ts) : '<span class="dim">not yet</span>'}</td><td>${p.outcome ? `<a href="#/r/${esc(p.receipt_id)}">${esc(p.outcome)}</a>` : '<span class="dim">open</span>'}</td></tr>`).join("")}</tbody></table>
      <h3>Confidence over time</h3>${confSvg(h.history)}<table><tbody>${h.history.map(c => `<tr><td class="m">${day(c.ts)} ${hm(c.ts)}</td><td class="m">${c.value.toFixed(2)}</td><td>${esc(c.reason)}</td><td class="m">${c.receipt_id ? `<a href="#/r/${esc(c.receipt_id)}">${esc(c.receipt_id)}</a>` : ""}</td></tr>`).join("")}</tbody></table>
      <h3>Experiments</h3>${S.experiments.filter(e => e.hypothesis_id === id).map(e => `<p><a href="#/e/${esc(e.id)}">${esc(e.id)}</a> · ${esc(e.kind)} · ${esc(e.status)}${e.replication_of ? " · replicates " + esc(e.replication_of) : ""}</p>`).join("") || '<p class="dim">None yet.</p>'}`
      : `<p>No hypothesis ${esc(id)}.</p>`;
  } else if (kind === "e") {
    const e = S.experiments.find(x => x.id === id);
    html = e ? `<h1 style="text-align:left">${esc(e.id)}</h1><p class="dek">${esc(e.question)}</p><p>${esc(e.kind)} · ${esc(e.status)} · ${day(e.created)} · by ${esc(WHO(e.agent))} · tests <a href="#/h/${esc(e.hypothesis_id)}">${esc(e.prediction_id)}</a>${e.replication_of ? ` · replicates <a href="#/e/${esc(e.replication_of)}">${esc(e.replication_of)}</a>` : ""}</p><p>Receipt: <a href="#/r/${esc(e.receipt_id)}">${esc(e.receipt_id)}</a></p>` : `<p>No experiment ${esc(id)}.</p>`;
  } else {
    const r = S.receipts.find(x => x.id === id);
    html = r ? `<h1 style="text-align:left">${esc(r.id)}</h1><p class="dek">${esc(r.question)}</p><p>${TAG(r.level)}</p><div class="receipt">${esc(JSON.stringify(r, null, 1))}</div>` : `<p>Receipt ${esc(id)} is older than the published window.</p>`;
  }
  det.innerHTML = `<a class="back" href="#">← back to the record</a>` + html;
  main.hidden = true; det.hidden = false; scrollTo(0, 0);
}
addEventListener("hashchange", route);

async function load() {
  try { const r = await fetch("status.json", {cache: "no-store"}); if (r.ok) { S = await r.json(); render(S); } }
  catch (e) { $("updated").textContent = "record unavailable"; }
}
// copy the contract address (clipboard API, with a selection fallback for older browsers)
const caBtn = document.getElementById("ca-copy");
if (caBtn) caBtn.addEventListener("click", async () => {
  const v = caBtn.dataset.ca;
  try { await navigator.clipboard.writeText(v); }
  catch (e) { const t = document.createElement("textarea"); t.value = v; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
  caBtn.textContent = "Copied"; caBtn.classList.add("ok");
  setTimeout(() => { caBtn.textContent = "Copy"; caBtn.classList.remove("ok"); }, 1600);
});
load(); setInterval(load, 60000);
