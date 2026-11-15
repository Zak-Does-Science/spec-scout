"""Read the project, catalog, vendor and price-list files.

Everything is TOML or CSV so a non-programmer can edit it in a text editor or Excel.
"""
from __future__ import annotations

import csv
import tomllib
from pathlib import Path

from .model import Candidate, Offer, Requirement, Vendor


def _toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_project(path: Path) -> tuple[str, list[Requirement]]:
    return load_project_full(path)[:2]


def load_project_full(path: Path) -> tuple[str, list[Requirement], dict]:
    """Return (name, requirements, the whole [project] table with rule-pack paths resolved)."""
    d = _toml(path)
    reqs = []
    for r in d.get("item", []):
        reqs.append(Requirement(
            id=str(r["id"]),
            name=r["name"],
            qty=int(r.get("qty", 1)),
            category=r["category"],
            constraints=r.get("require", {}),
            prefer=r.get("prefer", {}),
            shortlist=int(r.get("shortlist", 3)),
            notes=r.get("notes", ""),
        ))
    ids = [r.id for r in reqs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: item ids must be unique")
    proj = dict(d.get("project", {}))
    proj["rulepacks"] = [(path.parent / p).resolve() for p in proj.get("rulepacks", [])]
    return proj.get("name", path.stem), reqs, proj


def load_catalog(path: Path) -> list[Candidate]:
    d = _toml(path)
    return [Candidate(model=c["model"], maker=c.get("maker", ""), category=c["category"],
                      specs=c.get("specs", {}), datasheet=c.get("datasheet", ""))
            for c in d.get("model", [])]


_VENDOR_KEYS = {"id", "name", "approved", "shipping", "free_shipping_over", "min_order", "price_selector"}


def load_vendors(path: Path) -> tuple[list[Vendor], list[dict]]:
    """Return the vendors and the list of product pages to check live."""
    d = _toml(path)
    vendors = [Vendor(id=v["id"], name=v.get("name", v["id"]), approved=v.get("approved", True),
                      shipping=float(v.get("shipping", 0)),
                      free_shipping_over=v.get("free_shipping_over"),
                      min_order=float(v.get("min_order", 0)),
                      price_selector=v.get("price_selector", ""),
                      attrs={k: x for k, x in v.items() if k not in _VENDOR_KEYS})
               for v in d.get("vendor", [])]
    pages = d.get("page", [])
    for p in pages:  # a bare path (like the bundled examples) is read relative to this file
        if "://" not in p["url"]:
            p["url"] = (path.parent / p["url"]).resolve().as_uri()
    return vendors, pages


def load_price_list(path: Path) -> list[Offer]:
    """CSV columns: vendor, model, unit_price, in_stock, lead_days, url."""
    offers = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if not (row.get("vendor") and row.get("model") and row.get("unit_price")):
                continue
            offers.append(Offer(
                vendor=row["vendor"].strip(),
                model=row["model"].strip(),
                unit_price=float(str(row["unit_price"]).replace("$", "").replace(",", "")),
                in_stock=str(row.get("in_stock", "yes")).strip().lower() not in ("no", "false", "0", ""),
                lead_days=int(row["lead_days"]) if (row.get("lead_days") or "").strip() else None,
                url=(row.get("url") or "").strip(),
                source="price list",
                evidence=f"{path.name} row {i}",
            ))
    return offers
