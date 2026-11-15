import unittest
from pathlib import Path

from specscout import load, match, optimize, rulepack

HC = Path(__file__).resolve().parent.parent / "examples" / "houston_healthcare"


def setup(project):
    _, reqs, proj = load.load_project_full(HC / project)
    packs = [rulepack.load_pack(p) for p in proj["rulepacks"]]
    rulepack.apply_rules(packs, reqs, proj)
    catalog = load.load_catalog(HC / "catalog.toml")
    rejected = {}
    shortlists = {}
    for r in reqs:
        shortlists[r.id], rej = match.shortlist(r, catalog)
        rejected[r.category] = {m.candidate.model for m in rej}
    return reqs, proj, packs, shortlists, rejected


class PharmacyTests(unittest.TestCase):
    def test_rejections(self):
        _, _, _, _, rej = setup("pharmacy.toml")
        self.assertIn("HomeSafe DIY Kit", rej["intrusion"])      # 22 TAC 291.33 monitored alarm
        self.assertIn("Mini 3.1", rej["vaccine_fridge"])         # TVFC: no dorm units
        self.assertIn("USB TempStick", rej["data_logger"])       # TVFC logger spec
        self.assertIn("Room Sensor Basic", rej["pressure_monitor"])
        self.assertIn("HomeShare 2", rej["server"])              # HIPAA unique IDs + audit log
        self.assertNotIn("Drawer lockbox", rej["cs_cabinet"])    # DEA allows a locked cabinet

    def test_baa_flagged_for_vendor_without_one(self):
        reqs, proj, packs, sl, _ = setup("pharmacy.toml")
        offers = load.load_price_list(HC / "prices.csv")
        vendors, _ = load.load_vendors(HC / "vendors.toml")
        lines, ship, _ = optimize.optimize(sl, reqs, offers, vendors)
        rows = [r for r in rulepack.order_checks(packs, proj, lines, vendors, 0) if r["id"] == "HIPAA-BAA"]
        status = {r["items"]: r["status"] for r in rows}
        self.assertEqual(status.get("clinictech"), "ok")
        self.assertIn("CHECK", status.values())
        self.assertNotIn("coldchain", status)  # fridges are out of the BAA rule's categories


class VetTests(unittest.TestCase):
    def test_texas_vet_cabinet_and_no_hipaa(self):
        _, proj, packs, _, rej = setup("vet_clinic.toml")
        self.assertEqual(rej["cs_cabinet"], {"Drawer lockbox"})  # 22 TAC 573.61(5)
        ids = {c["id"] for c in rulepack.checklist(packs, [], proj)}
        self.assertNotIn("HIPAA-164.308", ids)
        self.assertIn("TX-801.353", ids)

    def test_wildlife_opioids_need_class_v(self):
        reqs, proj, packs, _, _ = setup("vet_clinic.toml")
        proj = dict(proj, wildlife_opioids=True)
        _, reqs2, _ = load.load_project_full(HC / "vet_clinic.toml")
        rulepack.apply_rules(packs, reqs2, proj)
        cab = next(r for r in reqs2 if r.category == "cs_cabinet")
        top, _ = match.shortlist(cab, load.load_catalog(HC / "catalog.toml"))
        self.assertEqual([m.candidate.model for m in top], ["Steelvault C5"])


class UrgentCareTests(unittest.TestCase):
    def test_no_facility_licence_and_houston_tax(self):
        _, proj, packs, _, _ = setup("urgent_care.toml")
        ids = {c["id"] for c in rulepack.checklist(packs, [], proj)}
        self.assertIn("TX-254.052", ids)
        self.assertNotIn("HHSC-509.143-POWER", ids)
        self.assertEqual(rulepack.tax_rate(packs, proj)[0], 0.0825)
        self.assertNotIn("TX-37.117-PANIC", ids)  # school rules stay out of clinics


if __name__ == "__main__":
    unittest.main()
