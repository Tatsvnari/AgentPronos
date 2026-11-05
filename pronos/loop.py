"""The research loop machinery. It holds no biology of its own: researchers add hypotheses and predictions, results and
replications; this module freezes, chains, judges and publishes them.

  hypothesis add  <file.json>         {statement, mechanism, why_vault, inside, consequence, branch, predictions:[{text, kind}]}
  freeze          <H id>              hash the prediction set; nothing can be added to it afterwards
  result          <P id> <pass|fail|inconclusive> <file.json>   {method, inputs, outputs, stats, limitations, interpretation, partition}
  replicate       <P id> <pass|fail> <file.json>                 same fields; must name a different method or data snapshot
  review          <H id> <file.json>  skeptic review {text, confound: true|false}
  handoff         <H id> <file.json>  human research handoff (lab work stays with qualified researchers)
  memo                                synthesis memo (reads only, writes one memo row)
  verify                              recompute the receipt chain

Confidence is computed, never chosen: prior 0.20, then a fixed log-odds step per evidence record (table W). Every change is a
row in `confidence` pointing at the receipt that caused it."""
from __future__ import annotations

import json
import math
import sys
import time

from . import ledger

PRIOR = 0.20
# log-odds step per evidence record: (kind, outcome) -> step
W = {("discovery", "pass"): 0.4, ("discovery", "fail"): -0.6,
     ("heldout", "pass"): 0.8, ("heldout", "fail"): -1.0,
     ("prospective", "pass"): 1.0, ("prospective", "fail"): -1.2,
     ("replication", "pass"): 0.6, ("replication", "fail"): -0.9,
     ("skeptic", "confound"): -0.5}


def _logit(p): return math.log(p / (1 - p))
def _sig(x): return 1 / (1 + math.exp(-x))


def _conf(hid):
    r = ledger.db().execute("SELECT confidence FROM hypotheses WHERE id=?", (hid,)).fetchone()
    return r[0] if r else None


def _move(hid, step, reason, rid):
    c = ledger.db()
    prev = _conf(hid)
    new = round(min(0.99, max(0.01, _sig(_logit(prev) + step))), 4)
    with ledger._LOCK:
        c.execute("UPDATE hypotheses SET confidence=? WHERE id=?", (new, hid))
        c.execute("INSERT INTO confidence(hypothesis_id,ts,value,prev,reason,receipt_id) VALUES(?,?,?,?,?,?)",
                  (hid, ledger.now(), new, prev, reason, rid))
        c.commit()
    ledger.event("Research Judge", "confidence", "%s confidence %.2f -> %.2f (%s)." % (hid, prev, new, reason), rid)
    _status(hid)
    return prev, new


def add_hypothesis(spec: dict, creator="researcher"):
    preds = spec.get("predictions") or []
    if len(preds) < 3:
        raise SystemExit("refused: a hypothesis needs at least three falsifiable predictions (has %d)" % len(preds))
    for k in ("statement", "mechanism", "why_vault"):
        if not spec.get(k):
            raise SystemExit("refused: missing " + k)
    hid = ledger.next_id("H", "hypotheses")
    c = ledger.db()
    with ledger._LOCK:
        c.execute("INSERT INTO hypotheses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (hid, spec["statement"], spec["mechanism"], spec["why_vault"], spec.get("inside", ""), spec.get("consequence", ""),
                   spec.get("branch", "main"), spec.get("origin", ""), creator, ledger.now(), "ACTIVE", "HYPOTHESIS", PRIOR,
                   json.dumps({k: v for k, v in spec.items() if k not in ("predictions",)})))
        for i, p in enumerate(preds, 1):
            c.execute("INSERT INTO predictions(id,hypothesis_id,text,test,kind) VALUES(?,?,?,?,?)",
                      ("%s-P%d" % (hid, i), hid, p["text"], json.dumps(p.get("test", {})), p.get("kind", "discovery")))
        c.execute("INSERT INTO confidence(hypothesis_id,ts,value,prev,reason,receipt_id) VALUES(?,?,?,?,?,?)",
                  (hid, ledger.now(), PRIOR, None, "prior", ""))
        c.commit()
    ledger.node(hid, "Hypothesis", spec["statement"])
    rid = ledger.receipt("Hypothesis desk", "New hypothesis " + hid, spec["statement"], hypothesis_id=hid, inputs=spec,
                         level="HYPOTHESIS", interpretation="Untested explanation; predictions not yet frozen.")
    ledger.event("Hypothesis desk", "hypothesis", "%s opened: %s (%d predictions)." % (hid, spec["statement"], len(preds)), rid)
    return hid


def freeze(hid):
    c = ledger.db()
    preds = c.execute("SELECT id,text,test,kind,frozen_hash FROM predictions WHERE hypothesis_id=? ORDER BY id", (hid,)).fetchall()
    if any(p["frozen_hash"] for p in preds):
        raise SystemExit("already frozen")
    h = ledger.H([[p["id"], p["text"], p["test"], p["kind"]] for p in preds])
    t = ledger.now()
    with ledger._LOCK:
        c.execute("UPDATE predictions SET frozen_hash=?, frozen_ts=? WHERE hypothesis_id=?", (h, t, hid))
        c.commit()
    rid = ledger.receipt("Prediction freeze", "Freeze predictions of " + hid, "%d predictions frozen before any test, sha256 %s"
                         % (len(preds), h[:16]), hypothesis_id=hid, inputs=[dict(p) for p in preds], outputs={"hash": h},
                         level="HYPOTHESIS")
    for p in preds:
        ledger.node(p["id"], "Prediction", p["text"])
        ledger.edge(hid, p["id"], "predicts", rid)
    ledger.event("Prediction freeze", "freeze", "%s: %d predictions frozen, hash %s." % (hid, len(preds), h[:12]), rid)
    return h


def _pred(pid):
    p = ledger.db().execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
    if not p:
        raise SystemExit("no such prediction")
    if not p["frozen_hash"]:
        raise SystemExit("refused: predictions must be frozen before a test is run")
    return p


def result(pid, outcome, rec: dict, agent="researcher"):
    p = _pred(pid)
    hid = p["hypothesis_id"]
    eid = ledger.next_id("E", "experiments")
    rid = ledger.receipt(agent, "Test %s: %s" % (pid, p["text"]), rec.get("summary", outcome), hypothesis_id=hid, experiment_id=eid,
                         inputs=rec.get("inputs"), params={"method": rec.get("method"), "partition": rec.get("partition")},
                         outputs=rec.get("outputs"), stats=rec.get("stats"), limitations=rec.get("limitations", ""),
                         interpretation=rec.get("interpretation", ""), level="OBSERVATION")
    c = ledger.db()
    with ledger._LOCK:
        c.execute("INSERT INTO experiments(id,hypothesis_id,prediction_id,kind,question,spec,status,created,done,receipt_id,result,agent) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (eid, hid, pid, p["kind"], p["text"], json.dumps(rec.get("method")), outcome,
                                                       ledger.now(), ledger.now(), rid, json.dumps(rec), agent))
        c.execute("UPDATE predictions SET outcome=?, outcome_ts=?, receipt_id=? WHERE id=?", (outcome, ledger.now(), rid, pid))
        c.commit()
    ledger.node(eid, "Experiment", p["text"])
    ledger.edge(eid, pid, "tests", rid)
    ledger.edge(eid, hid, "supports" if outcome == "pass" else "contradicts" if outcome == "fail" else "tests", rid)
    ledger.event(agent, "experiment", "%s finished (%s): %s." % (eid, outcome, rec.get("summary", p["text"]).rstrip(".")), rid)
    if outcome == "fail":
        _negative(eid, hid, p, rec)
    if outcome in ("pass", "fail"):
        _move(hid, W[(p["kind"] if p["kind"] in ("discovery", "heldout", "prospective") else "discovery", outcome)],
              "%s %s %s" % (eid, p["kind"], outcome), rid)
    return eid


def replicate(pid, outcome, rec: dict, agent="Replicator"):
    p = _pred(pid)
    orig = ledger.db().execute("SELECT * FROM experiments WHERE prediction_id=? AND replication_of IS NULL ORDER BY created LIMIT 1",
                               (pid,)).fetchone()
    if not orig:
        raise SystemExit("nothing to replicate yet")
    if rec.get("method") == json.loads(orig["spec"] or "null"):
        raise SystemExit("refused: a replication must use a different method, data snapshot or seed")
    hid = p["hypothesis_id"]
    eid = ledger.next_id("E", "experiments")
    rid = ledger.receipt(agent, "Replicate %s (%s)" % (orig["id"], pid), rec.get("summary", outcome), hypothesis_id=hid, experiment_id=eid,
                         inputs=rec.get("inputs"), params={"method": rec.get("method")}, outputs=rec.get("outputs"), stats=rec.get("stats"),
                         limitations=rec.get("limitations", ""), interpretation=rec.get("interpretation", ""),
                         level="REPRODUCED OBSERVATION" if outcome == "pass" else "OBSERVATION")
    c = ledger.db()
    with ledger._LOCK:
        c.execute("INSERT INTO experiments(id,hypothesis_id,prediction_id,kind,question,spec,status,created,done,receipt_id,result,"
                  "replication_of,agent) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (eid, hid, pid, "replication", p["text"], json.dumps(rec.get("method")), outcome, ledger.now(), ledger.now(), rid,
                   json.dumps(rec), orig["id"], agent))
        c.commit()
    ledger.edge(eid, orig["id"], "replicates", rid)
    verdict = ("reproduced" if outcome == orig["status"] else "disagreed with" if outcome in ("pass", "fail") else "could not settle")
    ledger.event(agent, "replication", "%s %s %s (original %s, replication %s)." % (eid, verdict, orig["id"], orig["status"], outcome), rid)
    if outcome in ("pass", "fail"):
        _move(hid, W[("replication", outcome)], "%s replication of %s %s" % (eid, orig["id"], outcome), rid)
    if outcome != orig["status"] and outcome in ("pass", "fail") and orig["status"] in ("pass", "fail"):
        contradiction(hid, orig["receipt_id"], rid, "%s and its replication %s disagree" % (orig["id"], eid))
    return eid


def review(hid, rec: dict, agent="Skeptic"):
    rid = ledger.receipt(agent, "Skeptic review of " + hid, rec["text"], hypothesis_id=hid, inputs=rec, level="INFERENCE",
                         review=rec["text"])
    ledger.event(agent, "review", "Reviewed %s: %s" % (hid, rec["text"]), rid)
    if rec.get("confound"):
        _move(hid, W[("skeptic", "confound")], "skeptic found a confound", rid)
    return rid


def contradiction(hid, a, b, text):
    cid = ledger.next_id("C", "contradictions")
    with ledger._LOCK:
        ledger.db().execute("INSERT INTO contradictions VALUES(?,?,?,?,?,?,?,?,?)",
                            (cid, hid, a, b, text, json.dumps(["lineage difference", "measurement difference", "annotation error",
                                                               "condition difference", "false positive", "false negative"]),
                             "open", ledger.now(), ""))
        ledger.db().commit()
    ledger.node(cid, "Contradiction", text)
    ledger.edge(cid, hid, "contradicts")
    ledger.event("Contradiction engine", "contradiction", "%s opened on %s: %s. Kept visible, not averaged away." % (cid, hid, text))
    return cid


def _negative(eid, hid, p, rec):
    nid = ledger.next_id("N", "negatives")
    with ledger._LOCK:
        ledger.db().execute("INSERT INTO negatives VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (nid, eid, hid, p["text"], rec.get("why", "frozen prediction of " + hid), rec.get("expected", p["text"]),
                             rec.get("summary", "failed"), 1, 1, ledger.now()))
        ledger.db().commit()


def _status(hid):
    """Claim level from fixed rules (spec 31)."""
    c = ledger.db()
    ex = c.execute("SELECT kind,status,replication_of FROM experiments WHERE hypothesis_id=?", (hid,)).fetchall()
    open_c = c.execute("SELECT COUNT(*) FROM contradictions WHERE hypothesis_id=? AND status='open'", (hid,)).fetchone()[0]
    kinds_pass = {e["kind"] for e in ex if e["status"] == "pass"}
    held_fail = any(e["kind"] == "heldout" and e["status"] == "fail" for e in ex)
    rep_fail = any(e["kind"] == "replication" and e["status"] == "fail" for e in ex)
    novelty = json.loads(c.execute("SELECT data FROM hypotheses WHERE id=?", (hid,)).fetchone()[0]).get("novelty", "")
    if held_fail and rep_fail:
        lvl, st = "REJECTED", "REJECTED"
    elif {"heldout", "replication"} <= kinds_pass and len(kinds_pass) >= 3 and not open_c and novelty in ("POSSIBLY NOVEL", "LIKELY NOVEL"):
        # a candidate explanation also needs a novelty check against the literature; without one the level stops at SUPPORTED
        lvl, st = "CANDIDATE EXPLANATION", "ACTIVE"
    elif "heldout" in kinds_pass and "replication" in kinds_pass:
        lvl, st = "SUPPORTED HYPOTHESIS", "ACTIVE"
    else:
        lvl, st = "HYPOTHESIS", "ACTIVE"
    with ledger._LOCK:
        c.execute("UPDATE hypotheses SET level=?, status=? WHERE id=?", (lvl, st, hid))
        c.commit()


def memo():
    """Synthesis: reads the last day, writes one memo. Never edits evidence."""
    c = ledger.db()
    since = time.time() - 86400
    moved = c.execute("SELECT hypothesis_id, MIN(prev) a, MAX(ts), value FROM confidence WHERE ts>? AND prev IS NOT NULL "
                      "GROUP BY hypothesis_id", (since,)).fetchall()
    body = {"since": since, "experiments": c.execute("SELECT COUNT(*) FROM experiments WHERE created>?", (since,)).fetchone()[0],
            "confidence_moves": [dict(r) for r in moved],
            "open_contradictions": [dict(r) for r in c.execute("SELECT id,hypothesis_id,text FROM contradictions WHERE status='open'")],
            "untested": [r[0] for r in c.execute("SELECT id FROM predictions WHERE frozen_hash IS NOT NULL AND outcome IS NULL")],
            "unfrozen": [r[0] for r in c.execute("SELECT DISTINCT hypothesis_id FROM predictions WHERE frozen_hash IS NULL")]}
    with ledger._LOCK:
        c.execute("INSERT INTO memos(ts,body) VALUES(?,?)", (ledger.now(), json.dumps(body)))
        c.commit()
    ledger.event("Synthesis", "memo", "Nightly memo: %d experiments, %d confidence moves, %d open contradictions, %d frozen predictions untested."
                 % (body["experiments"], len(body["confidence_moves"]), len(body["open_contradictions"]), len(body["untested"])))
    return body


def handoff(hid, rec):
    fid = ledger.next_id("L", "handoffs")
    with ledger._LOCK:
        ledger.db().execute("INSERT INTO handoffs VALUES(?,?,?,?)", (fid, hid, json.dumps(rec), ledger.now()))
        ledger.db().commit()
    ledger.event("Handoff desk", "handoff", "%s: question for qualified laboratory researchers on %s." % (fid, hid))
    return fid


def main(a):
    load = lambda f: json.load(open(f))
    cmd = a[0] if a else "help"
    if cmd == "hypothesis" and a[1] == "add":
        print(add_hypothesis(load(a[2])))
    elif cmd == "freeze":
        print(freeze(a[1]))
    elif cmd == "result":
        print(result(a[1], a[2], load(a[3])))
    elif cmd == "replicate":
        print(replicate(a[1], a[2], load(a[3])))
    elif cmd == "review":
        print(review(a[1], load(a[2])))
    elif cmd == "handoff":
        print(handoff(a[1], load(a[2])))
    elif cmd == "memo":
        print(json.dumps(memo(), indent=1))
    elif cmd == "verify":
        print(json.dumps(ledger.verify_chain()))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
