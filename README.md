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

6. **Checks the local rules.** A project can load rule packs: local codes, laws and buying rules, each with its citation. They add hard rules to the matching step (a door controller without UL 294 never makes the shortlist), put a checklist of licences, permits and inspections on a Compliance tab, add sales tax unless the buyer is exempt, and flag order-level problems such as "this vendor has no co-op contract and the order is over the bid threshold".

## Every day

Prices move, stock runs out, and a sale ends on a Tuesday. `--daily` runs the job now and then again every morning (06:00 by default, or `--daily 05:30`). Each day's cost sheet and screenshots go in their own dated folder, and `changes.txt` lists every line whose pick or price changed since the day before, so the morning check takes a minute.

```
spec-scout run project.toml --catalog catalog.toml --vendors vendors.toml --live --daily
```

If you'd rather not leave a window open, run the same command without `--daily` from Windows Task Scheduler or cron once a day, pointing `--out` at a new dated folder each time.

## Houston low-voltage work, and schools in particular

`rulepacks/houston_k12_low_voltage.toml` is a rule pack for low-voltage projects in the Houston area (cameras, access control, fire alarm, panic alert, emergency responder radio, networks), with extra weight on Texas public schools. It reads a few facts from the project (`site_type`, `jurisdiction`, `tax_exempt`, `federal_funds`, `erate`, `in_floodplain`) and applies what fits:

- **Who can't sell you what.** Federal-funds and E-Rate exclusions (Huawei, ZTE, Hytera, Hikvision, Dahua), plus the Texas prohibited-hardware list as a default exclusion.
- **Equipment that has to carry a listing.** Inside City of Houston limits: UL 294 and fire-alarm release for access control on egress doors, fail-safe maglocks, UL 2524 / FCC / NEMA 4 signal boosters, UL 1037 key boxes. For schools: a UL 864 fire alarm with voice evacuation. For unincorporated Harris County: an addressable fire alarm.
- **School safety rules.** Silent panic alert that triggers on 9-1-1 calls, reports location and locks exterior doors (19 TAC 61.1031, TEC 37.117). Door numbering, entrance ID, radio coverage, a key box, and 3-month retention for special-ed classroom video (TEC 29.022) go on the checklist.
- **Who has to be licensed.** DPS Private Security for cameras, access control and intrusion; State Fire Marshal for fire alarm; and the point where low-voltage ends and an electrician and City permit begin.
- **How a school district has to buy.** The $100,000 competitive-procurement line (raised from $50,000 in September 2025), co-op contracts, the verification letters, federal thresholds, E-Rate Form 470, and the 8.25% sales tax that a district with form 01-339 doesn't pay.
- **The Houston ground itself.** In the floodplain, head-end gear goes at the 500-year elevation plus two feet.

Every rule carries its statute or code section and a link, and the date it was last checked. It's a planning aid, not legal advice. Codes change, and the city and the district's purchasing office have the last word.

Try it on a made-up elementary campus refresh:

```
spec-scout run examples/houston_school/project.toml --catalog examples/houston_school/catalog.toml --vendors examples/houston_school/vendors.toml --prices examples/houston_school/prices.csv
```

Writing a pack for another city is a matter of copying this one and changing the rules; the format is described at the top of `specscout/rulepack.py`.

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
| `rulepacks/*.toml` | Local codes, laws and buying rules (optional) |

All of them are plain text, so the specialist who writes the requirements doesn't need to know Python.

## What Claude did that this doesn't

In the original, Claude was the flexible part. It worked from the project's schematics and the infrastructure already on site, judged which models met the specialists' choices, and found the product pages itself. Here those steps are deliberate inputs (the catalog and the page list), so a run gives the same answer every time and anyone can audit it. A natural next step is to let a model fill `catalog.toml` from datasheet PDFs, with a person checking it before the rules run.

## Be a good guest

Only point `--live` at sites whose terms allow it, keep the request rate low, and use a vendor's API or price file when it offers one. Screenshots of a vendor's page are for your own procurement records.

## License

MIT
