"""Data connectors. Every call records the source's exact release/date into the ledger so database versions never mix silently."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import ledger

UA = "pronos/0.1 (computational research record)"
_last = {}
GAP = {"ncbi": 0.36, "uniprot": 0.2, "ebi": 0.2, "rcsb": 0.2, "pubchem": 0.25, "europepmc": 0.2, "biorxiv": 0.5, "crossref": 0.3}


def get(url, params=None, host="ebi", raw=False, tries=4, data=None, headers=None):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    for i in range(tries):
        gap = GAP.get(host, 0.3) - (time.time() - _last.get(host, 0))
        if gap > 0:
            time.sleep(gap)
        _last[host] = time.time()
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
                hdr = dict(r.headers)
            if raw:
                return body, hdr
            return json.loads(body), hdr
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return (None, {}) if not raw else (b"", {})
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return (None, {}) if not raw else (b"", {})


# ---------------- UniProt ----------------
VAULT_QUERY = ("(xref:interpro-IPR039059 OR xref:pfam-PF01505 OR xref:pfam-PF17794 OR xref:pfam-PF17795 OR "
               "xref:pfam-PF17796 OR xref:pfam-PF11978)")


def uniprot_stream(query, fields):
    """Yields UniProt JSON entries for a query (paged search; records the release)."""
    url = "https://rest.uniprot.org/uniprotkb/search?" + urllib.parse.urlencode({"query": query, "fields": fields, "format": "json", "size": 500})
    while url:
        body, hdr = get(url, host="uniprot", raw=True)
        if not body:
            break
        rel = hdr.get("X-UniProt-Release") or hdr.get("x-uniprot-release")
        if rel:
            ledger.set_source("UniProtKB", "%s (%s)" % (rel, hdr.get("X-UniProt-Release-Date", "")), "https://rest.uniprot.org")
        for e in json.loads(body).get("results", []):
            yield e
        link = hdr.get("Link") or hdr.get("link") or ""
        url = link.split(";")[0].strip("<> ") if 'rel="next"' in link else None


# ---------------- NCBI ----------------
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def ncbi_text(util, **params):
    params.setdefault("tool", "vaultsearch")
    body, _ = get(EUTILS + util + ".fcgi", params, host="ncbi", raw=True)
    return body.decode("utf-8", "replace") if body else ""


def ncbi_version():
    j, _ = get(EUTILS + "einfo.fcgi", {"db": "nuccore", "retmode": "json"}, host="ncbi")
    try:
        info = j["einforesult"]["dbinfo"][0]
        ledger.set_source("NCBI nuccore", "%s, %s records" % (info.get("lastupdate", "?"), info.get("count", "?")), EUTILS)
    except Exception:
        pass


# ---------------- Europe PMC ----------------
def epmc_search(query, limit=2000, since=None):
    q = query + (" AND FIRST_PDATE:[%s TO 3000-01-01]" % since if since else "")
    cursor = "*"
    out = []
    while len(out) < limit:
        j, _ = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                   {"query": q, "resultType": "core", "format": "json", "pageSize": 500, "cursorMark": cursor}, host="europepmc")
        if not j:
            break
        res = j.get("resultList", {}).get("result", [])
        out += res
        nxt = j.get("nextCursorMark")
        if not res or not nxt or nxt == cursor:
            break
        cursor = nxt
    ledger.set_source("Europe PMC", time.strftime("%Y-%m-%d", time.gmtime()), "https://europepmc.org")
    return out[:limit]


# ---------------- RCSB PDB ----------------
def rcsb_search_text(text):
    q = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": text}},
         "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": 200}}}
    body, _ = get("https://search.rcsb.org/rcsbsearch/v2/query", host="rcsb", raw=True,
                  data=json.dumps(q).encode(), headers={"Content-Type": "application/json"})
    if not body:
        return []
    return [r["identifier"] for r in json.loads(body).get("result_set", [])]


def rcsb_entry(pdb_id):
    j, _ = get("https://data.rcsb.org/rest/v1/core/entry/" + pdb_id, host="rcsb")
    return j


def rcsb_version():
    j, _ = get("https://data.rcsb.org/rest/v1/holdings/current/entry_ids", host="rcsb", raw=True)
    ledger.set_source("RCSB PDB", time.strftime("%Y-%m-%d", time.gmtime()) + " holdings", "https://www.rcsb.org")


# ---------------- PubChem ----------------
PROPS = "MolecularFormula,MolecularWeight,HeavyAtomCount,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,Charge,Fingerprint2D"


def pubchem_props(name):
    j, _ = get("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/%s/property/%s/JSON" % (urllib.parse.quote(name), PROPS), host="pubchem")
    try:
        ledger.set_source("PubChem PUG-REST", time.strftime("%Y-%m-%d", time.gmtime()), "https://pubchem.ncbi.nlm.nih.gov")
        return j["PropertyTable"]["Properties"][0]
    except Exception:
        return None


# ---------------- bioRxiv ----------------
def biorxiv_recent(days=30):
    end = time.strftime("%Y-%m-%d", time.gmtime())
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    out, cursor = [], 0
    while cursor < 20000:
        j, _ = get("https://api.biorxiv.org/details/biorxiv/%s/%s/%d" % (start, end, cursor), host="biorxiv")
        if not j or not j.get("collection"):
            break
        out += j["collection"]
        cursor += len(j["collection"])
        if len(j["collection"]) < 100:
            break
    ledger.set_source("bioRxiv API", end, "https://api.biorxiv.org")
    return out
