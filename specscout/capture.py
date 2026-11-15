"""Open vendor product pages in a real browser, read the price, and keep a screenshot.

The screenshot is the point: procurement can check every number on the cost sheet
against what the vendor's page actually said, when, and at what address. A banner
with the URL and timestamp is stamped onto the page before the shot is taken.

Needs the optional extra:  pip install "spec-scout[web]"  then  playwright install chromium
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .model import Offer, Vendor

PRICE_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)")

BANNER_JS = """(text) => {
  const b = document.createElement('div');
  b.textContent = text;
  b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;' +
    'background:#111;color:#fff;font:13px/1.4 monospace;padding:6px 10px;';
  document.body.appendChild(b);
}"""


def _price_from_jsonld(blobs: list[str]) -> tuple[float | None, bool | None]:
    """Find a schema.org Offer price in the page's JSON-LD blocks."""
    def walk(node):
        if isinstance(node, list):
            for n in node:
                yield from walk(n)
        elif isinstance(node, dict):
            if "price" in node:
                yield node
            for v in node.values():
                if isinstance(v, (dict, list)):
                    yield from walk(v)
    for blob in blobs:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for offer in walk(data):
            try:
                price = float(str(offer["price"]).replace(",", ""))
            except ValueError:
                continue
            avail = str(offer.get("availability", ""))
            stock = None if not avail else ("InStock" in avail or "LimitedAvailability" in avail)
            return price, stock
    return None, None


def parse_price_text(text: str) -> float | None:
    m = PRICE_RE.search(text or "")
    return float(m.group(1).replace(",", "")) if m else None


def capture(pages: list[dict], vendors: list[Vendor], out_dir: Path,
            headless: bool = True, timeout_ms: int = 30000) -> tuple[list[Offer], list[dict]]:
    """Visit each page entry ({vendor, model, url, lead_days?}); return offers and an evidence log."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover - depends on the optional extra
        raise SystemExit('Live pricing needs Playwright: pip install "spec-scout[web]" '
                         "and then: playwright install chromium") from e

    vmap = {v.id: v for v in vendors}
    shots = out_dir / "evidence"
    shots.mkdir(parents=True, exist_ok=True)
    offers, log = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for i, p in enumerate(pages, start=1):
            vendor = vmap.get(p["vendor"])
            entry = {"vendor": p["vendor"], "model": p["model"], "url": p["url"]}
            try:
                page.goto(p["url"], timeout=timeout_ms, wait_until="domcontentloaded")
                page.wait_for_timeout(500)
                blobs = page.locator('script[type="application/ld+json"]').all_text_contents()
                price, stock = _price_from_jsonld(blobs)
                how = "schema.org JSON-LD"
                if price is None and vendor and vendor.price_selector:
                    el = page.locator(vendor.price_selector).first
                    price = parse_price_text(el.inner_text(timeout=5000))
                    how = f"selector {vendor.price_selector}"
                seen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                page.evaluate(BANNER_JS, f"{seen}  |  {p['url']}  |  spec-scout capture")
                safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{p['vendor']}_{p['model']}")[:80]
                shot = shots / f"{i:03d}_{safe}.png"
                page.screenshot(path=str(shot), full_page=True)
                digest = hashlib.sha256(shot.read_bytes()).hexdigest()
                entry.update(seen_at=seen, price=price, in_stock=stock, method=how,
                             screenshot=shot.relative_to(out_dir).as_posix(), sha256=digest)
                if price is not None:
                    offers.append(Offer(vendor=p["vendor"], model=p["model"], unit_price=price,
                                        in_stock=True if stock is None else stock,
                                        lead_days=p.get("lead_days"), url=p["url"], source="web",
                                        evidence=entry["screenshot"], seen_at=seen))
                else:
                    entry["error"] = "no price found on page"
            except Exception as e:  # keep going; one bad page should not sink the run
                entry["error"] = f"{type(e).__name__}: {e}"
            log.append(entry)
        browser.close()
    (out_dir / "evidence" / "manifest.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    return offers, log
