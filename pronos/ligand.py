"""Ligand Agent: candidates for the unidentified molecule in the L05 pocket, and predictions frozen before its map is released.

Candidates come from two data sources, never from a hand list: (1) every small molecule seen bound in a released vault structure
(the Structure Agent's catalogue), and (2) coenzyme A, which the structure's authors reported the density resembles, with its
nearest PubChem neighbours by 2D fingerprint. Scores are computed: chemical similarity to CoA (Tanimoto on PubChem's CACTVS
fingerprint), size match to CoA, and how often the molecule is seen bound in vault structures. Structural fit to the L05 density
cannot be computed until the map is public, so it is shown as awaiting the map, and no candidate is called identified."""
from __future__ import annotations

import base64
import json

from . import ledger, loop, sources

AGENT = "Ligand Agent"
COA_CID = 87642
ADDITIVES = {"GOL", "EDO", "PEG", "PG4", "PGE", "SO4", "PO4", "ACT", "CL", "NA", "MG", "ZN", "CA", "K", "DMS", "FMT", "MPD", "TRS", "EPE", "IMD"}


def fp(b64):
    raw = base64.b64decode(b64)[4:]
    return int.from_bytes(raw, "big")


def tanimoto(a, b):
    inter = bin(a & b).count("1")
    union = bin(a | b).count("1")
    return inter / union if union else 0.0


def props_cid(cid):
    j, _ = sources.get("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/%d/property/Title,%s/JSON" % (cid, sources.PROPS), host="pubchem")
    try:
        return j["PropertyTable"]["Properties"][0]
    except Exception:
        return None


def cid_for_comp(comp):
    j, _ = sources.get("https://data.rcsb.org/rest/v1/core/chemcomp/" + comp, host="rcsb")
    for x in (j or {}).get("rcsb_chem_comp_related") or []:
        if x.get("resource_name") == "PubChem":
            return int(x["resource_accession_code"]), (j.get("chem_comp") or {}).get("name", comp)
    return None, comp


def run():
    c = ledger.db()
    coa = props_cid(COA_CID)
    ref = fp(coa["Fingerprint2D"])
    mw0 = float(coa["MolecularWeight"])
    ledger.set_source("PubChem PUG-REST", ledger.time.strftime("%Y-%m-%d", ledger.time.gmtime()), "https://pubchem.ncbi.nlm.nih.gov")
    cands = {}
    # (1) bound in released vault structures
    for sid, ligs in c.execute("SELECT id, ligands FROM structures"):
        for l in json.loads(ligs or "[]"):
            d = cands.setdefault(l["id"], {"comp": l["id"], "entries": [], "copies": 0, "origin": "bound in a released vault structure"})
            d["entries"].append(sid)
            d["copies"] = max(d["copies"], l.get("copies", 0))
    # (2) CoA and its nearest fingerprint neighbours
    j, _ = sources.get("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastsimilarity_2d/cid/%d/cids/JSON?Threshold=92&MaxRecords=12" % COA_CID, host="pubchem")
    for cid in ((j or {}).get("IdentifierList", {}).get("CID") or [COA_CID]):
        cands.setdefault("CID%d" % cid, {"cid": cid, "entries": [], "copies": 0,
                                         "origin": "reported shape resemblance" if cid == COA_CID else "PubChem 2D neighbour of coenzyme A"})
    rows = []
    for key, d in cands.items():
        name = key
        if "comp" in d:
            cid, name = cid_for_comp(d["comp"])
            d["cid"] = cid
        p = props_cid(d["cid"]) if d.get("cid") else None
        if p:
            name = p["Title"] if p.get("Title") and not p["Title"].startswith("CID ") else name.title()
        sim = round(tanimoto(ref, fp(p["Fingerprint2D"])), 3) if p and p.get("Fingerprint2D") else None
        mw = float(p["MolecularWeight"]) if p else None
        size = round(max(0.0, 1 - abs(mw - mw0) / mw0), 3) if mw else None
        flags = []
        if d.get("comp") in ADDITIVES:
            flags.append("common crystallisation or buffer additive")
        bound = len(d["entries"])
        tier = ("NOT A CANDIDATE" if flags else
                "MODERATE (seen bound in vaults; structural fit to L05 unknown)" if bound and (sim or 0) >= 0.5 else
                "WEAK (seen bound in vaults, chemically unlike CoA)" if bound else
                "WEAK (resembles CoA; never seen bound in a vault)" if (sim or 0) >= 0.9 else "VERY WEAK")
        score = {"structural": None, "chemical": sim, "size": size, "vault_bound": bound, "copies": d["copies"],
                 "evolutionary": None, "genomic": None, "contradictions": len(flags), "flags": flags, "overall": tier,
                 "mw": mw, "entries": d["entries"][:8], "cid": d.get("cid")}
        rows.append((key, name, d.get("cid"), d["origin"], json.dumps({"comp": d.get("comp")}), json.dumps(score), ledger.now()))
    with ledger._LOCK:
        c.execute("DELETE FROM ligands")     # working table: the receipt below keeps every pass's full ranking
        c.executemany("INSERT INTO ligands VALUES(?,?,?,?,?,?,?)", rows)
        c.commit()
    ranked = sorted(rows, key=lambda r: (-(json.loads(r[5])["vault_bound"] > 0), -(json.loads(r[5])["chemical"] or 0)))
    rid = ledger.receipt(AGENT, "Which molecules are candidates for the unidentified L05 pocket molecule, on the evidence available now?",
                         "%d candidates: %d seen bound in released vault structures, %d from coenzyme A's fingerprint neighbourhood. "
                         "Structural fit awaits the L05 map." % (len(rows), sum(1 for k in cands.values() if k["entries"]),
                                                                 sum(1 for k in cands.values() if not k["entries"])),
                         inputs={"coa_cid": COA_CID, "structures": [r[0] for r in c.execute("SELECT id FROM structures")]},
                         outputs=[(r[0], r[1], json.loads(r[5])) for r in ranked], level="OBSERVATION",
                         limitations="No density is available, so nothing here measures fit to the pocket. Similarity to CoA is a "
                                     "proxy for the authors' reported shape resemblance, not evidence of identity.",
                         artifact={"candidates": [(r[0], r[1], r[3], json.loads(r[5])) for r in rows]})
    full = [(r[1], json.loads(r[5])) for r in rows if json.loads(r[5])["copies"] >= 39 and not json.loads(r[5])["flags"]]
    if full:
        ledger.event(AGENT, "known", "Observation, already published (KNOWN): released vault structures carry %s on every major vault "
                     "protein copy (up to %d copies in one particle). Like coenzyme A, these are built on an ADP core."
                     % (", ".join(sorted({n for n, _ in full})), max(sc["copies"] for _, sc in full)), rid)
    ledger.event(AGENT, "ligands", "Ranked %d candidate molecules for the L05 pocket from released vault structures and PubChem. "
                 "None is identified: the map is not public yet." % len(rows), rid)
    return rid


PROSPECTIVE = [
    ("CoA", "The L05 pocket holds coenzyme A or a CoA thioester.",
     "The pocket binds the pantetheine arm as well as the ADP core, so the shell carries an acyl-group carrier on every copy.",
     ["When the L05 map is released, a CoA-family molecule accounts for the pocket density better than the best ADP-ribose/NAD-family and other candidates.",
      "The density includes a pantetheine-length arm extending beyond an ADP core.",
      "Residues that contact that arm are conserved across prokaryotic vault proteins more than the protein as a whole."]),
    ("ADP-nucleotide", "The L05 pocket holds an ADP-ribose or NAD-type nucleotide, like the molecules bound to every copy of released human vault shoulders.",
     "The ancestral vault shoulder binds an adenine nucleotide, and the phage vault kept that site.",
     ["When the L05 map is released, an ADP-ribose/NAD-family molecule accounts for the pocket density better than the best CoA-family and other candidates.",
      "The density ends at the ribose or nicotinamide end, with no pantetheine-length arm.",
      "The L05 pocket aligns structurally to the human vault shoulder site that binds NAD and ADP-ribose."]),
    ("other", "The L05 pocket holds a molecule outside both the CoA and ADP-nucleotide families.",
     "The phage vault pocket evolved a different ligand from the eukaryotic shoulder site.",
     ["When the L05 map is released, neither family's best candidate accounts for the pocket density.",
      "The density has no ADP-like core.",
      "The L05 pocket does not align to the human vault shoulder ligand site."]),
]


def freeze_prospective():
    """Competing predictions about the pocket, frozen now, before the L05 map exists publicly. Run once."""
    if ledger.kv_get("prospective_frozen"):
        return []
    ids = []
    for key, stmt, mech, preds in PROSPECTIVE:
        hid = loop.add_hypothesis({"statement": stmt, "mechanism": mech, "why_vault": "Concerns the ligand bound in every copy of the vault wall.",
                                   "branch": "ligand", "origin": "prospective:" + key, "question": "What is the molecule in the L05 pocket?",
                                   "answer": key, "predictions": [{"text": t, "kind": "prospective", "test": {"awaits": "L05 map and model release"}} for t in preds]},
                                  creator="Pronos")
        loop.freeze(hid)
        ids.append(hid)
    ledger.kv_set("prospective_frozen", ids)
    ledger.event("Pronos", "prospective", "Froze %d competing answers about the L05 pocket (%s) before its map is public. When the structure is "
                 "released these become genuinely held-out tests." % (len(ids), ", ".join(ids)))
    return ids
