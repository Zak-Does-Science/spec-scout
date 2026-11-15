"""Command line: spec-scout run <project.toml> --catalog ... --vendors ... [--prices ...] [--live] [--daily]"""
from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import load, match, optimize, rulepack, sheet


def run_once(a, out_dir: Path) -> int:
    project, reqs, proj = load.load_project_full(a.project)
    packs = [rulepack.load_pack(p) for p in proj["rulepacks"]]
    rulepack.apply_rules(packs, reqs, proj)
    for pk in packs:
        print(f"Rule pack: {pk['pack']['name']} (checked {pk['pack'].get('as_of', '?')})")
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
        web, log = capture.capture(todo, vendors, out_dir, headless=not a.show)
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
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{a.project.stem}_cost_sheet.xlsx"
    items = sum(ln.extended for ln in lines)
    shipping = sum(ship.values())
    rate, tax_label, tax_cite = rulepack.tax_rate(packs, proj)
    tax = round(items * rate, 2)
    total = items + shipping + tax
    compliance = None
    if packs:
        compliance = (rulepack.checklist(packs, reqs, proj)
                      + rulepack.order_checks(packs, proj, lines, vendors, total))
    sheet.write(out, project, lines, ship, vendors, shortlists, rejected, unfillable,
                tax=(rate, tax_label, tax_cite), compliance=compliance, packs=packs)

    print(f"\n{project}: {len(lines)} lines from {len(ship)} vendor(s)")
    print(f"  items ${items:,.2f} + shipping ${shipping:,.2f} + tax ${tax:,.2f} = ${total:,.2f}")
    if compliance:
        flagged = sum(1 for c in compliance if c["status"] == "CHECK")
        print(f"  compliance: {len(compliance)} checklist items, {flagged} flagged for review")
    for rid in unfillable:
        print(f"  ! {rid}: no approved, in-stock offer for any shortlisted model")
    print(f"  wrote {out} and {out.with_suffix('.csv').name}")
    return 1 if unfillable else 0


def _read_prices(csv_path: Path) -> dict[str, tuple[str, str, float]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {r["Item"]: (r["Vendor"], r["Model"], float(r["Unit price"])) for r in csv.DictReader(f)}


def compare_days(prev: Path, cur: Path, out: Path) -> list[str]:
    """Write and return the lines whose pick or price changed since the previous run."""
    old, new = _read_prices(prev), _read_prices(cur)
    changes = []
    for item, (v, m, p) in new.items():
        if item not in old:
            changes.append(f"{item}: new line, {m} from {v} at ${p:,.2f}")
        elif old[item] != (v, m, p):
            ov, om, op = old[item]
            changes.append(f"{item}: {om} from {ov} at ${op:,.2f} -> {m} from {v} at ${p:,.2f}")
    for item in sorted(old.keys() - new.keys()):
        changes.append(f"{item}: no longer fillable")
    out.write_text("\n".join(changes or ["No changes since the last run."]) + "\n", encoding="utf-8")
    return changes


def run_daily(a) -> int:
    hh, mm = (int(x) for x in a.daily.split(":"))
    print(f"Running now, then every day at {hh:02d}:{mm:02d}. Ctrl+C to stop.")
    while True:
        day = datetime.now().strftime("%Y-%m-%d")
        out_dir = a.out / day
        run_once(a, out_dir)
        stem = f"{a.project.stem}_cost_sheet.csv"
        earlier = sorted(p for p in a.out.glob(f"*/{stem}") if p.parent.name < day)
        if earlier and (out_dir / stem).exists():
            changes = compare_days(earlier[-1], out_dir / stem, out_dir / "changes.txt")
            print(f"  {len(changes)} change(s) since {earlier[-1].parent.name}; see {out_dir / 'changes.txt'}")
        now = datetime.now()
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        print(f"-- next run {nxt:%a %d %b %H:%M}\n")
        time.sleep((nxt - now).total_seconds())


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
    r.add_argument("--daily", nargs="?", const="06:00", metavar="HH:MM",
                   help="keep running and repeat every day at this local time (default 06:00); "
                        "each day's results go in their own dated folder with a changes.txt")
    r.add_argument("--out", type=Path, default=Path("out"))
    a = ap.parse_args(argv)
    if a.daily:
        return run_daily(a)
    return run_once(a, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
