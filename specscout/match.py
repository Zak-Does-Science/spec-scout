"""Check every catalog model against each requirement and rank the ones that pass.

Constraint forms, written under [item.require] in the project file:

    capacity_l   = { min = 50 }             numeric floor
    noise_db     = { max = 55 }             numeric ceiling
    voltage      = { eq = 120 }             exact value
    plug         = { in = ["NEMA 5-15"] }   one of these values
    standards    = { all = ["UL 61010-1"] } spec is a list that must contain all of these
    refrigerant  = { not_in = ["R-404A"] }  must not be (or, for a list spec, contain) any of these
"""
from __future__ import annotations

from .model import Candidate, Match, Requirement


def _check(name: str, rule: dict, value) -> str | None:
    """Return a failure message, or None if the value satisfies the rule."""
    if value is None:
        return f"{name}: not listed on datasheet"
    if "min" in rule and not (isinstance(value, (int, float)) and value >= rule["min"]):
        return f"{name}: {value} < required {rule['min']}"
    if "max" in rule and not (isinstance(value, (int, float)) and value <= rule["max"]):
        return f"{name}: {value} > allowed {rule['max']}"
    if "eq" in rule and value != rule["eq"]:
        return f"{name}: {value} != {rule['eq']}"
    if "in" in rule and value not in rule["in"]:
        return f"{name}: {value} not in {rule['in']}"
    if "not_in" in rule:
        banned = [v for v in (value if isinstance(value, list) else [value]) if v in rule["not_in"]]
        if banned:
            return f"{name}: {', '.join(map(str, banned))} is excluded"
    if "all" in rule:
        have = set(value if isinstance(value, list) else [value])
        missing = [s for s in rule["all"] if s not in have]
        if missing:
            return f"{name}: missing {', '.join(missing)}"
    return None


def evaluate(req: Requirement, cand: Candidate) -> Match:
    failures = [msg for name, rule in req.constraints.items()
                if (msg := _check(name, rule, cand.specs.get(name)))]
    return Match(req, cand, passed=not failures, failures=failures, score=0.0)


def _rank(matches: list[Match], prefer: dict[str, str]) -> None:
    """Score passing models 0-100 on the preferred specs (min-max scaled, averaged)."""
    for m in matches:
        m.score = 0.0
    if not prefer or not matches:
        return
    for spec, direction in prefer.items():
        vals = [m.candidate.specs.get(spec) for m in matches]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if not nums:
            continue
        lo, hi = min(nums), max(nums)
        for m, v in zip(matches, vals):
            if not isinstance(v, (int, float)):
                continue
            frac = 1.0 if hi == lo else (v - lo) / (hi - lo)
            if direction == "low":
                frac = 1.0 - frac
            m.score += 100.0 * frac / len(prefer)
    for m in matches:
        m.score = round(m.score, 1)


def shortlist(req: Requirement, catalog: list[Candidate]) -> tuple[list[Match], list[Match]]:
    """Return (shortlisted passing matches, rejected matches with reasons)."""
    results = [evaluate(req, c) for c in catalog if c.category == req.category]
    passing = [m for m in results if m.passed]
    rejected = [m for m in results if not m.passed]
    _rank(passing, req.prefer)
    passing.sort(key=lambda m: -m.score)
    return passing[: req.shortlist], rejected
