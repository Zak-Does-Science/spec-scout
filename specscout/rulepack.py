"""Rule packs: local codes, laws and buying rules layered on top of a project.

A rule pack is a TOML file a project lists under [project] rulepacks = [...].
It can hold four kinds of entries, each with a citation:

  [[rule]]        hard equipment rules added to every item in the named categories
                  (spec requirements and/or banned makers). Failures name the rule id.
  [[check]]       checklist items (licences, permits, inspections, signage, records)
                  that land on the Compliance tab when a matching category is on the list.
  [tax]           a sales-tax rate added to the cost sheet unless the project is exempt.
  [[order_rule]]  rules about the order as a whole, such as "over this total, buy through
                  a purchasing co-op contract". Broken ones are flagged on the Compliance tab.

`when` limits an entry to some projects, matched against the [project] table:
  when = { site_type = ["k12", "higher_ed"] }   any listed value matches
  when = { tax_exempt = false }                  exact value
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from .model import Line, Requirement, Vendor


def load_pack(path: Path) -> dict:
    with open(path, "rb") as f:
        d = tomllib.load(f)
    d.setdefault("pack", {}).setdefault("name", path.stem)
    return d


def applies(when: dict | None, project: dict) -> bool:
    for key, want in (when or {}).items():
        have = project.get(key)
        if isinstance(want, list):
            if have not in want:
                return False
        elif have != want:
            return False
    return True


def _cats_match(cats: list[str] | None, category: str) -> bool:
    return not cats or "*" in cats or category in cats


def apply_rules(packs: list[dict], reqs: list[Requirement], project: dict) -> None:
    for pack in packs:
        for rule in pack.get("rule", []):
            if not applies(rule.get("when"), project):
                continue
            for r in reqs:
                if not _cats_match(rule.get("categories"), r.category):
                    continue
                for spec, cond in rule.get("require", {}).items():
                    r.pack_rules.append((rule["id"], spec, cond))
                if rule.get("banned_makers"):
                    r.banned_makers.append((rule["id"], list(rule["banned_makers"])))


def checklist(packs: list[dict], reqs: list[Requirement], project: dict) -> list[dict]:
    rows = []
    for pack in packs:
        for c in pack.get("check", []):
            if not applies(c.get("when"), project):
                continue
            items = [r.id for r in reqs if _cats_match(c.get("categories"), r.category)]
            if c.get("categories") and not items:
                continue
            rows.append({"pack": pack["pack"]["name"], "id": c["id"], "kind": c.get("kind", ""),
                         "title": c.get("title", ""), "text": c.get("text", ""),
                         "items": ", ".join(items) if c.get("categories") else "whole project",
                         "cite": c.get("cite", ""), "url": c.get("url", ""), "status": "to do"})
    return rows


def tax_rate(packs: list[dict], project: dict) -> tuple[float, str, str]:
    """Return (rate, label, citation); rate 0 when exempt or no pack sets one."""
    for pack in packs:
        t = pack.get("tax")
        if not t:
            continue
        if applies(t.get("exempt_when"), project) and t.get("exempt_when"):
            return 0.0, f"Sales tax (exempt: {t.get('exempt_note', 'see citation')})", t.get("cite", "")
        return float(t["rate"]), t.get("label", "Sales tax"), t.get("cite", "")
    return 0.0, "", ""


def order_checks(packs: list[dict], project: dict, lines: list[Line],
                 vendors: list[Vendor], order_total: float) -> list[dict]:
    vmap = {v.id: v for v in vendors}
    by_vendor: dict[str, float] = {}
    for ln in lines:
        by_vendor[ln.offer.vendor] = by_vendor.get(ln.offer.vendor, 0.0) + ln.extended
    rows = []
    for pack in packs:
        for o in pack.get("order_rule", []):
            if not applies(o.get("when"), project):
                continue
            basis = order_total if o.get("basis", "order") == "order" else None
            attr = o.get("require_vendor_attr")
            # optional: only vendors supplying lines in these categories
            cats = o.get("categories")
            in_scope = {ln.offer.vendor for ln in lines if _cats_match(cats, ln.requirement.category)}
            for vid, spend in by_vendor.items():
                if vid not in in_scope:
                    continue
                amount = basis if basis is not None else spend
                if amount < float(o.get("min_total", 0)):
                    continue
                v = vmap.get(vid)
                ok = bool(v and attr and v.attrs.get(attr))
                rows.append({"pack": pack["pack"]["name"], "id": o["id"], "kind": "procurement",
                             "title": o.get("title", ""),
                             "text": o.get("text", "") + f" Vendor: {v.name if v else vid}, "
                                     f"${amount:,.2f}. " + (f"Has {attr}: {v.attrs.get(attr)}." if ok
                                                           else f"No '{attr}' on file for this vendor."),
                             "items": vid, "cite": o.get("cite", ""), "url": o.get("url", ""),
                             "status": "ok" if ok else "CHECK"})
    return rows
