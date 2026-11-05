"""The rules the record depends on: receipts chain and detect tampering, predictions must be frozen before tests, replications
must differ in method, confidence follows the fixed rule, held-out partitions are fixed. Runs offline on a temporary database."""
import json
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_TMP = tempfile.mkdtemp()
os.environ["VFS_DB"] = os.path.join(_TMP, "test.sqlite")

from pronos import census, ledger, loop  # noqa: E402

HYP = {"statement": "Test statement.", "mechanism": "Test mechanism.", "why_vault": "Test reason.",
       "predictions": [{"text": "P one", "kind": "discovery"}, {"text": "P two", "kind": "heldout"}, {"text": "P three", "kind": "phylo"}]}


class Rules(unittest.TestCase):
    def test_chain_detects_tampering(self):
        ledger.receipt("t", "q1", "first")
        ledger.receipt("t", "q2", "second")
        self.assertTrue(ledger.verify_chain()["ok"])
        db = ledger.db()
        n = db.execute("SELECT MAX(n) FROM receipts").fetchone()[0]
        db.execute("UPDATE receipts SET summary='edited' WHERE n=?", (n,))
        db.commit()
        v = ledger.verify_chain()
        self.assertFalse(v["ok"])
        db.execute("DELETE FROM receipts WHERE n=?", (n,))      # leave the shared test db consistent
        db.commit()

    def test_needs_three_predictions(self):
        with self.assertRaises(SystemExit):
            loop.add_hypothesis({**HYP, "predictions": HYP["predictions"][:2]})

    def test_no_test_before_freeze(self):
        hid = loop.add_hypothesis(HYP)
        with self.assertRaises(SystemExit):
            loop.result(hid + "-P1", "pass", {"method": "m1", "summary": "s"})
        loop.freeze(hid)
        with self.assertRaises(SystemExit):
            loop.freeze(hid)                                     # frozen once, never again

    def test_replication_must_differ_and_confidence_rule(self):
        hid = loop.add_hypothesis(HYP)
        loop.freeze(hid)
        loop.result(hid + "-P1", "pass", {"method": "m1", "summary": "s"})
        c1 = ledger.db().execute("SELECT confidence FROM hypotheses WHERE id=?", (hid,)).fetchone()[0]
        expect = 1 / (1 + math.exp(-(math.log(loop.PRIOR / (1 - loop.PRIOR)) + loop.W[("discovery", "pass")])))
        self.assertAlmostEqual(c1, round(expect, 4), places=4)
        with self.assertRaises(SystemExit):
            loop.replicate(hid + "-P1", "pass", {"method": "m1", "summary": "same method"})
        loop.replicate(hid + "-P1", "fail", {"method": "m2", "summary": "different method"})
        open_c = ledger.db().execute("SELECT COUNT(*) FROM contradictions WHERE hypothesis_id=?", (hid,)).fetchone()[0]
        self.assertEqual(open_c, 1)                              # disagreement stays visible

    def test_partition_is_fixed(self):
        self.assertEqual(census.partition_of("Corallococcus"), census.partition_of("Corallococcus"))
        parts = [census.partition_of("g%d" % i) for i in range(2000)]
        share = parts.count("discovery") / len(parts)
        self.assertTrue(0.65 < share < 0.75, share)


if __name__ == "__main__":
    unittest.main()
