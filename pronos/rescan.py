"""Uniform repeat rescan: count vault repeat domains the same way for every protein.

The census takes repeat counts from database annotation, which uses each Pfam model's gathering threshold. Diverged repeats can
fall under that threshold, and if they diverge more in some lineages than others, the annotation can make one group look as if
it carries more repeats. This module re-measures from the sequences themselves: all four MVP repeat models (Pfam PF01505,
PF17794, PF17795, PF17796) are searched against every census sequence with one sensitive per-domain cutoff, overlapping hits are
merged into one repeat, and the count is stored next to the annotated one. The receipt reports totals only; group comparisons are
left to the agent's frozen tests."""
from __future__ import annotations

import os

from . import ledger

MODELS = ["PF01505", "PF17794", "PF17795", "PF17796"]
DOM_E = 1.0            # per-domain independent E-value cutoff: far more sensitive than the gathering thresholds (23-29 bits)
MERGE = 0.5            # two hits overlapping by at least half of the shorter one are the same repeat
HMM_DIR = os.path.join(os.path.dirname(os.path.abspath(ledger.DB_PATH)), "hmm")


def _fetch_models():
    from . import sources
    import gzip
    os.makedirs(HMM_DIR, exist_ok=True)
    for acc in MODELS:
        p = os.path.join(HMM_DIR, acc + ".hmm")
        if not os.path.exists(p):
            body, _ = sources.get("https://www.ebi.ac.uk/interpro/api/entry/pfam/%s?annotation=hmm" % acc, raw=True)
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
            open(p, "wb").write(body)
    return [os.path.join(HMM_DIR, a + ".hmm") for a in MODELS]


def _merge(iv):
    iv.sort()
    units = []
    for s, e in iv:
        if units:
            ps, pe = units[-1]
            ov = min(pe, e) - max(ps, s)
            if ov >= MERGE * min(pe - ps, e - s):
                units[-1] = (min(ps, s), max(pe, e))
                continue
        units.append((s, e))
    return units


def run(agent="Rescan"):
    import pyhmmer
    c = ledger.db()
    cols = [r[1] for r in c.execute("PRAGMA table_info(census)")]
    if "repeats_scan" not in cols:
        with ledger._LOCK:
            c.execute("ALTER TABLE census ADD COLUMN repeats_scan INTEGER")
            c.commit()
    paths = _fetch_models()
    hmms, versions = [], {}
    for p in paths:
        with pyhmmer.plan7.HMMFile(p) as f:
            h = f.read()
            hmms.append(h)
            versions[h.accession.decode() if isinstance(h.accession, bytes) else h.accession] = True
    alpha = pyhmmer.easel.Alphabet.amino()
    rows = c.execute("SELECT acc, seq FROM census").fetchall()
    seqs = [pyhmmer.easel.TextSequence(name=r["acc"].encode(), sequence=r["seq"]).digitize(alpha) for r in rows if r["seq"]]
    block = pyhmmer.easel.DigitalSequenceBlock(alpha, seqs)
    hits_by = {}
    for top in pyhmmer.hmmer.hmmsearch(hmms, block, E=1000.0, domE=DOM_E, cpus=2):
        for hit in top:
            name = hit.name.decode() if isinstance(hit.name, bytes) else hit.name
            for d in hit.domains:
                if d.i_evalue <= DOM_E:
                    hits_by.setdefault(name, []).append((d.env_from, d.env_to))
    counts = {r["acc"]: len(_merge(hits_by.get(r["acc"], []))) for r in rows}
    with ledger._LOCK:
        c.executemany("UPDATE census SET repeats_scan=? WHERE acc=?", [(v, k) for k, v in counts.items()])
        c.commit()
    vals = list(counts.values())
    ann = {r[0]: r[1] for r in c.execute("SELECT acc, repeats FROM census")}
    zero_ann = sum(1 for k in counts if ann.get(k, 0) == 0)
    zero_ann_found = sum(1 for k, v in counts.items() if ann.get(k, 0) == 0 and v > 0)
    stats = {"proteins": len(vals), "mean_repeats_scan": round(sum(vals) / max(1, len(vals)), 3),
             "mean_repeats_annotated": round(sum(ann.values()) / max(1, len(ann)), 3),
             "with_any_repeat": sum(1 for v in vals if v > 0),
             "annotated_zero": zero_ann, "annotated_zero_but_scan_found": zero_ann_found,
             "models": sorted(versions), "domain_evalue_cutoff": DOM_E, "merge_overlap": MERGE, "pyhmmer": pyhmmer.__version__}
    ledger.set_source("Pfam HMMs (InterPro API)", ", ".join(sorted(versions)), "https://www.ebi.ac.uk/interpro/")
    rid = ledger.receipt(agent, "How many vault repeat domains does each protein carry when every protein is scanned the same way?",
                         "Uniform rescan of %d proteins with 4 MVP repeat models (domain E <= %g): mean %.2f repeats per protein "
                         "(annotation: %.2f); repeats found in %d of %d proteins the annotation counted as zero."
                         % (len(vals), DOM_E, stats["mean_repeats_scan"], stats["mean_repeats_annotated"], zero_ann_found, zero_ann),
                         inputs={"models": MODELS, "proteins": len(vals)}, params={"domE": DOM_E, "merge": MERGE},
                         outputs=stats, stats=stats, level="OBSERVATION", artifact={"counts": counts},
                         limitations="Still model-based: a repeat too diverged for every Pfam model is missed. Totals only; no group "
                                     "comparison is reported here, so the agent's frozen tests read the groups first.")
    ledger.event(agent, "rescan", "Recounted repeat domains for all %d vault proteins with one uniform, sensitive scan "
                 "(mean %.2f per protein vs %.2f annotated). The groups are compared only by frozen tests."
                 % (len(vals), stats["mean_repeats_scan"], stats["mean_repeats_annotated"]), rid)
    return rid


def done():
    c = ledger.db()
    cols = [r[1] for r in c.execute("PRAGMA table_info(census)")]
    return "repeats_scan" in cols and c.execute("SELECT COUNT(*) FROM census WHERE repeats_scan IS NULL").fetchone()[0] == 0
