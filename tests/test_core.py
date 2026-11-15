import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from specscout import load, match, optimize, sheet
from specscout.capture import _price_from_jsonld, parse_price_text
from specscout.model import Candidate, Offer, Requirement, Vendor

EX = Path(__file__).resolve().parent.parent / "examples"


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.req = Requirement(id="X", name="x", qty=1, category="c",
                               constraints={"a": {"min": 10}, "std": {"all": ["UL"]},
                                            "r": {"not_in": ["bad"]}},
                               prefer={"a": "high"})

    def test_pass_and_fail_reasons(self):
        good = Candidate("G", "m", "c", {"a": 12, "std": ["UL", "CE"], "r": "ok"})
        low = Candidate("L", "m", "c", {"a": 5, "std": ["UL"], "r": "ok"})
        nostd = Candidate("N", "m", "c", {"a": 20, "std": ["CE"], "r": "bad"})
        missing = Candidate("M", "m", "c", {"std": ["UL"], "r": "ok"})
        self.assertTrue(match.evaluate(self.req, good).passed)
        self.assertIn("5 < required 10", match.evaluate(self.req, low).failures[0])
        self.assertEqual(len(match.evaluate(self.req, nostd).failures), 2)
        self.assertIn("not listed", match.evaluate(self.req, missing).failures[0])

    def test_ranking_prefers_high(self):
        cands = [Candidate(str(v), "m", "c", {"a": v, "std": ["UL"], "r": "ok"}) for v in (10, 30, 20)]
        top, rejected = match.shortlist(self.req, cands)
        self.assertEqual([m.candidate.model for m in top], ["30", "20", "10"])
        self.assertEqual(rejected, [])


class OptimizeTests(unittest.TestCase):
    def test_shipping_can_beat_cheapest_per_line(self):
        reqs = [Requirement("A", "a", 1, "c"), Requirement("B", "b", 1, "c")]
        ca, cb = Candidate("MA", "", "c"), Candidate("MB", "", "c")
        sl = {"A": [match.Match(reqs[0], ca, True, [], 0)], "B": [match.Match(reqs[1], cb, True, [], 0)]}
        vendors = [Vendor("v1", "V1", shipping=50), Vendor("v2", "V2", shipping=50)]
        offers = [Offer("v1", "MA", 100), Offer("v1", "MB", 110),
                  Offer("v2", "MA", 120), Offer("v2", "MB", 100)]
        # per-line cheapest = 100 + 100 + two shipping charges = 300; all from v1 = 210 + 50 = 260
        lines, ship, unfill = optimize.optimize(sl, reqs, offers, vendors)
        self.assertEqual({ln.offer.vendor for ln in lines}, {"v1"})
        self.assertEqual(ship, {"v1": 50})
        self.assertEqual(unfill, [])

    def test_unapproved_and_out_of_stock_are_skipped(self):
        r = Requirement("A", "a", 1, "c")
        c = Candidate("MA", "", "c")
        sl = {"A": [match.Match(r, c, True, [], 0)]}
        vendors = [Vendor("cheap", "Cheap", approved=False), Vendor("ok", "OK")]
        offers = [Offer("cheap", "MA", 1), Offer("ok", "MA", 5, in_stock=False)]
        lines, _, unfill = optimize.optimize(sl, [r], offers, vendors)
        self.assertEqual(lines, [])
        self.assertEqual(unfill, ["A"])


class CaptureParsingTests(unittest.TestCase):
    def test_jsonld(self):
        blob = '{"@type":"Product","offers":{"@type":"Offer","price":"1,234.50","availability":"https://schema.org/OutOfStock"}}'
        self.assertEqual(_price_from_jsonld(["not json", blob]), (1234.5, False))

    def test_price_text(self):
        self.assertEqual(parse_price_text("Now only $12,650.00!"), 12650.0)
        self.assertIsNone(parse_price_text("Call for price"))


class ExampleEndToEnd(unittest.TestCase):
    def test_example_project(self):
        name, reqs = load.load_project(EX / "lab_fitout.toml")
        catalog = load.load_catalog(EX / "catalog.toml")
        vendors, pages = load.load_vendors(EX / "vendors.toml")
        self.assertTrue(all(p["url"].startswith("file:") for p in pages))
        offers = load.load_price_list(EX / "prices.csv")
        sl, rej = {}, {}
        for r in reqs:
            sl[r.id], rej[r.id] = match.shortlist(r, catalog)
        self.assertNotIn("Polar 500C", [m.candidate.model for m in sl["L2"]])  # banned refrigerant
        lines, ship, unfill = optimize.optimize(sl, reqs, offers, vendors)
        self.assertEqual(unfill, [])
        self.assertNotIn("quickbuy", {ln.offer.vendor for ln in lines})
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "sheet.xlsx"
            sheet.write(out, name, lines, ship, vendors, sl, rej, unfill)
            wb = load_workbook(out)
            self.assertEqual(wb.sheetnames, ["Cost sheet", "Vendors", "Shortlists", "About"])
            self.assertTrue(out.with_suffix(".csv").exists())


if __name__ == "__main__":
    unittest.main()
