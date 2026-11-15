"""Command line: spec-scout run <project.toml> --catalog ... --vendors ... [--prices ...] [--live]"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import load, match, optimize, sheet


def run_once(a) -> int:
    project, reqs = load.load_project(a.project)
    catalog = load.load_catalog(a.catalog)
    vendors, pages = load.load_vendors(a.vendors)

    shortlists, rejected = {}, {}
    for r in reqs:
        shortlists[r.id], rejected[r.id] = match.shortlist(r, catalog)
        print(f"[{r.id}] {r.name}: {len(shortlists[r.id])} shortlisted, {len(rejected[r.id])} rejected")

    offers = []
    for p in a.prices or []:
        offers += load.load_price_list(p)
    if a.live:
        from . import capture
        wanted = {m.candidate.model for ms in shortlists.values() for m in ms}
        todo = [p for p in pages if p["model"] in wanted]
        print(f"Checking {len(todo)} product pages live (skipping {len(pages) - len(todo)} "
              "for models that did not make a shortlist)...")
        web, log = capture.capture(todo, vendors, a.out, headless=not a.show)
        errs = [e for e in log if "error" in e]
        print(f"  {len(web)} prices captured, {len(errs)} pages failed")
        for e in errs:
            print(f"  ! {e['vendor']} {e['model']}: {e['error']}")
        # a live price replaces the price-list price for the same vendor and model
        live_keys = {(o.vendor, o.model) for o in web}
        offers = [o for o in offers if (o.vendor, o.model) not in live_keys] + web

    lines, ship, unfillable = optimize.optimize(shortlists, reqs, offers, vendors,
                                                max_lead_days=a.max_lead_days,
                                                max_vendors=a.max_vendors)
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"{a.project.stem}_cost_sheet.xlsx"
    sheet.write(out, project, lines, ship, vendors, shortlists, rejected, unfillable)

    items = sum(ln.extended for ln in lines)
    shipping = sum(ship.values())
    print(f"\n{project}: {len(lines)} lines from {len(ship)} vendor(s)")
    print(f"  items ${items:,.2f} + shipping ${shipping:,.2f} = ${items + shipping:,.2f}")
    for rid in unfillable:
        print(f"  ! {rid}: no approved, in-stock offer for any shortlisted model")
    print(f"  wrote {out} and {out.with_suffix('.csv').name}")
    return 1 if unfillable else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="spec-scout",
                                 description="Turn a requirements list into a priced, evidenced cost sheet.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="match, price and optimize a project")
    r.add_argument("project", type=Path)
    r.add_argument("--catalog", type=Path, required=True, help="models and their specs (TOML)")
    r.add_argument("--vendors", type=Path, required=True, help="approved vendors and product pages (TOML)")
    r.add_argument("--prices", type=Path, action="append", help="vendor price list CSV (repeatable)")
    r.add_argument("--live", action="store_true", help="read prices from product pages and screenshot them")
    r.add_argument("--show", action="store_true", help="show the browser while it works")
    r.add_argument("--max-lead-days", type=int)
    r.add_argument("--max-vendors", type=int, help="cap how many vendors the order may use")
    r.add_argument("--every", type=float, metavar="MIN", help="re-run every MIN minutes until stopped")
    r.add_argument("--out", type=Path, default=Path("out"))
    a = ap.parse_args(argv)
    if a.every:
        while True:
            run_once(a)
            print(f"-- next run in {a.every:g} min (Ctrl+C to stop)\n")
            time.sleep(a.every * 60)
    return run_once(a)


if __name__ == "__main__":
    raise SystemExit(main())
