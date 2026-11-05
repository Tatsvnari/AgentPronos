"""Evolution Agent: alignment-free sequence similarity across the census.

Each protein becomes a normalised k-mer count profile (k = 3 for discovery, k = 4 for replication: a different representation,
not the same one rerun). Similarity is cosine. Two measurements, both with label-permutation nulls:

  separation  - for prokaryotic query proteins, how often is the nearest other-genus neighbour also prokaryotic?
  coherence   - for prokaryotic query proteins, how often is the nearest other-genus prokaryotic neighbour from the same phylum?

Neighbours from the query's own genus are always excluded, so near-identical relatives cannot carry the result. This is
similarity, not a phylogeny; the page says so."""
from __future__ import annotations

import numpy as np
from scipy import sparse

from . import ledger

AA = "ACDEFGHIKLMNPQRSTVWY"
_IDX = {a: i for i, a in enumerate(AA)}
_CACHE = {}


def _profiles(k):
    rel = ledger.source_versions().get("UniProtKB", "")
    key = (k, rel)
    if key in _CACHE:
        return _CACHE[key]
    rows = [dict(r) for r in ledger.db().execute("SELECT acc,domain,phylum,genus,partition,seq FROM census ORDER BY acc")]
    data, ri, ci = [], [], []
    for n, r in enumerate(rows):
        s = [_IDX.get(ch, -1) for ch in r["seq"]]
        counts = {}
        for i in range(len(s) - k + 1):
            w = s[i:i + k]
            if min(w) < 0:
                continue
            code = 0
            for x in w:
                code = code * 20 + x
            counts[code] = counts.get(code, 0) + 1
        for code, v in counts.items():
            ri.append(n); ci.append(code); data.append(float(v))
    X = sparse.csr_matrix((data, (ri, ci)), shape=(len(rows), 20 ** k))
    norm = np.sqrt(np.asarray(X.multiply(X).sum(axis=1)).ravel()) + 1e-12
    X = sparse.diags(1 / norm) @ X
    S = (X @ X.T).toarray()
    genus = np.array([r["genus"] for r in rows])
    S[genus[:, None] == genus[None, :]] = -1          # never a neighbour from the same genus (includes self)
    _CACHE.clear()
    _CACHE[key] = (rows, S)
    return rows, S


def measure(what, partition, k, seed, n_perm=2000, per_genus=False):
    rows, S = _profiles(k)
    prok = np.array([r["domain"] in ("Bacteria", "Archaea") for r in rows])
    phy = np.array([r["phylum"] for r in rows])
    q, seen = [], set()
    for i, r in enumerate(rows):
        if prok[i] and (partition is None or r["partition"] == partition) and not (per_genus and r["genus"] in seen):
            q.append(i); seen.add(r["genus"])
    q = np.array(q, dtype=int)
    if len(q) < 5:
        return None
    rng = np.random.default_rng(seed)
    if what == "separation":
        nn = S[q].argmax(axis=1)
        obs = float(prok[nn].mean())
        null = np.array([rng.permutation(prok)[nn].mean() for _ in range(n_perm)])   # labels shuffled over all proteins
        base = float(prok.mean())
    else:
        P = np.where(prok)[0]
        sub = S[np.ix_(q, P)]
        nn = P[sub.argmax(axis=1)]
        ok = sub.max(axis=1) > -1
        q2, nn = q[ok], nn[ok]
        if len(q2) < 5:
            return None
        obs = float((phy[q2] == phy[nn]).mean())
        perm = phy.copy()
        null = []
        for _ in range(n_perm):
            perm[P] = rng.permutation(phy[P])
            null.append((perm[q2] == perm[nn]).mean())
        null = np.array(null)
        base = float(null.mean())
    p = float((np.sum(null >= obs) + 1) / (len(null) + 1))
    return {"what": what, "k": k, "n_queries": int(len(q)), "observed": round(obs, 3), "chance": round(base, 3),
            "null_mean": round(float(null.mean()), 3), "p": float("%.3g" % p), "permutations": n_perm, "seed": seed,
            "excluded": "neighbours from the query's own genus", "one_query_per_genus": per_genus}
