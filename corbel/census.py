"""Genome Archaeologist, part 1: the vault census. Every vault-family protein in UniProtKB, its taxonomy, size, repeat
architecture and EMBL coding record, plus the discovery / hidden-validation split (by genus, 70/30, fixed by hash)."""
from __future__ import annotations

import collections
import hashlib
import json

from . import ledger, sources

FIELDS = "accession,organism_name,organism_id,lineage,length,protein_name,xref_embl,ft_domain,xref_pfam,sequence"


def partition_of(genus: str) -> str:
    """Held-out split by genus so relatives never straddle the line. Fixed forever by sha256."""
    v = int(hashlib.sha256(("vault-split-1:" + (genus or "?")).encode()).hexdigest()[:8], 16) % 100
    return "discovery" if v < 70 else "validation"


def _phylum(lin):
    if not lin:
        return "?"
    if lin[0] in ("Bacteria", "Archaea"):
        for x in lin[1:4]:
            if x.endswith("ota") or x.endswith("otes") or x.endswith("eota"):
                return x
        return lin[2] if len(lin) > 2 else lin[-1]
    return lin[1] if len(lin) > 1 else lin[0]


def run(agent="Genome Archaeologist"):
    c = ledger.db()
    n_new = 0
    seen = set(r[0] for r in c.execute("SELECT acc FROM census"))
    rel = None
    rows = []
    for e in sources.uniprot_stream(sources.VAULT_QUERY, FIELDS):
        acc = e["primaryAccession"]
        org = e.get("organism", {})
        lin = org.get("lineage", [])
        dom = lin[0] if lin else "?"
        if dom == "Eukaryota":
            dom = "Eukaryota"
        feats = e.get("features", [])
        reps = sum(1 for f in feats if f.get("type") == "Domain" and "repeat" in (f.get("description") or "").lower())
        shoulder = sum(1 for f in feats if "shoulder" in (f.get("description") or "").lower())
        pf = sorted({x["id"] for x in e.get("uniProtKBCrossReferences", []) if x["database"] == "Pfam"})
        pid, nuc = "", ""
        for x in e.get("uniProtKBCrossReferences", []):
            if x["database"] == "EMBL":
                props = {p["key"]: p["value"] for p in x.get("properties", [])}
                if props.get("ProteinId", "-") != "-" and props.get("MoleculeType", "").startswith("Genomic"):
                    pid, nuc = props["ProteinId"], x["id"]
                    break
        if not pid:
            for x in e.get("uniProtKBCrossReferences", []):
                if x["database"] == "EMBL":
                    props = {p["key"]: p["value"] for p in x.get("properties", [])}
                    if props.get("ProteinId", "-") != "-":
                        pid, nuc = props["ProteinId"], x["id"]
                        break
        pd = e.get("proteinDescription", {})
        name = (pd.get("recommendedName") or (pd.get("submissionNames") or [{}])[0]).get("fullName", {}).get("value", "")
        genus = lin[-1] if lin else "?"
        rel = ledger.source_versions().get("UniProtKB", "")
        rows.append((acc, org.get("scientificName", ""), org.get("taxonId", 0), json.dumps(lin), dom, _phylum(lin), genus,
                     e.get("sequence", {}).get("length", 0), reps, shoulder, json.dumps(pf), name, pid, nuc,
                     partition_of(genus), e.get("sequence", {}).get("value", ""), rel))
        if acc not in seen:
            n_new += 1
    with ledger._LOCK:
        c.executemany("INSERT OR REPLACE INTO census VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        c.commit()
    s = summary()
    rid = ledger.receipt(agent, "Which proteins in UniProtKB belong to the vault family, and where on the tree of life are they?",
                         "Census: %d vault-family proteins (%d new). Bacteria %d, Archaea %d, Eukaryota %d, viruses %d; %d phyla."
                         % (s["total"], n_new, s["by_domain"].get("Bacteria", 0), s["by_domain"].get("Archaea", 0),
                            s["by_domain"].get("Eukaryota", 0), s["by_domain"].get("Viruses", 0), len(s["by_phylum"])),
                         inputs={"query": sources.VAULT_QUERY, "release": rel}, params={"fields": FIELDS},
                         outputs=s, stats=s, level="OBSERVATION",
                         limitations="UniProtKB holds no phage vault proteins (phage vaults live in metagenomes and phage genomes not "
                                     "translated into UniProtKB); phage association is therefore measured from genomic context.",
                         artifact={"accessions": [r[0] for r in rows]})
    ledger.node("dataset:census", "Dataset", "Vault census (UniProtKB %s)" % rel, s)
    ledger.event(agent, "census", "Census updated: %d vault-family proteins across %d phyla (%d new)." % (s["total"], len(s["by_phylum"]), n_new), rid)
    return rid


def summary():
    c = ledger.db()
    rows = c.execute("SELECT domain, phylum, genus, length, repeats, partition, organism FROM census").fetchall()
    by_dom = collections.Counter(r["domain"] for r in rows)
    by_phy = collections.Counter((r["domain"], r["phylum"]) for r in rows)
    rep = collections.Counter((r["domain"], r["repeats"]) for r in rows)
    genera = len({r["genus"] for r in rows})
    species = len({r["organism"] for r in rows})
    part = collections.Counter(r["partition"] for r in rows if r["domain"] in ("Bacteria", "Archaea"))
    return {"total": len(rows), "by_domain": dict(by_dom), "genera": genera, "species": species,
            "by_phylum": [{"domain": d, "phylum": p, "n": n} for (d, p), n in by_phy.most_common()],
            "repeats": [{"domain": d, "repeats": k, "n": n} for (d, k), n in sorted(rep.items(), key=lambda x: (x[0][0], x[0][1]))],
            "partition_prokaryote": dict(part)}
