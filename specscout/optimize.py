"""Pick a vendor and model for every line so the whole order costs the least.

Cheapest-per-line is not the cheapest order: each vendor you add brings its own
shipping charge and minimum order. With a handful of vendors it is cheap to try
every combination of vendors exactly, so that is what this does.
"""
from __future__ import annotations

from itertools import combinations

from .model import Line, Match, Offer, Requirement, Vendor


def _shipping(v: Vendor, subtotal: float) -> float:
    if v.free_shipping_over is not None and subtotal >= v.free_shipping_over:
        return 0.0
    return v.shipping


def usable_offers(match: Match, offers: list[Offer], vendors: dict[str, Vendor],
                  max_lead_days: int | None) -> list[Offer]:
    out = []
    for o in offers:
        v = vendors.get(o.vendor)
        if o.model != match.candidate.model or v is None or not v.approved or not o.in_stock:
            continue
        if max_lead_days is not None and o.lead_days is not None and o.lead_days > max_lead_days:
            continue
        out.append(o)
    return out


def optimize(shortlists: dict[str, list[Match]], reqs: list[Requirement], offers: list[Offer],
             vendors: list[Vendor], max_lead_days: int | None = None,
             max_vendors: int | None = None) -> tuple[list[Line], dict[str, float], list[str]]:
    """Return (chosen lines, per-vendor shipping, requirement ids nobody can fill)."""
    vmap = {v.id: v for v in vendors}
    # (requirement, match, offer) options for each line
    options: dict[str, list[tuple[Match, Offer]]] = {}
    for r in reqs:
        opts = [(m, o) for m in shortlists.get(r.id, [])
                for o in usable_offers(m, offers, vmap, max_lead_days)]
        options[r.id] = opts
    unfillable = [r.id for r in reqs if not options[r.id]]
    fill = [r for r in reqs if options[r.id]]
    if not fill:
        return [], {}, unfillable

    used = sorted({o.vendor for opts in options.values() for _, o in opts})
    limit = min(len(used), max_vendors or len(used))
    if len(used) > 16:
        raise ValueError("more than 16 vendors: narrow the vendor list first")

    best = None
    for k in range(1, limit + 1):
        for subset in combinations(used, k):
            allowed = set(subset)
            picks = {}
            ok = True
            for r in fill:
                cands = [(m, o) for m, o in options[r.id] if o.vendor in allowed]
                if not cands:
                    ok = False
                    break
                # cheapest, then higher spec score, then shorter lead time
                picks[r.id] = min(cands, key=lambda mo: (mo[1].unit_price, -mo[0].score,
                                                         mo[1].lead_days or 0))
            if not ok:
                continue
            sub = {v: 0.0 for v in subset}
            for r in fill:
                sub[picks[r.id][1].vendor] += picks[r.id][1].unit_price * r.qty
            if any(0 < s < vmap[v].min_order for v, s in sub.items()):
                continue
            ship = {v: _shipping(vmap[v], s) for v, s in sub.items() if s > 0}
            total = sum(sub.values()) + sum(ship.values())
            key = (round(total, 2), len(ship))
            if best is None or key < best[0]:
                best = (key, picks, ship)
    if best is None:
        return [], {}, [r.id for r in reqs]

    _, picks, ship = best
    lines = []
    for r in fill:
        m, o = picks[r.id]
        alts = sorted((x for _, x in options[r.id] if x is not o), key=lambda x: x.unit_price)
        lines.append(Line(requirement=r, candidate=m.candidate, offer=o, alternatives=alts[:4]))
    return lines, ship, unfillable
