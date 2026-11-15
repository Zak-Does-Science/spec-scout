import csv
import tempfile
import unittest
from pathlib import Path

from specscout import load, match, optimize, rulepack
from specscout.cli import compare_days

ROOT = Path(__file__).resolve().parent.parent
HOU = ROOT / "examples" / "houston_school"


class HoustonPackTests(unittest.TestCase):
    def setUp(self):
        _, self.reqs, self.proj = load.load_project_full(HOU / "project.toml")
        self.packs = [rulepack.load_pack(p) for p in self.proj["rulepacks"]]
        rulepack.apply_rules(self.packs, self.reqs, self.proj)
        self.catalog = load.load_catalog(HOU / "catalog.toml")
        self.by_id = {r.id: r for r in self.reqs}

    def rejected(self, rid):
        _, rej = match.shortlist(self.by_id[rid], self.catalog)
        return {m.candidate.maker if "Example" in m.candidate.model else m.candidate.model for m in rej}

    def test_prohibited_makers(self):
        self.assertEqual(self.rejected("S1"), {"Hikvision", "Uniview"})
        self.assertEqual(self.rejected("S8"), {"TP-Link"})

    def test_code_rules(self):
        self.assertEqual(self.rejected("S2"), {"DoorBrain Lite"})        # no UL 294
        self.assertEqual(self.rejected("S4"), {"Beacon 250"})            # no voice evac in a school
        self.assertEqual(self.rejected("S5"), {"AlertButton Basic"})     # 19 TAC 61.1031 features
        self.assertEqual(self.rejected("S6"), {"RelayPoint Indoor"})     # NEMA 4 for ERRCS

    def test_when_conditions(self):
        proj = dict(self.proj, federal_funds=False, use_dir_list=False)
        self.assertFalse(rulepack.applies({"federal_funds": True}, proj))
        self.assertTrue(rulepack.applies({"site_type": ["k12", "higher_ed"]}, proj))

    def test_tax_exempt_and_taxable(self):
        self.assertEqual(rulepack.tax_rate(self.packs, self.proj)[0], 0.0)
        self.assertEqual(rulepack.tax_rate(self.packs, dict(self.proj, tax_exempt=False))[0], 0.0825)

    def test_order_rule_flags_vendor_without_contract(self):
        offers = load.load_price_list(HOU / "prices.csv")
        vendors, _ = load.load_vendors(HOU / "vendors.toml")
        sl = {r.id: match.shortlist(r, self.catalog)[0] for r in self.reqs}
        lines, ship, _ = optimize.optimize(sl, self.reqs, offers, vendors)
        total = sum(ln.extended for ln in lines) + sum(ship.values())
        rows = rulepack.order_checks(self.packs, self.proj, lines, vendors, total)
        flagged = {(r["id"], r["items"]) for r in rows if r["status"] == "CHECK"}
        self.assertIn(("TX-44.031", "bayou"), flagged)
        self.assertNotIn(("TX-44.031", "gulfline"), flagged)


class DailyCompareTests(unittest.TestCase):
    def write(self, path, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Item", "Vendor", "Model", "Unit price"])
            w.writerows(rows)

    def test_changes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.write(d / "a.csv", [["L1", "V1", "M1", "10.00"], ["L2", "V1", "M2", "5.00"]])
            self.write(d / "b.csv", [["L1", "V2", "M1", "9.50"], ["L3", "V1", "M3", "1.00"]])
            ch = compare_days(d / "a.csv", d / "b.csv", d / "changes.txt")
            self.assertEqual(len(ch), 3)
            self.assertIn("L1: M1 from V1 at $10.00 -> M1 from V2 at $9.50", ch)
            self.assertTrue((d / "changes.txt").exists())


if __name__ == "__main__":
    unittest.main()
