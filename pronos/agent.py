"""Pronos: the autonomous agent. One step per tick, forever.

Its first rung is architecture: before asking what vaults do, establish how vault proteins are built across the tree of life
(length, number of repeat domains, the shoulder domain) and how that differs between prokaryotes and eukaryotes. It never peeks
before it predicts: for every question it writes COMPETING answers (higher / lower / no difference), freezes all their
predictions, and only then looks at data. Each answer then goes through the same steps, picked by expected information gain:

  discovery test (discovery genera only) -> skeptic check -> held-out test (hidden genera) -> one-per-genus test
  -> independent replication (a different statistic, a different seed)

Confidence moves only through loop.py's fixed rule. Nothing here chooses a conclusion."""
from __future__ import annotations

import json
import math
import random
import time

import numpy as np
from scipy import stats as sst

from . import census, evolution, ledger, ligand, loop, memory, structure

AGENT = "Pronos"            # records written before the rename carry its former name, Corbel
PROPS = {"length": "protein length", "repeats": "number of annotated MVP repeat domains", "shoulder": "having a shoulder domain",
         "residual": "chain length beyond what the repeat count predicts"}
SPLITS = {
    "prok_euk": ("prokaryotic", "eukaryotic", lambda r: r["domain"] in ("Bacteria", "Archaea"), lambda r: r["domain"] == "Eukaryota"),
    "metazoa": ("animal", "other eukaryotic", lambda r: r["phylum"] == "Metazoa", lambda r: r["domain"] == "Eukaryota" and r["phylum"] != "Metazoa"),
}
NEGLIGIBLE = 0.147      # |Cliff's delta| below this is a negligible difference (Romano et al. 2006 thresholds)
MIN_N = 5


# ---------------- the question space ----------------
def questions():
    qs = []
    for sp, (a, b, _, _) in SPLITS.items():
        for pr, label in [(k, v) for k, v in PROPS.items() if k != "residual"]:   # residual questions come only from memory
            qs.append({"key": "cmp:%s:%s" % (sp, pr), "split": sp, "prop": pr, "kind": "compare",
                       "text": "Do %s vault proteins differ from %s ones in %s?" % (a, b, label)})
    qs.append({"key": "cor:length:repeats", "prop": "length", "kind": "correlate",
               "text": "Do vault proteins with more repeat domains have longer chains?"})
    qs.append({"key": "nn:separation", "kind": "neighbour", "what": "separation", "prop": "sequence",
               "text": "Do prokaryotic vault proteins resemble each other more than they resemble eukaryotic vault proteins?"})
    qs.append({"key": "nn:coherence", "kind": "neighbour", "what": "coherence", "prop": "sequence",
               "text": "Is a prokaryotic vault protein most similar to vaults from its own phylum, as vertical inheritance predicts?"})
    for m in ledger.kv_get("memory_questions", []):
        qs.append(dict(m))
    return qs


def _answers(q):
    if q["kind"] == "neighbour" and q["what"] == "separation":
        return [("yes", "Prokaryotic vault proteins form their own family: their closest relatives are other prokaryotic vaults.",
                 "Prokaryotic and eukaryotic vaults diverged long ago and stayed apart.", "The two vault lineages evolved separately."),
                ("no", "Prokaryotic vault proteins are no closer to each other than to eukaryotic vaults.",
                 "Vaults moved between prokaryotes and eukaryotes, or diverged too little to separate.", "No lineage split between the two.")]
    if q["kind"] == "neighbour":
        return [("yes", "Prokaryotic vault proteins are most similar to vaults from their own phylum.",
                 "Vault genes were mostly inherited vertically within phyla.", "Vault history tracks the species tree."),
                ("no", "Prokaryotic vault proteins are no more similar within a phylum than across phyla.",
                 "Vault genes moved between phyla (horizontal transfer), or similarity does not resolve phyla.",
                 "Vault history does not track the species tree.")]
    if q["kind"] == "correlate":
        return [("pos", "Vault proteins with more repeat domains are longer: the shell can grow by duplicating wall segments.",
                 "If size changes by duplicating repeating wall segments, chain length should rise with the number of repeats.",
                 "Duplicated repeats lengthen each chain, so the assembled shell is larger and encloses more volume."),
                ("none", "Chain length does not track the number of repeat domains.",
                 "If length is set by other regions (termini, caps, inserts), repeat count would not predict it.",
                 "Shell size would then depend on parts of the chain other than the repeats.")]
    a, b = SPLITS[q["split"]][:2]
    A = a.capitalize()
    more, less = {"residual": ("are longer for their repeat count", "are shorter for their repeat count"),
                  "length": ("are longer", "are shorter"), "repeats": ("carry more repeat domains", "carry fewer repeat domains"),
                  "shoulder": ("more often have a shoulder domain", "less often have a shoulder domain")}[q["prop"]]
    return [("gt", "%s vault proteins %s than %s ones." % (A, more, b),
             "A lineage-specific change in vault architecture.", "The two groups build their shells differently."),
            ("lt", "%s vault proteins %s than %s ones." % (A, less, b),
             "A lineage-specific change in vault architecture.", "The two groups build their shells differently."),
            ("eq", "%s and %s vault proteins do not differ in %s." % (A, b, PROPS[q["prop"]]),
             "A conserved architecture inherited from an ancestral vault.", "The shell is built the same way on both sides of the tree.")]


# ---------------- data ----------------
def _rows():
    return [dict(r) for r in ledger.db().execute("SELECT acc,domain,phylum,genus,length,repeats,shoulder,partition FROM census")]


def _val(r, prop):
    return (1.0 if r["shoulder"] else 0.0) if prop == "shoulder" else float(r[prop])


def _groups(q, partition=None, per_genus=False):
    _, _, fa, fb = SPLITS[q["split"]]
    rows = [r for r in _rows() if partition is None or r["partition"] == partition]
    if q["prop"] == "residual":
        rows = [r for r in rows if r["repeats"] > 0]
        if len(rows) > 2:
            b, a = np.polyfit([r["repeats"] for r in rows], [r["length"] for r in rows], 1)
            for r in rows:
                r["residual"] = r["length"] - (a + b * r["repeats"])
    out = []
    for f in (fa, fb):
        sel = [r for r in rows if f(r)]
        if per_genus:     # one value per genus: the genus median (controls for many relatives counting many times)
            g = {}
            for r in sel:
                g.setdefault(r["genus"], []).append(_val(r, q["prop"]))
            out.append(np.array([float(np.median(v)) for v in g.values()]))
        else:
            out.append(np.array([_val(r, q["prop"]) for r in sel]))
    return out


def cliff(x, y):
    x, y = np.asarray(x), np.asarray(y)
    if not len(x) or not len(y):
        return 0.0
    gt = sum(np.sum(xi > y) for xi in x)
    lt = sum(np.sum(xi < y) for xi in x)
    return float((gt - lt) / (len(x) * len(y)))


def boot_ci(x, y, seed, n=600):
    rng = np.random.default_rng(seed)
    ds = [cliff(rng.choice(x, len(x)), rng.choice(y, len(y))) for _ in range(n)]
    return [round(float(np.percentile(ds, 2.5)), 3), round(float(np.percentile(ds, 97.5)), 3)]


def judge_cmp(ans, x, y, p, d, ci):
    """Fixed pass/fail rule for one comparison answer, written before data was seen (it is part of the frozen test spec)."""
    if len(x) < MIN_N or len(y) < MIN_N:
        return "inconclusive"
    if ans == "gt":
        return "pass" if p < 0.05 and ci[0] > 0 else "fail" if ci[1] < 0 or (p >= 0.05 and abs(d) < NEGLIGIBLE) else "inconclusive"
    if ans == "lt":
        return "pass" if p < 0.05 and ci[1] < 0 else "fail" if ci[0] > 0 or (p >= 0.05 and abs(d) < NEGLIGIBLE) else "inconclusive"
    return "pass" if -0.33 < ci[0] and ci[1] < 0.33 and abs(d) < NEGLIGIBLE else "fail" if ci[0] > NEGLIGIBLE or ci[1] < -NEGLIGIBLE else "inconclusive"


def run_compare(q, ans, partition, per_genus, method, seed):
    x, y = _groups(q, partition, per_genus)
    if len(x) < MIN_N or len(y) < MIN_N:
        return "inconclusive", {"n_a": len(x), "n_b": len(y)}, "Too few proteins in one group (%d vs %d; need %d)." % (len(x), len(y), MIN_N)
    d = cliff(x, y)
    if method == "mann-whitney":
        p = float(sst.mannwhitneyu(x, y, alternative="two-sided").pvalue)
    else:   # permutation of the difference in means, a different statistic on purpose
        rng = np.random.default_rng(seed)
        allv, obs, k = np.concatenate([x, y]), abs(x.mean() - y.mean()), 0
        for _ in range(3000):
            rng.shuffle(allv)
            k += abs(allv[:len(x)].mean() - allv[len(x):].mean()) >= obs
        p = (k + 1) / 3001
    ci = boot_ci(x, y, seed)
    out = judge_cmp(ans, x, y, p, d, ci)
    st = {"n_a": int(len(x)), "n_b": int(len(y)), "median_a": float(np.median(x)), "median_b": float(np.median(y)),
          "mean_a": round(float(x.mean()), 3), "mean_b": round(float(y.mean()), 3), "cliffs_delta": round(d, 3),
          "ci95": ci, "p": float("%.3g" % p), "method": method, "seed": seed, "multiple_testing": "none; one frozen test per prediction"}
    a, b = SPLITS[q["split"]][:2]
    s = ("%s %s: mean %.2f (n=%d) vs %s %.2f (n=%d); Cliff's delta %.2f [%.2f, %.2f], p=%.3g, %s."
         % (a, PROPS[q["prop"]], x.mean(), len(x), b, y.mean(), len(y), d, ci[0], ci[1], p, method))
    return out, st, s


def run_correlate(ans, partition, per_genus, method, seed):
    rows = [r for r in _rows() if (partition is None or r["partition"] == partition) and r["repeats"] > 0]
    if per_genus:
        g = {}
        for r in rows:
            g.setdefault(r["genus"], []).append((r["repeats"], r["length"]))
        pairs = [(float(np.median([a for a, _ in v])), float(np.median([b for _, b in v]))) for v in g.values()]
    else:
        pairs = [(r["repeats"], r["length"]) for r in rows]
    if len(pairs) < 10:
        return "inconclusive", {"n": len(pairs)}, "Too few proteins with annotated repeats (%d)." % len(pairs)
    x, y = np.array([a for a, _ in pairs]), np.array([b for _, b in pairs])
    res = sst.spearmanr(x, y) if method == "spearman" else sst.kendalltau(x, y)
    rho, p = float(res[0]), float(res[1])
    if ans == "pos":
        out = "pass" if p < 0.05 and rho > 0.1 else "fail" if rho <= 0 or (p >= 0.05 and abs(rho) < 0.1) else "inconclusive"
    else:
        out = "pass" if p >= 0.05 and abs(rho) < 0.1 else "fail" if p < 0.05 and abs(rho) >= 0.1 else "inconclusive"
    st = {"n": len(pairs), "rho": round(rho, 3), "p": float("%.3g" % p), "method": method, "excluded": "proteins with no annotated repeats"}
    return out, st, "Length vs repeat count: %s %.2f, p=%.3g, n=%d." % (method, rho, p, len(pairs))


def run_neighbour(q, ans, partition, per_genus, method, seed):
    k = 4 if method == "kmer4" else 3
    m = evolution.measure(q["what"], partition, k, seed or 1, per_genus=per_genus)
    if not m:
        return "inconclusive", {"n_queries": 0}, "Too few prokaryotic proteins in this set to measure."
    lift = m["observed"] - m["chance"]
    if ans == "yes":
        out = "pass" if m["p"] < 0.05 and lift > 0.1 else "fail" if m["p"] >= 0.2 or lift <= 0 else "inconclusive"
    else:
        out = "pass" if m["p"] >= 0.05 and lift < 0.1 else "fail" if m["p"] < 0.05 and lift > 0.1 else "inconclusive"
    what = "nearest other-genus neighbour is prokaryotic" if q["what"] == "separation" else "nearest prokaryotic neighbour shares the phylum"
    m["method"] = method
    return out, m, ("%s: %.0f%% of %d prokaryotic queries (chance %.0f%%), permutation p=%.3g, %d-mer profiles."
                    % (what.capitalize(), m["observed"] * 100, m["n_queries"], m["chance"] * 100, m["p"], k))


# ---------------- the steps ----------------
STEPS = ["discovery", "skeptic", "heldout", "phylo", "replication"]
WEIGHT = {"discovery": 0.6, "skeptic": 0.5, "heldout": 1.0, "phylo": 0.7, "replication": 0.9}


def _state():
    return ledger.kv_get("agent_state", {"asked": [], "steps": {}, "release": ""})


def _save(s):
    ledger.kv_set("agent_state", s)


def ask(q):
    """Write competing answers to a question and freeze all their predictions before any data is looked at."""
    ids = []
    for ans, stmt, mech, cons in _answers(q):
        method = {"correlate": "spearman", "neighbour": "kmer3"}.get(q["kind"], "mann-whitney")
        preds = [
            {"text": "On discovery genera, the %s test agrees: %s" % (method, stmt), "kind": "discovery",
             "test": {"q": q["key"], "ans": ans, "partition": "discovery", "per_genus": False, "method": method}},
            {"text": "On hidden validation genera, never seen before this test: %s" % stmt, "kind": "heldout",
             "test": {"q": q["key"], "ans": ans, "partition": "validation", "per_genus": False, "method": method}},
            {"text": "With one value per genus, so close relatives cannot count many times: %s" % stmt, "kind": "phylo",
             "test": {"q": q["key"], "ans": ans, "partition": "discovery", "per_genus": True, "method": method}},
        ]
        hid = loop.add_hypothesis({"statement": stmt, "mechanism": mech, "why_vault": "Concerns how the vault shell itself is built."
                                   if q["kind"] != "neighbour" else "Concerns where vault proteins came from.",
                                   "consequence": cons, "branch": "evolution" if q["kind"] == "neighbour" else "architecture", "origin": q["key"], "answer": ans,
                                   "question": q["text"], "predictions": preds}, creator=AGENT)
        loop.freeze(hid)
        ids.append(hid)
    ledger.event(AGENT, "ask", "Asked: %s It wrote %d competing answers (%s) and froze their predictions before looking at any data."
                 % (q["text"], len(ids), ", ".join(ids)))
    return ids


def _hyp(hid):
    h = dict(ledger.db().execute("SELECT * FROM hypotheses WHERE id=?", (hid,)).fetchone())
    h["data"] = json.loads(h["data"])
    h["preds"] = {p["kind"]: dict(p) for p in ledger.db().execute("SELECT * FROM predictions WHERE hypothesis_id=?", (hid,))}
    return h


def _q(key):
    return next(q for q in questions() if q["key"] == key)


def _test(h, kind, method=None, seed=None):
    p = h["preds"][kind]
    t = json.loads(p["test"])
    q = _q(t["q"])
    method = method or t["method"]
    seed = seed if seed is not None else 1
    if q["kind"] == "correlate":
        return run_correlate(t["ans"], t["partition"], t["per_genus"], method, seed)
    if q["kind"] == "neighbour":
        return run_neighbour(q, t["ans"], t["partition"], t["per_genus"], method, seed)
    return run_compare(q, t["ans"], t["partition"], t["per_genus"], method, seed)


def step(hid, kind):
    h = _hyp(hid)
    rel = ledger.source_versions().get("UniProtKB", "")
    if kind == "skeptic":
        t = json.loads(h["preds"]["discovery"]["test"])
        q = _q(t["q"])
        notes, confound = [], False
        rows = [r for r in _rows() if r["partition"] == "discovery"]
        if q["kind"] == "compare":
            _, _, fa, fb = SPLITS[q["split"]]
            for name, f in zip(SPLITS[q["split"]][:2], (fa, fb)):
                sel = [r for r in rows if f(r)]
                if sel:
                    top = max(set(r["genus"] for r in sel), key=lambda g: sum(r["genus"] == g for r in sel))
                    share = sum(r["genus"] == top for r in sel) / len(sel)
                    if share > 0.4:
                        confound = True
                        notes.append("%.0f%% of %s discovery proteins come from one genus (%s)" % (share * 100, name, top))
        if q["kind"] == "neighbour":
            pr = [r for r in rows if r["domain"] in ("Bacteria", "Archaea")]
            if pr:
                top = max(set(r["phylum"] for r in pr), key=lambda g: sum(r["phylum"] == g for r in pr))
                share = sum(r["phylum"] == top for r in pr) / len(pr)
                if share > 0.4:
                    notes.append("%.0f%% of prokaryotic discovery proteins are %s, so one phylum carries most of the signal" % (share * 100, top))
                    confound = q["what"] == "coherence"
        if q["prop"] in ("repeats", "residual") or q["kind"] == "correlate":
            z = sum(r["repeats"] == 0 for r in rows) / max(1, len(rows))
            notes.append("%.0f%% of discovery proteins have no annotated repeat domain, so repeat counts are lower bounds" % (z * 100))
        text = ("; ".join(notes) + ".") if notes else "No single genus dominates either group and no annotation gap applies."
        loop.review(hid, {"text": text, "confound": confound}, agent="Skeptic")
        return
    if kind == "replication":
        orig = h["preds"]["discovery"]
        if orig["outcome"] not in ("pass", "fail"):
            ledger.event("Replicator", "skip", "%s: nothing to replicate, the discovery test was inconclusive." % hid)
            return
        t = json.loads(orig["test"])
        alt = {"spearman": "kendall", "kmer3": "kmer4"}.get(t["method"], "permutation")
        out, st, s = _test(h, "discovery", method=alt, seed=random.SystemRandom().randrange(1, 10 ** 6))
        loop.replicate(orig["id"], out if out in ("pass", "fail") else "inconclusive",
                       {"method": alt, "summary": s, "stats": st, "inputs": {"release": rel},
                        "interpretation": "Independent rerun with a different statistic and a fresh random seed."}, agent="Replicator")
        return
    out, st, s = _test(h, kind)
    loop.result(h["preds"][kind]["id"], out, {"method": st.get("method"), "partition": json.loads(h["preds"][kind]["test"])["partition"],
                                             "summary": s, "stats": st, "inputs": {"release": rel, "census_rows": len(_rows())},
                                             "outputs": st, "limitations": "Annotation-based census; repeat counts are Pfam annotations.",
                                             "interpretation": "Frozen rule applied: %s." % out}, agent=AGENT if kind != "heldout" else "Held-out evaluator")


def _entropy(p):
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p)) if 0 < p < 1 else 0.0


def tick():
    """One autonomous step: pick the action with the highest expected information gain per unit cost and do it."""
    s = _state()
    rel = ledger.source_versions().get("UniProtKB", "")
    if s.get("release") and rel and rel != s["release"]:
        ledger.event(AGENT, "snapshot", "New UniProtKB snapshot (%s). Every replication from here on also counts as a new-snapshot rerun." % rel)
    s["release"] = rel
    now = time.time()
    if now - s.get("structure_ts", 0) > 6 * 3600:
        ledger.event("Scheduler", "plan", "Next: Structure Agent checks the PDB for new vault structures (every 6 hours).")
        structure.run()
        s["structure_ts"] = now
        _save(s)
        return "structure"
    if now - s.get("ligand_ts", 0) > 24 * 3600:
        ledger.event("Scheduler", "plan", "Next: Ligand Agent re-ranks pocket candidates from the current structure catalogue (daily).")
        ligand.run()
        ligand.freeze_prospective()
        s["ligand_ts"] = now
        _save(s)
        return "ligand"
    # candidate actions: the next step of every open hypothesis
    cands = []
    for h in ledger.db().execute("SELECT id, confidence, status FROM hypotheses WHERE creator IN (?, 'Corbel') AND status='ACTIVE' "
                                 "AND branch IN ('architecture','evolution')", (AGENT,)):
        done = s["steps"].get(h["id"], [])
        nxt = next((k for k in STEPS if k not in done), None)
        if nxt:
            cands.append((_entropy(h["confidence"]) * WEIGHT[nxt], h["id"], nxt))
    if cands:
        eig, hid, kind = max(cands)
        ledger.event("Scheduler", "plan", "Next: %s on %s (expected information gain %.2f, %d actions open)." % (kind, hid, eig, len(cands)))
        step(hid, kind)
        s["steps"].setdefault(hid, []).append(kind)
        _save(s)
        return "%s %s" % (hid, kind)
    new = [q for q in questions() if q["key"] not in s["asked"]]
    if not new and now - s.get("memory_ts", 0) > 6 * 3600:
        ledger.event("Scheduler", "plan", "Next: memory review. No open questions left, so Pronos re-reads its record for connections and tensions.")
        memory.review()
        s["memory_ts"] = now
        s.pop("rung_done", None)
        _save(s)
        return "memory review"
    if new:
        q = new[0]
        ask(q)
        s["asked"].append(q["key"])
        _save(s)
        return "asked " + q["key"]
    if not s.get("rung_done"):
        ledger.event(AGENT, "idle", "Every architecture question on this rung has been asked and tested. Waiting for a new data snapshot to rerun them.")
        s["rung_done"] = True
        _save(s)
    return "idle"


def run_forever(every=300):
    while True:
        try:
            print(time.strftime("%H:%M:%S"), tick(), flush=True)
            if time.gmtime().tm_hour == 3 and ledger.kv_get("memo_day") != time.strftime("%Y-%m-%d"):
                loop.memo()
                ledger.kv_set("memo_day", time.strftime("%Y-%m-%d"))
        except SystemExit as e:
            ledger.event(AGENT, "refused", "A step was refused by the record's rules: %s" % e)
        except Exception as e:
            ledger.event(AGENT, "error", "A step failed and was logged: %s" % e)
        time.sleep(every)
