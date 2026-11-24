"""A first draft of GSTR-9 from the portal files, every line with where its figure came from.

This is a working draft for staff to review, not the return. Each line is one of:
  draft   worked out from the filed returns, source stated
  needs   cannot be worked out from what is in the folder (says what is needed); never shown as zero
  check   worked out, but a rule of thumb was used and staff must confirm the split

A draft is only offered when GSTR-1 summary and GSTR-3B are present for all 12 months.
"""
from decimal import Decimal

from .portal import TAXES, ZERO, month_name, months, next_months

COLS = ("taxable",) + TAXES


def _zero():
    return {k: ZERO for k in COLS}


def _sum(rows):
    out = _zero()
    for r in rows:
        for k in COLS:
            out[k] += (r or {}).get(k) or ZERO
    return out


def _neg(a):
    return {k: -(v or ZERO) for k, v in a.items()}


def _any(a):
    return any((v or ZERO) != ZERO for v in a.values())


def build(fy, data):
    """data: {kind: {period: figures}} -> dict(ready, missing, lines=[...], totals={...})."""
    mon = months(fy)
    g1, g3, g2 = data.get("gstr1_summary") or {}, data.get("gstr3b") or {}, data.get("gstr2b") or {}
    missing = [("GSTR-1 summary", [month_name(p) for p in mon if p not in g1]), ("GSTR-3B", [month_name(p) for p in mon if p not in g3])]
    missing = [(k, v) for k, v in missing if v]
    if missing:
        return dict(ready=False, missing=missing, lines=[], totals={})

    def sec(*names):   # a GSTR-1 section over the year
        return _sum(g1[p].get(n) for p in mon for n in names)

    def b3(key):       # a GSTR-3B 3.1 row over the year
        return _sum(g3[p].get(key) for p in mon)

    def itc(group, ty=None):   # GSTR-3B table 4 rows over the year (tax only)
        rows = [v for p in mon for t, v in (g3[p].get(group) or {}).items() if ty is None or t == ty]
        return dict(_sum(rows), taxable=None)

    # older summaries have only the B2B total, without its 4A / 4B / 6B / 6C parts
    reg_b2b = _sum(g1[p].get("B2B_4A") if "B2B_4A" in g1[p] else g1[p].get("B2B") for p in mon)
    lines = []

    def add(table, label, amounts, source, state="draft", note=""):
        lines.append(dict(table=table, label=label, amounts=amounts, source=source, state=state, note=note))

    def need(table, label, what):
        add(table, label, None, what, "needs")

    # ---------------- table 4: supplies on which tax is payable
    b2c = sec("B2CS", "B2CL", "CDNUR")
    add("4A", "Supplies to unregistered persons (B2C)", b2c, "GSTR-1 tables 5 and 7, less notes to unregistered persons (9B), 12 months")
    add("4B", "Supplies to registered persons (B2B)", reg_b2b, "GSTR-1 table 4A, 12 months")
    exp, sezwp, deemed = sec("EXP"), sec("B2B_SEZWP"), sec("B2B_6C")
    paid = sum((exp[k] for k in TAXES), ZERO) != ZERO
    if _any(exp):
        add("4C" if paid else "5A", "Exports %s payment of tax" % ("with" if paid else "without"), exp, "GSTR-1 table 6A, 12 months", "check",
            "The summary does not split exports with and without payment of tax: confirm the split between 4C and 5A.")
    add("4D", "Supplies to SEZ with payment of tax", sezwp, "GSTR-1 table 6B (with payment), 12 months")
    add("4E", "Deemed exports", deemed, "GSTR-1 table 6C, 12 months")
    adv = _sum([sec("AT"), _neg(sec("TXPD"))])
    add("4F", "Advances on which tax is paid and no invoice issued", adv, "GSTR-1 table 11A less 11B, 12 months")
    rcm = b3("rcm")
    add("4G", "Inward supplies on which tax is paid on reverse charge", rcm, "GSTR-3B table 3.1(d), 12 months")
    h = _sum([b2c, reg_b2b, exp if paid else None, sezwp, deemed, adv, rcm])
    notes = sec("CDNR")
    credit = sum(notes.values(), ZERO) < ZERO
    add("4I" if credit else "4J", "%s notes for supplies in 4B to 4E" % ("Credit" if credit else "Debit"), _neg(notes) if credit else notes,
        "GSTR-1 table 9B (registered), 12 months, net", "check" if _any(notes) else "draft",
        "The summary nets credit and debit notes: split them between 4I and 4J from the invoice detail." if _any(notes) else "")
    amend = sec("B2BA", "B2CLA", "B2CSA", "EXPA", "CDNRA", "CDNURA", "ATA", "TXPDA")
    up = sum(amend.values(), ZERO) >= ZERO
    add("4K" if up else "4L", "Supplies %s through amendments" % ("declared" if up else "reduced"), amend if up else _neg(amend),
        "GSTR-1 tables 9A, 9C, 10 and 11 amendments, 12 months, net", "check" if _any(amend) else "draft",
        "Amendments are netted here: an upward one goes in 4K and a downward one in 4L." if _any(amend) else "")
    n4 = _sum([h, notes, amend])
    add("4N", "Supplies and advances on which tax is to be paid", n4, "4A to 4G, less 4I, plus 4J, plus 4K, less 4L")

    # ---------------- table 5: supplies on which tax is not payable
    sezwop, out_rcm = sec("B2B_SEZWOP"), sec("B2B_4B")
    add("5B", "Supplies to SEZ without payment of tax", sezwop, "GSTR-1 table 6B (without payment), 12 months")
    add("5C", "Supplies on which the recipient pays tax on reverse charge", dict(out_rcm, **{k: ZERO for k in TAXES}), "GSTR-1 table 4B, 12 months")
    nil = [g1[p].get("NIL") or {} for p in mon]
    three_b = b3("nil_exempt")["taxable"], b3("non_gst")["taxable"]
    if all(n.get("split") for n in nil):
        for t, label, key in (("5D", "Exempted supplies", "exempt"), ("5E", "Nil rated supplies", "nil_rated"), ("5F", "Non-GST supplies", "non_gst")):
            add(t, label, dict(_zero(), taxable=sum((n[key] for n in nil), ZERO)), "GSTR-1 table 8, 12 months")
    elif three_b[0] or three_b[1]:
        add("5D, 5E", "Exempted and nil rated supplies", dict(_zero(), taxable=three_b[0]), "GSTR-3B table 3.1(c), 12 months", "check",
            "GSTR-3B shows exempt and nil rated together: split them between 5D and 5E.")
        add("5F", "Non-GST supplies", dict(_zero(), taxable=three_b[1]), "GSTR-3B table 3.1(e), 12 months")
    else:
        for t, label in (("5D", "Exempted supplies"), ("5E", "Nil rated supplies"), ("5F", "Non-GST supplies")):
            add(t, label, _zero(), "GSTR-1 table 8 and GSTR-3B 3.1(c) and (e) are nil for 12 months")
    exempt = _sum(l["amounts"] for l in lines if l["table"][:2] in ("5D", "5E", "5F"))
    m5 = _sum([exp if not paid else None, sezwop, out_rcm, exempt])
    m5 = dict(m5, **{k: ZERO for k in TAXES})
    add("5M", "Turnover on which tax is not to be paid", m5, "5A to 5F (credit notes and amendments on these, 5H to 5K, to be added from the invoice detail)")
    turnover = n4["taxable"] + m5["taxable"] - rcm["taxable"]
    add("5N", "Total turnover including advances", dict(_sum([n4, m5]), taxable=n4["taxable"] + m5["taxable"]), "4N plus 5M")

    # ---------------- table 6: ITC availed
    a6 = itc("itc_availed")
    add("6A", "Total ITC availed through GSTR-3B", a6, "GSTR-3B table 4(A), 12 months (filled by the portal)")
    oth = itc("itc_availed", "OTH")
    add("6B", "Inward supplies, other than imports and reverse charge", oth, "GSTR-3B table 4(A)(5), 12 months", "check",
        "Split between inputs, capital goods and input services from the books (Tally purchase and expense ledgers).")
    isrc = itc("itc_availed", "ISRC")
    reg = dict(_sum(g2[p].get("rcm") for p in mon if p in g2), taxable=None)
    if all(p in g2 for p in mon):
        unreg = {k: (isrc[k] - reg[k] if k in TAXES else None) for k in COLS}
        st = "check" if any(unreg[k] < ZERO for k in TAXES) else "draft"
        add("6C", "Reverse charge ITC, supplies from unregistered persons", unreg, "GSTR-3B table 4(A)(3) less reverse charge supplies in GSTR-2B", st,
            "Negative: less reverse charge ITC was taken than GSTR-2B shows for registered suppliers." if st == "check" else
            "Includes services under section 9(3) from unregistered suppliers; split inputs, capital goods and services from the books.")
        add("6D", "Reverse charge ITC, supplies from registered persons", reg, "GSTR-2B reverse charge supplies, 12 months")
    else:
        add("6C, 6D", "Reverse charge ITC", isrc, "GSTR-3B table 4(A)(3), 12 months", "check", "GSTR-2B is needed for all 12 months to split registered and unregistered suppliers.")
    add("6E", "Import of goods", itc("itc_availed", "IMPG"), "GSTR-3B table 4(A)(1), 12 months")
    add("6F", "Import of services", itc("itc_availed", "IMPS"), "GSTR-3B table 4(A)(2), 12 months")
    add("6G", "ITC received from ISD", itc("itc_availed", "ISD"), "GSTR-3B table 4(A)(4), 12 months")
    need("6H", "ITC reclaimed under the Act", "Not shown separately in GSTR-3B: take from the books and the reversal and re-claim statement.")
    add("6J", "Difference between 6A and the lines above", {k: (ZERO if k in TAXES else None) for k in COLS}, "6I less 6A: nil until 6H is entered")

    # ---------------- table 7: ITC reversed
    rev = itc("itc_reversed")
    add("7", "ITC reversed and ineligible ITC", rev, "GSTR-3B table 4(B), 12 months", "check" if _any({k: rev[k] for k in TAXES}) else "draft",
        "Split between rules 37, 39, 42, 43, section 17(5) and other reversals (7A to 7H) from the workings." if _any({k: rev[k] for k in TAXES}) else "")
    add("7J", "Net ITC available for utilisation", {k: (a6[k] - rev[k] if k in TAXES else None) for k in COLS}, "6O less 7I")

    # ---------------- table 8: other ITC information
    have2b = all(p in g2 for p in mon)
    if have2b:
        a8 = dict(_sum([_sum(g2[p].get("other_itc") for p in mon), _neg(_sum(g2[p].get("credit_notes") for p in mon)), reg]), taxable=None)
        add("8A", "ITC as per GSTR-2B", a8, "GSTR-2B, 12 months: all other ITC less credit notes, plus reverse charge", "check",
            "The portal fills 8A itself and it cannot be changed: compare this with the portal's Table 8A document details.")
    else:
        need("8A", "ITC as per GSTR-2B", "GSTR-2B for all 12 months.")
    b8 = {k: (oth[k] + (reg[k] if have2b else ZERO) if k in TAXES else None) for k in COLS}
    add("8B", "ITC as per 6B and 6H", b8, "6B (plus 6D, which GSTR-2B also carries); 6H to be added")
    if all(p in g2 for p in next_months(fy)):
        c8 = dict(_sum((g2[p].get("by_fy") or {}).get(fy) for p in next_months(fy)), taxable=None)
        add("8C", "ITC on this year's inward supplies availed in the next year", c8,
            "FY %s documents in GSTR-2B of April to October of the next year" % fy, "check",
            "This is what became available. Enter only what was actually taken in next year's GSTR-3B (also table 13).")
    else:
        need("8C", "ITC on this year's inward supplies availed in the next year", "GSTR-2B for April to October of the next year.")
        c8 = None
    if have2b and c8:
        add("8D", "Difference: 8A less (8B plus 8C)", {k: (a8[k] - b8[k] - c8[k] if k in TAXES else None) for k in COLS}, "Worked out", "check",
            "A positive figure is credit available and not taken: show it in 8E (not availed) or 8F (ineligible).")

    # ---------------- table 9: tax paid
    payable = {k: (b3("outward")[k] + b3("zero_rated")[k] + rcm[k] if k in TAXES else None) for k in COLS}
    add("9", "Tax payable", payable, "GSTR-3B tables 3.1(a), (b) and (d), 12 months", "check",
        "Compare with 4N. Paid in cash and paid through ITC come from GSTR-3B table 6.1 and the electronic ledgers.")
    need("9 (paid)", "Paid in cash and through ITC; interest and late fee", "Electronic cash and credit ledgers, or GSTR-3B table 6.1, for 12 months.")
    need("10 to 14", "This year's transactions reported in the next year", "GSTR-1 and GSTR-3B of April to October of the next year, and staff's decision on each cleared review point.")
    need("17, 18", "HSN summary of outward and inward supplies", "GSTR-1 invoice detail (table 12) for 12 months; inward HSN from the books.")

    gap = {k: n4[k] - payable[k] for k in TAXES}
    return dict(ready=True, missing=[], lines=lines,
                totals=dict(turnover=turnover, tax_4n=sum((n4[k] for k in TAXES), ZERO), tax_3b=sum(payable[k] for k in TAXES),
                            tax_gap=sum(gap.values(), ZERO), needs=sum(1 for l in lines if l["state"] == "needs"),
                            check=sum(1 for l in lines if l["state"] == "check"), gstr9c=turnover > Decimal("50000000")))
