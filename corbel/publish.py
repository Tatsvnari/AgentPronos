"""Writes the public feed (status.json) from the ledger. Read-only on the record."""
from __future__ import annotations

import json
import os
import time

from . import census, ledger

BRANCHES = [
    ("census", "Vault census", "running"),
    ("architecture", "How vault proteins are built", "running"),
    ("evolution", "Evolutionary origin", "running"),
    ("structure", "Released vault structures", "running"),
    ("ligand", "Identity of the pocket molecule", "running"),
    ("neighbourhoods", "Genomic neighbourhoods", "out of scope"),
    ("literature", "Map of earlier proposals", "out of scope"),
    ("handoff", "Questions for laboratory researchers", "open"),
]


def rows(sql, *a):
    return [dict(r) for r in ledger.db().execute(sql, a)]


def build():
    c = ledger.db()
    one = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    hyps = rows("SELECT id,statement,mechanism,why_vault,inside,consequence,branch,creator,created,status,level,confidence,data FROM hypotheses ORDER BY id")
    for h in hyps:
        d = json.loads(h.pop("data") or "{}")
        h["question"], h["answer"] = d.get("question", ""), d.get("answer", "")
        h["steps"] = rows("SELECT kind,status,id FROM experiments WHERE hypothesis_id=? ORDER BY created", h["id"])
        h["predictions"] = rows("SELECT id,text,kind,frozen_hash,frozen_ts,outcome,receipt_id FROM predictions WHERE hypothesis_id=? ORDER BY id", h["id"])
        h["history"] = rows("SELECT ts,value,reason,receipt_id FROM confidence WHERE hypothesis_id=? ORDER BY id", h["id"])
        h["support"] = one("SELECT COUNT(*) FROM experiments WHERE hypothesis_id=? AND status='pass'", h["id"])
        h["contra"] = one("SELECT COUNT(*) FROM experiments WHERE hypothesis_id=? AND status='fail'", h["id"])
        h["replications"] = one("SELECT COUNT(*) FROM experiments WHERE hypothesis_id=? AND kind='replication' AND status='pass'", h["id"])
        h["unresolved"] = sum(1 for p in h["predictions"] if not p["outcome"])
    leaves = rows("SELECT acc,organism,domain,phylum,genus,length,repeats,shoulder,partition,nuc FROM census ORDER BY domain,phylum,genus")
    for l in leaves:
        l["located"] = 1 if l.pop("nuc") else 0
    last = c.execute("SELECT created FROM experiments ORDER BY created DESC LIMIT 1").fetchone()
    s = {
        "generated": time.time(),
        "counts": {
            "active": one("SELECT COUNT(*) FROM hypotheses WHERE status='ACTIVE'"),
            "rejected": one("SELECT COUNT(*) FROM hypotheses WHERE status='REJECTED'"),
            "experiments": one("SELECT COUNT(*) FROM experiments"),
            "replications": one("SELECT COUNT(*) FROM experiments WHERE kind='replication'"),
            "contradictions": one("SELECT COUNT(*) FROM contradictions WHERE status='open'"),
            "ligands": one("SELECT COUNT(*) FROM ligands"),
            "receipts": one("SELECT COUNT(*) FROM receipts"),
            "proteins": one("SELECT COUNT(*) FROM census"),
        },
        "last_experiment": last[0] if last else None,
        "events": rows("SELECT ts,agent,kind,text,ref FROM events ORDER BY id DESC LIMIT 200"),
        "hypotheses": hyps,
        "experiments": rows("SELECT id,hypothesis_id,prediction_id,kind,question,status,created,receipt_id,replication_of,agent FROM experiments ORDER BY created DESC LIMIT 300"),
        "negatives": rows("SELECT * FROM negatives ORDER BY ts DESC"),
        "contradictions": rows("SELECT * FROM contradictions ORDER BY ts DESC"),
        "ligands": rows("SELECT id,name,origin,score FROM ligands"),
        "structures": rows("SELECT id,title,method,resolution,released,organism,chains,ligands FROM structures ORDER BY released DESC"),
        "memos": rows("SELECT ts,body FROM memos ORDER BY id DESC LIMIT 7"),
        "handoffs": rows("SELECT * FROM handoffs ORDER BY ts DESC"),
        "receipts": rows("SELECT id,ts,agent,question,hypothesis_id,experiment_id,summary,level,code_hash,input_hash,output_hash,prev_hash,hash FROM receipts ORDER BY n DESC LIMIT 120"),
        "chain": ledger.verify_chain(),
        "sources": ledger.source_versions(),
        "census": census.summary(),
        "leaves": leaves,
        "branches": [{"id": a, "name": b, "status": s_} for a, b, s_ in BRANCHES],
    }
    s["census"]["located"] = sum(l["located"] for l in leaves)
    return s


def write(path):
    s = build()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, separators=(",", ":"), default=str)
    os.replace(tmp, path)
    return s["counts"]
