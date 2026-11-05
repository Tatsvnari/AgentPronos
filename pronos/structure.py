"""Structure Agent: catalogue every released vault structure in the PDB and watch for new ones.

Entries are found by domain annotation (Pfam/InterPro vault families on the polymer entities), not by words in titles. For each
entry: title, method, resolution, release date, source organism(s), number of protein chains, and every bound small molecule.
A new entry is an event; if it is the reported phage vault (or any prokaryotic vault), the frozen pocket predictions become testable
and a handoff to evaluate them is written, because fitting a molecule into a map is checked by people, not asserted by this agent."""
from __future__ import annotations

import json

from . import ledger, sources

ANNOT = ["PF01505", "PF11978", "PF17794", "PF17795", "PF17796", "IPR039059"]
AGENT = "Structure Agent"


def search():
    q = {"query": {"type": "terminal", "service": "text",
                   "parameters": {"attribute": "rcsb_polymer_entity_annotation.annotation_id", "operator": "in", "value": ANNOT}},
         "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": 500}}}
    body, _ = sources.get("https://search.rcsb.org/rcsbsearch/v2/query", host="rcsb", raw=True, data=json.dumps(q).encode(),
                          headers={"Content-Type": "application/json"})
    return sorted(r["identifier"] for r in json.loads(body).get("result_set", [])) if body else []


def entry(pid):
    e = sources.rcsb_entry(pid) or {}
    info = e.get("rcsb_entry_info", {})
    res = (info.get("resolution_combined") or [None])[0]
    orgs, chains, vault_chains = set(), 0, 0
    for eid in (e.get("rcsb_entry_container_identifiers", {}).get("polymer_entity_ids") or []):
        pe, _ = sources.get("https://data.rcsb.org/rest/v1/core/polymer_entity/%s/%s" % (pid, eid), host="rcsb")
        if not pe:
            continue
        n = len(pe.get("rcsb_polymer_entity_container_identifiers", {}).get("auth_asym_ids") or [])
        chains += n
        ann = {a.get("annotation_id") for a in pe.get("rcsb_polymer_entity_annotation") or []}
        if ann & set(ANNOT):
            vault_chains += n
        for o in pe.get("rcsb_entity_source_organism") or []:
            if o.get("scientific_name"):
                orgs.add(o["scientific_name"])
    ligs = []
    for eid in (e.get("rcsb_entry_container_identifiers", {}).get("non_polymer_entity_ids") or []):
        npe, _ = sources.get("https://data.rcsb.org/rest/v1/core/nonpolymer_entity/%s/%s" % (pid, eid), host="rcsb")
        if npe:
            cid = npe.get("pdbx_entity_nonpoly", {}).get("comp_id")
            nm = npe.get("pdbx_entity_nonpoly", {}).get("name")
            n = len(npe.get("rcsb_nonpolymer_entity_container_identifiers", {}).get("auth_asym_ids") or [])
            ligs.append({"id": cid, "name": nm, "copies": n})
    return {"id": pid, "title": (e.get("struct") or {}).get("title", ""), "method": ((e.get("exptl") or [{}])[0]).get("method", ""),
            "resolution": res, "released": (e.get("rcsb_accession_info") or {}).get("initial_release_date", "")[:10],
            "organisms": sorted(orgs), "chains": chains, "vault_chains": vault_chains, "ligands": ligs}


def run():
    c = ledger.db()
    known = {r[0] for r in c.execute("SELECT id FROM structures")}
    ids = search()
    ledger.set_source("RCSB PDB", ledger.time.strftime("%Y-%m-%d", ledger.time.gmtime()) + " search", "https://www.rcsb.org")
    new = [i for i in ids if i not in known]
    rows = []
    for pid in ids:
        if pid in known:
            continue
        d = entry(pid)
        rows.append(d)
        with ledger._LOCK:
            c.execute("INSERT OR REPLACE INTO structures VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (pid, d["title"], d["method"], d["resolution"], d["released"], "; ".join(d["organisms"]), d["chains"],
                       json.dumps(d["ligands"]), json.dumps(d), ledger.now()))
            c.commit()
        ledger.node("pdb:" + pid, "Structure", d["title"], d)
    allrows = [json.loads(r[0]) for r in c.execute("SELECT data FROM structures")]
    ligset = sorted({l["id"] for d in allrows for l in d["ligands"]})
    rid = ledger.receipt(AGENT, "Which vault structures are released, and what small molecules are bound in them?",
                         "%d vault structures in the PDB (%d new this pass). Bound small molecules seen: %s."
                         % (len(allrows), len(new), ", ".join(ligset) or "none"),
                         inputs={"annotations": ANNOT}, outputs={"ids": ids}, stats={"n": len(allrows), "new": new, "ligands": ligset},
                         level="OBSERVATION", artifact={"entries": allrows},
                         limitations="Catalogue from PDB metadata only; no map or model geometry is analysed here.")
    if known and new:
        ledger.event(AGENT, "new-structure", "New vault structure(s) released: %s. Queued for comparison with the frozen pocket predictions."
                     % ", ".join(new), rid)
        from . import loop
        for h in c.execute("SELECT id FROM hypotheses WHERE branch='ligand' AND status='ACTIVE'"):
            loop.handoff(h[0], {"question": "New structures %s may test the frozen pocket predictions of %s." % (", ".join(new), h[0]),
                                "why": "Fitting candidate molecules into released density is checked by structural biologists.",
                                "entries": new})
    else:
        ledger.event(AGENT, "catalogue", "Catalogued %d released vault structures (%s)." %
                     (len(allrows), "first pass" if not known else "no new entries since the last pass"), rid)
    return rid
