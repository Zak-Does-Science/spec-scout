"""Write the cost sheet: an Excel workbook with live formulas, plus a CSV copy."""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .model import Line, Match, Vendor

HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="2F4F4F")
WARN = PatternFill("solid", fgColor="FCE4D6")
MONEY = '"$"#,##0.00'

LINE_COLS = ["Item", "Requirement", "Qty", "Model", "Maker", "Vendor", "Unit price", "Extended",
             "Lead days", "Source", "Evidence", "Seen at", "URL", "Next best (vendor @ price)"]


def _header(ws, cols, widths):
    ws.append(cols)
    for i, w in enumerate(widths, start=1):
        c = ws.cell(row=1, column=i)
        c.font, c.fill = HEAD, FILL
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def write(path: Path, project: str, lines: list[Line], shipping: dict[str, float],
          vendors: list[Vendor], shortlists: dict[str, list[Match]],
          rejected: dict[str, list[Match]], unfillable: list[str],
          tax: tuple[float, str, str] = (0.0, "", ""), compliance: list[dict] | None = None,
          packs: list[dict] | None = None) -> None:
    vname = {v.id: v.name for v in vendors}
    wb = Workbook()

    ws = wb.active
    ws.title = "Cost sheet"
    _header(ws, LINE_COLS, [8, 30, 6, 22, 16, 20, 12, 13, 9, 11, 30, 22, 40, 34])
    for ln in lines:
        r = ws.max_row + 1
        o = ln.offer
        nxt = "; ".join(f"{vname.get(a.vendor, a.vendor)} {a.model} @ ${a.unit_price:,.2f}"
                        for a in ln.alternatives[:2])
        ws.append([ln.requirement.id, ln.requirement.name, ln.requirement.qty, ln.candidate.model,
                   ln.candidate.maker, vname.get(o.vendor, o.vendor), o.unit_price, f"=C{r}*G{r}",
                   o.lead_days, o.source, o.evidence, o.seen_at, o.url, nxt])
        ws.cell(row=r, column=7).number_format = MONEY
        ws.cell(row=r, column=8).number_format = MONEY
        if not o.evidence:
            for c in range(1, len(LINE_COLS) + 1):
                ws.cell(row=r, column=c).fill = WARN
    last = ws.max_row
    ws.append([])
    ws.append(["", "Items subtotal", "", "", "", "", "", f"=SUM(H2:H{last})"])
    sub_row = ws.max_row
    ws.append(["", "Shipping", "", "", "", "", "", "='Vendors'!D" + str(len(shipping) + 2)])
    rate, tax_label, tax_cite = tax
    ws.append(["", tax_label or "Sales tax", "", "", "", "", rate,
               f"=ROUND(H{sub_row}*G{sub_row + 2},2)", "", "", tax_cite])
    ws.cell(row=sub_row + 2, column=7).number_format = "0.00%"
    ws.append(["", "Order total", "", "", "", "", "", f"=H{sub_row}+H{sub_row + 1}+H{sub_row + 2}"])
    for rr in range(sub_row, sub_row + 4):
        ws.cell(row=rr, column=2).font = Font(bold=True)
        ws.cell(row=rr, column=8).number_format = MONEY
        ws.cell(row=rr, column=8).font = Font(bold=True)
    for rid in unfillable:
        ws.append([rid, "NO APPROVED OFFER: needs a manual quote"])
        ws.cell(row=ws.max_row, column=2).fill = WARN

    vs = wb.create_sheet("Vendors")
    _header(vs, ["Vendor", "Lines", "Subtotal", "Shipping", "Vendor total"], [24, 8, 14, 12, 14])
    for v, ship in sorted(shipping.items()):
        r = vs.max_row + 1
        nm = vname.get(v, v)
        vs.append([nm, f"=COUNTIF('Cost sheet'!F2:F{last},A{r})",
                   f"=SUMIF('Cost sheet'!F2:F{last},A{r},'Cost sheet'!H2:H{last})", ship, f"=C{r}+D{r}"])
    end = vs.max_row
    vs.append(["Total", f"=SUM(B2:B{end})", f"=SUM(C2:C{end})", f"=SUM(D2:D{end})", f"=SUM(E2:E{end})"])
    for row in vs.iter_rows(min_row=2, min_col=3, max_col=5):
        for c in row:
            c.number_format = MONEY

    ms = wb.create_sheet("Shortlists")
    _header(ms, ["Item", "Model", "Maker", "Result", "Score", "Why"], [8, 24, 16, 10, 8, 70])
    for rid, ms_list in shortlists.items():
        for m in ms_list:
            ms.append([rid, m.candidate.model, m.candidate.maker, "shortlist", m.score,
                       ", ".join(f"{k}={v}" for k, v in m.candidate.specs.items())])
        for m in rejected.get(rid, []):
            ms.append([rid, m.candidate.model, m.candidate.maker, "rejected", None, "; ".join(m.failures)])
    for row in ms.iter_rows(min_row=2):
        row[5].alignment = Alignment(wrap_text=True, vertical="top")

    if compliance is not None:
        cs = wb.create_sheet("Compliance")
        _header(cs, ["Status", "Kind", "Rule", "Title", "What to do", "Items", "Citation", "Source", "Pack"],
                [9, 12, 14, 30, 70, 12, 26, 40, 24])
        for row in compliance:
            cs.append([row["status"], row["kind"], row["id"], row["title"], row["text"], row["items"],
                       row["cite"], row["url"], row["pack"]])
            if row["status"] == "CHECK":
                for c in range(1, 10):
                    cs.cell(row=cs.max_row, column=c).fill = WARN
        for r in cs.iter_rows(min_row=2):
            for c in (r[3], r[4]):
                c.alignment = Alignment(wrap_text=True, vertical="top")

    info = wb.create_sheet("About")
    info.append(["Project", project])
    info.append(["Rule", "Every unit price must trace to a screenshot or a price-list row (Evidence column)."])
    info.append(["Rule", "Orange rows have no evidence and must be quoted by hand before purchase."])
    for pk in packs or []:
        meta = pk.get("pack", {})
        info.append(["Rule pack", f"{meta.get('name')} (checked {meta.get('as_of', '?')}). "
                                  f"{meta.get('disclaimer', '')}"])
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 10, 90
    wb.save(path)

    with open(path.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(LINE_COLS)
        for ln in lines:
            o = ln.offer
            w.writerow([ln.requirement.id, ln.requirement.name, ln.requirement.qty, ln.candidate.model,
                        ln.candidate.maker, vname.get(o.vendor, o.vendor), f"{o.unit_price:.2f}",
                        f"{ln.extended:.2f}", o.lead_days or "", o.source, o.evidence, o.seen_at, o.url, ""])
