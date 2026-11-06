"""Scientific memory: what Pronos knows, how the pieces connect, and where they disagree.

The ledger stays the source of truth. Memory is DERIVED from it and never writes to a hypothesis, prediction, hash or outcome:
it only reads them, and its own output (links, tensions, proposals) is written as new events and as new questions for the agent.
Any model or agent can use it: `run.py memory recall "<text>"` and `run.py memory review`, and the full memory is published in
status.json.

  findings   one per question: the answer the evidence currently favours, plus the answers it rejected
  links      findings that bear on each other (same property in different groups; a property and a correlation that predicts it)
  tensions   two supported findings that, chained together, predict something a third supported finding says is not so
  proposals  for each tension, a new question whose competing answers would resolve it; the agent freezes and runs it
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter

from . import ledger

STRONG = ("SUPPORTED HYPOTHESIS", "CANDIDATE EXPLANATION", "STRONG FUNCTIONAL EXPLANATION")


def _hyps():
    out = []
    for r in ledger.db().execute("SELECT id, statement, level, confidence, status, branch, data FROM hypotheses ORDER BY id"):
        d = json.loads(r["data"] or "{}")
        out.append({"id": r["id"], "statement": r["statement"], "level": r["level"], "confidence": r["confidence"],
                     "status": r["status"], "branch": r["branch"], "key": d.get("origin", ""), "answer": d.get("answer", ""),
                     "question": d.get("question", "")})
    return out


def findings():
    """One entry per question: the leading answer and what it beat."""
    by = {}
    for h in _hyps():
        if h["branch"] not in ("architecture", "evolution") or not h["key"]:
            continue
        by.setdefault(h["key"], []).append(h)
    out = []
    for key, hs in by.items():
        best = max(hs, key=lambda h: h["confidence"])
        parts = key.split(":")
        out.append({"key": key, "question": best["question"], "leader": best["id"], "statement": best["statement"],
                    "answer": best["answer"], "level": best["level"], "confidence": round(best["confidence"], 3),
                    "strong": best["level"] in STRONG, "kind": parts[0], "split": parts[1] if parts[0] == "cmp" else "",
                    "prop": parts[2] if parts[0] == "cmp" else (parts[1] if parts[0] == "cor" else parts[1]),
                    "rejected": [h["id"] for h in hs if h["status"] == "REJECTED"]})
    return out


def links_and_tensions(F):
    links, tensions = [], []
    cmp_ = [f for f in F if f["kind"] == "cmp"]
    # same property, different groups
    for i, a in enumerate(cmp_):
        for b in cmp_[i + 1:]:
            if a["prop"] == b["prop"] and a["split"] != b["split"]:
                links.append({"a": a["key"], "b": b["key"], "why": "same property (%s) compared in different groups" % a["prop"]})
    # a correlation between two properties links every comparison of either property
    for c in [f for f in F if f["kind"] == "cor"]:
        x, y = c["key"].split(":")[2], c["key"].split(":")[1]          # cor:<y>:<x>  e.g. cor:length:repeats
        for f in cmp_:
            if f["prop"] in (x, y):
                links.append({"a": c["key"], "b": f["key"], "why": "%s tracks %s across vault proteins" % (y, x)})
        # chain: a supported difference in x, plus a supported positive x->y link, predicts the same difference in y
        if not (c["strong"] and c["answer"] == "pos"):
            continue
        for fx in cmp_:
            if fx["prop"] != x or not fx["strong"] or fx["answer"] not in ("gt", "lt"):
                continue
            fy = next((f for f in cmp_ if f["split"] == fx["split"] and f["prop"] == y), None)
            if fy and fy["strong"] and fy["answer"] != fx["answer"]:
                tensions.append({
                    "id": "T-%s-%s-%s" % (fx["split"], x, y), "findings": [fx["key"], c["key"], fy["key"]],
                    "text": "%s (%s), and %s (%s), together predict a difference in %s; but %s (%s)."
                            % (fx["statement"].rstrip("."), fx["leader"], c["statement"].split(":")[0].rstrip("."), c["leader"],
                               y, fy["statement"][0].lower() + fy["statement"][1:].rstrip("."), fy["leader"]),
                    "split": fx["split"], "x": x, "y": y, "direction": fx["answer"]})
    return links, tensions


def proposals(T):
    """Each tension becomes a question about the part of y that x does not explain."""
    out = []
    for t in T:
        if (t["x"], t["y"]) == ("repeats", "length"):
            out.append({"key": "cmp:%s:residual" % t["split"], "split": t["split"], "prop": "residual", "kind": "compare",
                        "from_tension": t["id"],
                        "text": "Once repeat count is accounted for, do %s vault proteins have longer or shorter chains than %s ones?"
                                % _names(t["split"])})
    return out


def _names(split):
    from .agent import SPLITS
    return SPLITS[split][0], SPLITS[split][1]


def build():
    F = findings()
    L, T = links_and_tensions(F)
    P = proposals(T)
    asked = set(ledger.kv_get("agent_state", {}).get("asked", []))
    for p in P:
        p["asked"] = p["key"] in asked
    return {"findings": F, "links": L, "tensions": T, "proposals": P,
            "counts": {"findings": len(F), "links": len(L), "tensions": len(T), "open_proposals": sum(not p["asked"] for p in P)}}


def review():
    """The wake-up pass: read everything, report connections and tensions, queue any new question. Evidence is never edited."""
    m = build()
    known = {q["key"] for q in ledger.kv_get("memory_questions", [])}
    new = [p for p in m["proposals"] if p["key"] not in known]
    if new:
        ledger.kv_set("memory_questions", ledger.kv_get("memory_questions", []) + [
            {k: p[k] for k in ("key", "split", "prop", "kind", "text", "from_tension")} for p in new])
    seen = set(ledger.kv_get("memory_seen_tensions", []))
    for t in m["tensions"]:
        if t["id"] not in seen:
            ledger.event("Memory", "tension", "Tension found: " + t["text"])
            seen.add(t["id"])
    ledger.kv_set("memory_seen_tensions", sorted(seen))
    for p in new:
        ledger.event("Memory", "proposal", "Proposed a new question to resolve %s: %s" % (p["from_tension"], p["text"]))
    ledger.event("Memory", "review", "Reviewed the record: %d findings, %d links, %d tensions, %d new questions proposed."
                 % (m["counts"]["findings"], m["counts"]["links"], m["counts"]["tensions"], len(new)))
    ledger.kv_set("memory_reviewed", ledger.now())
    return m


# ---------------- recall: retrieval over the whole record ----------------
_W = re.compile(r"[a-z0-9]+")


def _docs():
    c = ledger.db()
    for r in c.execute("SELECT id, statement, level FROM hypotheses"):
        yield r["id"], "hypothesis", "%s [%s]" % (r["statement"], r["level"].lower())
    for r in c.execute("SELECT id, question, status, result FROM experiments"):
        s = json.loads(r["result"] or "{}").get("summary", "")
        yield r["id"], "experiment", "%s (%s) %s" % (r["question"], r["status"], s)
    for r in c.execute("SELECT id, text FROM contradictions"):
        yield r["id"], "contradiction", r["text"]
    for r in c.execute("SELECT id, summary FROM receipts ORDER BY n DESC LIMIT 400"):
        yield r["id"], "receipt", r["summary"]


def recall(text, k=8):
    docs = list(_docs())
    toks = [Counter(_W.findall(d[2].lower())) for d in docs]
    df = Counter(w for t in toks for w in t)
    n = len(docs) or 1
    q = Counter(_W.findall(text.lower()))
    scored = []
    for d, t in zip(docs, toks):
        s = sum(qv * t[w] * math.log(1 + n / df[w]) for w, qv in q.items() if w in t)
        if s:
            scored.append((s / math.sqrt(sum(t.values())), d))
    return [{"id": d[0], "type": d[1], "text": d[2][:300], "score": round(s, 3)} for s, d in sorted(scored, reverse=True)[:k]]
