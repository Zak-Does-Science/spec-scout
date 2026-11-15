# spec-scout

Give it a project's item list, written as requirements and standards. It hands back a shortlist of models that actually meet them, a priced cost sheet that buys from the cheapest mix of approved vendors, and a timestamped screenshot behind every price so procurement can check the work.

## Why it exists

At a company I worked for, I was the one bringing AI into the workplace, and our most experienced specialists sat in Europe. They would send me the hard part of a project in requirement form: this much capacity, this voltage, these safety listings, not that refrigerant. My job was to turn each line into something we could actually buy. That meant reading datasheets until one fit, finding who sold it, comparing prices across our vendors, and packaging it so procurement would sign off. A spreadsheet of numbers isn't proof. Procurement wanted to see the page the price came from.

Doing that by hand is a slow loop, and the prices move while you work. So I built a Claude add-on that did the loop for me. It checked models against the requirements and the standards, shortlisted the ones that passed, then used Claude's browser control to shop them in real time. It filled the cost sheet as it went and screenshotted each product page so procurement could verify every line against their existing standards.

That add-on lived inside the company, and its code and data stayed there. This repository is a fresh rebuild of the same idea, written to run on its own, outside Claude, with made-up products and vendors.

## What it does

1. **Matches.** Each item on the list has hard rules (`min`, `max`, `eq`, `in`, `not_in`, and `all` for "must carry every one of these certifications"). Every model in the catalog is checked against them. Rejected models keep their reasons ("noise_db: 58 > allowed 55"), which is the part people usually ask about.
2. **Ranks.** Models that pass are scored on the specs you said you care about (`prefer.kwh_per_day = "low"`) and cut to a shortlist.
3. **Prices.** Offers come from vendor price lists (CSV), from live product pages, or both. A live page is read by a real browser: it takes the price from the page's schema.org data if it has any, and from a CSS selector if it doesn't. It stamps the URL and the time across the top of the page and saves a full-page screenshot, plus a SHA-256 hash of it, to `out/evidence/`.
4. **Optimizes.** Buying every line wherever it's cheapest isn't always the cheapest order, because each extra vendor adds a shipping charge, a minimum order and another invoice. spec-scout tries every combination of approved vendors, buys each line at its cheapest price within that set, and keeps the cheapest total. Vendors that aren't approved, items out of stock and offers past your lead-time limit never make it in.
5. **Writes the cost sheet.** You get an Excel workbook with live formulas, so procurement can change a quantity and watch the total move. It has four tabs: Cost sheet, Vendors, Shortlists (including the rejects and why), and About. You also get a CSV copy. Any line without evidence is shaded so nobody buys from it without a quote.

`--every 30` re-runs the whole thing every 30 minutes, which is the "real time" part when prices are moving.

## Try it

```
pip install -e .
spec-scout run examples/lab_fitout.toml --catalog examples/catalog.toml --vendors examples/vendors.toml --prices examples/prices.csv
```

For live pages and screenshots:

```
pip install -e ".[web]"
playwright install chromium
spec-scout run examples/lab_fitout.toml --catalog examples/catalog.toml --vendors examples/vendors.toml --prices examples/prices.csv --live
```

The example fits out a small molecular-biology lab with five lines: centrifuges, a -80 freezer, a UPS for that freezer, network switches and pipettes. The demo vendor pages in `examples/vendor_pages/` are local HTML files, so it runs offline and never touches a real store. A few of them show sale prices that beat the price list, so you can watch a live price replace a stale one. One is backordered. And one vendor, QuickBuy, is cheapest on paper but isn't approved, so it never wins.

Tests: `python -m unittest discover -s tests -t .`

## Files you edit

| File | What goes in it |
|---|---|
| `project.toml` | The item list: quantity, category, hard rules, preferences |
| `catalog.toml` | Models and their datasheet specs |
| `vendors.toml` | Approved vendors, their shipping terms and minimums, product page URLs |
| `prices.csv` | Any price lists or quotes you already have |

All of them are plain text, so the specialist who writes the requirements doesn't need to know Python.

## What Claude did that this doesn't

In the original, Claude was the flexible part. It worked from the project's schematics and the infrastructure already on site, judged which models met the specialists' choices, and found the product pages itself. Here those steps are deliberate inputs (the catalog and the page list), so a run gives the same answer every time and anyone can audit it. A natural next step is to let a model fill `catalog.toml` from datasheet PDFs, with a person checking it before the rules run.

## Be a good guest

Only point `--live` at sites whose terms allow it, keep the request rate low, and use a vendor's API or price file when it offers one. Screenshots of a vendor's page are for your own procurement records.

## License

MIT
