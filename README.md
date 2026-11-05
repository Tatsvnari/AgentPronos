<p align="center">
  <img src="assets/logo.png" alt="Pronos" width="420">
</p>

<p align="center">
  <b>An agent that researches what vault particles do, on its own and in public.</b><br>
  <a href="https://agentpronos.com">agentpronos.com</a> · predictions frozen before data · every failure kept
</p>

---

**What do vault particles do?** Vaults are hollow barrels of protein found in cells across the tree of life. They were
discovered in 1986, and their biological function is still unknown.

Pronos is a computational research record run by an autonomous agent, **Corbel**. Corbel picks its own questions,
writes competing answers, freezes their predictions with a hash *before* it looks at any data, tests them, attacks its own
results, re-tests on data it has never seen, replicates with a different method, and updates its confidence by a fixed rule.
Every step writes an immutable, hash-chained receipt. Failures stay on the record. A static web page publishes all of it.

## How a question is handled

1. **Ask:** pick a question answerable from public data.
2. **Compete:** write every rival answer (e.g. longer / shorter / no difference).
3. **Freeze:** hash each answer's predictions before any data is opened.
4. **Test:** run on the *discovery* set (70% of genera, fixed by hash).
5. **Attack:** a skeptic step looks for artefacts (one genus dominating, annotation gaps).
6. **Hidden test:** check the same prediction on the 30% of genera no hypothesis-forming step has seen.
7. **Replicate:** re-run with a different statistic or representation and a fresh seed. Disagreement opens a contradiction.
8. **Judge:** confidence moves by a fixed log-odds rule from those outcomes only. The scheduler picks the next step by
   expected information gain.

Claim levels: observation, reproduced observation, inference, hypothesis, supported hypothesis, speculation, rejected,
candidate explanation. A hypothesis needs a passed held-out test and a passed replication to be "supported".

## Branches

| Branch | What runs | Data |
|---|---|---|
| Census | Every vault-family protein, its taxonomy, length and repeat architecture, refreshed daily | UniProtKB REST |
| Architecture | Corbel compares length, repeat domains and the shoulder domain across prokaryotes/eukaryotes and animals/other eukaryotes | census |
| Evolution | Alignment-free k-mer similarity; do prokaryotic vaults form their own family, and do they group by phylum? | census sequences |
| Structure | Catalogue of released vault structures and their bound molecules; watcher for new entries | RCSB PDB |
| Ligand | Candidates for the unidentified molecule in the L05 phage-vault pocket; competing predictions frozen before its map is public | RCSB PDB, PubChem |

Out of scope: analysis of genes neighbouring vault genes, and literature mining. Laboratory questions are written up as
handoffs for qualified researchers, never simulated.

## Layout

```
corbel/
  ledger.py      SQLite record: events, hash-chained receipts, graph, hypotheses, predictions, experiments, confidence
  loop.py        research-loop rules: freeze, result, replicate, review, contradiction, judge, memo, handoff (+ researcher CLI)
  agent.py       Corbel: question space, competing answers, tests, skeptic, replication, information-gain scheduler
  census.py      vault-family census from UniProtKB and the discovery/validation split
  evolution.py   k-mer similarity measurements with permutation nulls
  structure.py   PDB catalogue and watcher
  ligand.py      pocket-molecule candidates and prospective predictions
  sources.py     HTTP connectors; every source's release/date is recorded
  publish.py     writes site/status.json from the ledger
site/            static page: index.html, app.js, cell.js (figure 1), tree.js (figure 2), vault.css, vendor/three
deploy/          systemd units, nginx location, publish script
tests/           ledger and rule tests
run.py           command line
```

## Run it

Requires Python 3.10+, `numpy`, `scipy` and network access to UniProt, RCSB and PubChem.

```bash
pip install -r requirements.txt
python run.py census              # build the census (about 20 s)
python run.py tick 10             # ten autonomous agent steps
python run.py publish site        # write site/status.json
python -m http.server -d site 8000
python run.py loop verify         # recompute the receipt chain
python -m unittest discover tests
```

`run.py agent 300` runs Corbel forever, one step every 300 s. The state lives in `state/vault.sqlite` (override with
`VFS_DB`); per-receipt artefacts go to `state/artifacts/`.

Researchers can add their own hypotheses through the same rules:

```bash
python run.py loop hypothesis add my_hypothesis.json   # needs >= 3 predictions
python run.py loop freeze H010
python run.py loop result H010-P1 pass result.json
```

## Deploy (systemd + nginx)

Copy the repo to `/opt/pronos`, then install the units under a common prefix, keeping each timer's name equal to
its service's name (e.g. `pronos-publish.service` + `pronos-publish.timer`). `deploy/publish.sh` copies
`site/` and a fresh `status.json` to `$VFS_WEBROOT` (default `/var/www/vaults`); `deploy/nginx-location.conf` serves it at
`/vaults/`. The page needs no backend.

## Licence

MIT, see [LICENSE](LICENSE). Third-party code and data are listed in [THIRD_PARTY.md](THIRD_PARTY.md).
