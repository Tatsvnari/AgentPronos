"""The research record. Append-only: evidence is never overwritten, a change is a new row.

Layers (spec 17): events = RAW EVENTS, receipts = EVIDENCE (hash-chained, immutable), hypotheses/predictions/experiments =
HYPOTHESES + WORKING MEMORY, knowledge = rows whose claim level reached SUPPORTED or above. The graph (nodes/edges) ties every
claim back to the receipts it rests on."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import threading
import time

DB_PATH = os.environ.get("VFS_DB", os.path.join(os.path.dirname(__file__), "..", "state", "vault.sqlite"))
_LOCK = threading.RLock()

LEVELS = ["OBSERVATION", "REPRODUCED OBSERVATION", "INFERENCE", "HYPOTHESIS", "SUPPORTED HYPOTHESIS", "SPECULATION",
          "REJECTED", "CANDIDATE EXPLANATION", "STRONG FUNCTIONAL EXPLANATION"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL, agent TEXT, kind TEXT, text TEXT, ref TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS receipts(n INTEGER PRIMARY KEY, id TEXT UNIQUE, ts REAL, agent TEXT, question TEXT, hypothesis_id TEXT,
  experiment_id TEXT, code_hash TEXT, env TEXT, versions TEXT, input_hash TEXT, params TEXT, output_hash TEXT, summary TEXT,
  stats TEXT, limitations TEXT, interpretation TEXT, review TEXT, artifact TEXT, level TEXT, prev_hash TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, type TEXT, label TEXT, data TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS edges(id INTEGER PRIMARY KEY, src TEXT, dst TEXT, rel TEXT, receipt_id TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS hypotheses(id TEXT PRIMARY KEY, statement TEXT, mechanism TEXT, why_vault TEXT, inside TEXT,
  consequence TEXT, branch TEXT, origin TEXT, creator TEXT, created REAL, status TEXT, level TEXT, confidence REAL, data TEXT);
CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY, hypothesis_id TEXT, text TEXT, test TEXT, kind TEXT, frozen_hash TEXT,
  frozen_ts REAL, outcome TEXT, outcome_ts REAL, receipt_id TEXT);
CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, hypothesis_id TEXT, prediction_id TEXT, kind TEXT, question TEXT,
  spec TEXT, status TEXT, created REAL, done REAL, receipt_id TEXT, result TEXT, replication_of TEXT, eig REAL, cost REAL, agent TEXT);
CREATE TABLE IF NOT EXISTS confidence(id INTEGER PRIMARY KEY, hypothesis_id TEXT, ts REAL, value REAL, prev REAL, reason TEXT, receipt_id TEXT);
CREATE TABLE IF NOT EXISTS contradictions(id TEXT PRIMARY KEY, hypothesis_id TEXT, a_receipt TEXT, b_receipt TEXT, text TEXT,
  explanations TEXT, status TEXT, ts REAL, resolved_by TEXT);
CREATE TABLE IF NOT EXISTS negatives(id TEXT PRIMARY KEY, experiment_id TEXT, hypothesis_id TEXT, tested TEXT, why TEXT, expected TEXT,
  actual TEXT, weakened INTEGER, informative INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS ligands(id TEXT PRIMARY KEY, name TEXT, cid INTEGER, origin TEXT, data TEXT, score TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS memos(id INTEGER PRIMARY KEY, ts REAL, body TEXT);
CREATE TABLE IF NOT EXISTS census(acc TEXT PRIMARY KEY, organism TEXT, taxid INTEGER, lineage TEXT, domain TEXT, phylum TEXT, genus TEXT,
  length INTEGER, repeats INTEGER, shoulder INTEGER, pfams TEXT, name TEXT, protein_id TEXT, nuc TEXT, partition TEXT, seq TEXT, release TEXT);
CREATE TABLE IF NOT EXISTS loci(acc TEXT PRIMARY KEY, contig TEXT, start INTEGER, stop INTEGER, strand TEXT, genes TEXT, fetched REAL, status TEXT);
CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, year INTEGER, title TEXT, journal TEXT, abstract TEXT, source TEXT, doi TEXT,
  cats TEXT, claims TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS structures(id TEXT PRIMARY KEY, title TEXT, method TEXT, resolution REAL, released TEXT, organism TEXT,
  chains INTEGER, ligands TEXT, data TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, name TEXT, version TEXT, url TEXT, ts REAL, hash TEXT);
CREATE TABLE IF NOT EXISTS handoffs(id TEXT PRIMARY KEY, hypothesis_id TEXT, body TEXT, ts REAL);
"""


def conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


DB = None


def db():
    global DB
    if DB is None:
        DB = conn()
        DB.executescript(SCHEMA)
        DB.commit()
    return DB


def H(obj) -> str:
    if not isinstance(obj, (bytes, bytearray)):
        obj = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(obj).hexdigest()


def now() -> float:
    return time.time()


def kv_get(key, default=None):
    r = db().execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def kv_set(key, value):
    with _LOCK:
        db().execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, json.dumps(value)))
        db().commit()


def next_id(prefix: str, table: str) -> str:
    with _LOCK:
        k = "seq_" + prefix
        n = kv_get(k, 0) + 1
        kv_set(k, n)
        return "%s%03d" % (prefix, n)


def event(agent: str, kind: str, text: str, ref: str = "", data=None):
    with _LOCK:
        db().execute("INSERT INTO events(ts,agent,kind,text,ref,data) VALUES(?,?,?,?,?,?)",
                     (now(), agent, kind, text, ref, json.dumps(data or {}, default=str)))
        db().commit()


_CODE_HASH = None


def code_hash() -> str:
    """Hash of every engine source file: the receipt's 'code commit'."""
    global _CODE_HASH
    if _CODE_HASH is None:
        d = os.path.dirname(os.path.abspath(__file__))
        h = hashlib.sha256()
        for f in sorted(os.listdir(d)):
            if f.endswith(".py"):
                h.update(f.encode())
                with open(os.path.join(d, f), "rb") as fh:
                    h.update(fh.read())
        _CODE_HASH = h.hexdigest()
    return _CODE_HASH


def env() -> dict:
    import numpy
    import scipy
    return {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "host": platform.node(), "os": platform.platform(terse=True)}


def source_versions() -> dict:
    return kv_get("source_versions", {})


def receipt(agent, question, summary, *, hypothesis_id="", experiment_id="", inputs=None, params=None, outputs=None,
            stats=None, limitations="", interpretation="", review="", level="OBSERVATION", artifact=None) -> str:
    """Write one immutable receipt. receipt[n].prev_hash = hash(receipt[n-1])."""
    with _LOCK:
        c = db()
        last = c.execute("SELECT n, hash FROM receipts ORDER BY n DESC LIMIT 1").fetchone()
        n = (last["n"] + 1) if last else 1
        prev = last["hash"] if last else "0" * 64
        rid = "R%04d" % n
        art_path = ""
        if artifact is not None:
            d = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "artifacts")
            os.makedirs(d, exist_ok=True)
            art_path = "artifacts/%s.json" % rid
            with open(os.path.join(d, rid + ".json"), "w") as f:
                json.dump(artifact, f, default=str)
        row = {"id": rid, "ts": round(now(), 3), "agent": agent, "question": question, "hypothesis_id": hypothesis_id,
               "experiment_id": experiment_id, "code_hash": code_hash(), "env": env(), "versions": source_versions(),
               "input_hash": H(inputs or {}), "params": params or {}, "output_hash": H(outputs if outputs is not None else artifact or {}),
               "summary": summary, "stats": stats or {}, "limitations": limitations, "interpretation": interpretation,
               "review": review, "artifact": art_path, "level": level, "prev_hash": prev}
        h = H(row)
        c.execute("INSERT INTO receipts(n,id,ts,agent,question,hypothesis_id,experiment_id,code_hash,env,versions,input_hash,params,"
                  "output_hash,summary,stats,limitations,interpretation,review,artifact,level,prev_hash,hash) VALUES "
                  "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (n, rid, row["ts"], agent, question, hypothesis_id, experiment_id, row["code_hash"], json.dumps(row["env"]),
                   json.dumps(row["versions"]), row["input_hash"], json.dumps(row["params"], default=str), row["output_hash"],
                   summary, json.dumps(row["stats"], default=str), limitations, interpretation, review, art_path, level, prev, h))
        c.commit()
        return rid


def verify_chain() -> dict:
    """Recompute every receipt hash and link. Returns {ok, n, broken_at}."""
    prev = "0" * 64
    n = 0
    for r in db().execute("SELECT * FROM receipts ORDER BY n"):
        row = {"id": r["id"], "ts": r["ts"], "agent": r["agent"], "question": r["question"], "hypothesis_id": r["hypothesis_id"],
               "experiment_id": r["experiment_id"], "code_hash": r["code_hash"], "env": json.loads(r["env"]),
               "versions": json.loads(r["versions"]), "input_hash": r["input_hash"], "params": json.loads(r["params"]),
               "output_hash": r["output_hash"], "summary": r["summary"], "stats": json.loads(r["stats"]),
               "limitations": r["limitations"], "interpretation": r["interpretation"], "review": r["review"],
               "artifact": r["artifact"], "level": r["level"], "prev_hash": r["prev_hash"]}
        if r["prev_hash"] != prev or H(row) != r["hash"]:
            return {"ok": False, "n": n, "broken_at": r["id"]}
        prev = r["hash"]
        n += 1
    return {"ok": True, "n": n, "head": prev}


def node(nid, ntype, label, data=None):
    with _LOCK:
        db().execute("INSERT OR IGNORE INTO nodes VALUES(?,?,?,?,?)", (nid, ntype, label, json.dumps(data or {}, default=str), now()))
        db().commit()


def edge(src, dst, rel, receipt_id=""):
    with _LOCK:
        c = db()
        if not c.execute("SELECT 1 FROM edges WHERE src=? AND dst=? AND rel=?", (src, dst, rel)).fetchone():
            c.execute("INSERT INTO edges(src,dst,rel,receipt_id,ts) VALUES(?,?,?,?,?)", (src, dst, rel, receipt_id, now()))
            c.commit()


def set_source(name, version, url=""):
    with _LOCK:
        v = kv_get("source_versions", {})
        if v.get(name) != version:
            v[name] = version
            kv_set("source_versions", v)
            db().execute("INSERT INTO sources(name,version,url,ts,hash) VALUES(?,?,?,?,?)", (name, version, url, now(), H([name, version])))
            db().commit()
