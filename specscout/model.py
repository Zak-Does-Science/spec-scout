"""Plain data types shared by every stage of the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Requirement:
    """One line on the project's item list, as the specialists wrote it."""
    id: str
    name: str
    qty: int
    category: str
    constraints: dict[str, dict[str, Any]] = field(default_factory=dict)
    prefer: dict[str, str] = field(default_factory=dict)  # spec -> "high" | "low"
    shortlist: int = 3
    notes: str = ""
    # filled in by rule packs: (label, spec, rule) and (label, [maker names])
    pack_rules: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    banned_makers: list[tuple[str, list[str]]] = field(default_factory=list)


@dataclass
class Candidate:
    """A specific make and model with its published specs."""
    model: str
    maker: str
    category: str
    specs: dict[str, Any] = field(default_factory=dict)
    datasheet: str = ""


@dataclass
class Match:
    requirement: Requirement
    candidate: Candidate
    passed: bool
    failures: list[str]
    score: float


@dataclass
class Vendor:
    id: str
    name: str
    approved: bool = True
    shipping: float = 0.0
    free_shipping_over: float | None = None
    min_order: float = 0.0
    price_selector: str = ""  # CSS selector used when a page has no schema.org price
    attrs: dict[str, Any] = field(default_factory=dict)  # e.g. hub = true, contracts = ["BuyBoard ..."]


@dataclass
class Offer:
    vendor: str
    model: str
    unit_price: float
    in_stock: bool = True
    lead_days: int | None = None
    url: str = ""
    source: str = "price list"  # "price list" or "web"
    evidence: str = ""  # screenshot path, or the price-list file and row
    seen_at: str = ""


@dataclass
class Line:
    """The chosen buy for one requirement."""
    requirement: Requirement
    candidate: Candidate
    offer: Offer
    alternatives: list[Offer] = field(default_factory=list)

    @property
    def extended(self) -> float:
        return round(self.offer.unit_price * self.requirement.qty, 2)
