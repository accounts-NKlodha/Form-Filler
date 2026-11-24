"""Month-wise checks on portal data for the annual return. Each check that does not tie becomes a review point.

A check compares two sources month by month and for the year. Three outcomes:
  ok     both sources are present for every month and they tie
  point  they differ in a month or for the year: a reviewer clears it with a reason
  needs  a source is missing for some month: shown as "needs input", never treated as zero

Checks against the books (Tally) come in a later step; this file needs no ledger data.
"""
import hashlib
from decimal import Decimal

from .portal import LABEL, TAXES, ZERO, add, month_name, months, next_months, total

TOLERANCE = Decimal("1.00")  # rupees; portal summaries round each section


def _t(o):
    return total(o or {})


def _g1(f, sec):
    return f.get(sec) or {}


def _itc(f, ty):
    return (f.get("itc_availed") or {}).get(ty) or {}


CHECKS = (
    # id, area, title, GSTR-9/9C tables, (kind a, label a, fn a), (kind b, label b, fn b), note
    ("outward_taxable", "Outward supplies", "Taxable value of outward supplies", "4, 5; 9C 5 and 7",
     ("gstr1_summary", "GSTR-1", lambda f: _g1(f, "TTL_LIAB").get("taxable", ZERO)),
     ("gstr3b", "GSTR-3B 3.1(a)+(b)", lambda f: f["outward"]["taxable"] + f["zero_rated"]["taxable"]),
     "A gap usually means an invoice or credit note reported in one return and not the other."),
    ("outward_tax", "Outward supplies", "Tax on outward supplies", "4, 9",
     ("gstr1_summary", "GSTR-1", lambda f: _t(_g1(f, "TTL_LIAB"))),
     ("gstr3b", "GSTR-3B 3.1(a)+(b)", lambda f: _t(f["outward"]) + _t(f["zero_rated"])),
     "Tax paid in a later month than GSTR-1 shows it carries interest under section 50 even when the year ties."),
    ("hsn_tax", "HSN", "HSN summary tax against the return total", "17",
     ("gstr1_summary", "GSTR-1 table 12 (HSN)", lambda f: _t(_g1(f, "HSN"))),
     ("gstr1_summary", "GSTR-1 total liability", lambda f: _t(_g1(f, "TTL_LIAB"))),
     "Table 17 is built from the HSN rows, so they must add up to the supplies reported."),
    ("hsn_b2b", "HSN", "HSN summary, B2B part, against B2B supplies", "17",
     ("gstr1_summary", "GSTR-1 table 12 (HSN B2B)", lambda f: _t(_g1(f, "HSN_B2B")) if "HSN_B2B" in f else None),
     ("gstr1_summary", "GSTR-1 B2B and credit notes", lambda f: _t(_g1(f, "B2B")) + _t(_g1(f, "CDNR"))),
     "A swap between the B2B and B2C tabs of table 12 does not change tax but must be right in table 17."),
    ("itc_2b", "Input tax credit", "ITC taken in GSTR-3B against ITC available in GSTR-2B", "6B, 8A to 8D",
     ("gstr3b", "GSTR-3B 4(A)(5)", lambda f: _t(_itc(f, "OTH"))),
     ("gstr2b", "GSTR-2B (all other ITC less credit notes)", lambda f: _t(f["other_itc"]) - _t(f["credit_notes"])),
     "Credit is often taken in a later month, so read the year line. ITC in 2B not taken by the cut-off lapses; "
     "ITC taken above 2B needs the supplier-wise reason."),
    ("rcm_itc", "Reverse charge", "Reverse charge tax paid against ITC taken on it", "6C, 6D, 9",
     ("gstr3b", "GSTR-3B 3.1(d) tax", lambda f: _t(f["rcm"])),
     ("gstr3b", "GSTR-3B 4(A)(3) ITC", lambda f: _t(_itc(f, "ISRC"))),
     "ITC on reverse charge cannot exceed the tax paid on it; a lower figure may be blocked credit."),
    ("rcm_2b", "Reverse charge", "Reverse charge paid against registered-supplier RCM in GSTR-2B", "6D",
     ("gstr3b", "GSTR-3B 3.1(d) tax", lambda f: _t(f["rcm"])),
     ("gstr2b", "GSTR-2B reverse charge", lambda f: _t(f["rcm"])),
     "GSTR-2B shows only registered suppliers. The balance should be RCM on unregistered supplies (table 6C)."),
    ("imports", "Imports", "IGST on import of goods", "6E",
     ("gstr3b", "GSTR-3B 4(A)(1)", lambda f: _t(_itc(f, "IMPG"))),
     ("gstr2b", "GSTR-2B imports", lambda f: _t(f["imports"])),
     "Compare with bills of entry when the two differ."),
    ("isd", "Input tax credit", "ITC from input service distributor", "6G",
     ("gstr3b", "GSTR-3B 4(A)(4)", lambda f: _t(_itc(f, "ISD"))),
     ("gstr2b", "GSTR-2B ISD", lambda f: _t(f["isd"])), ""),
    ("gstr2a_2b", "Input tax credit", "GSTR-2A against GSTR-2B", "8A",
     ("gstr2a", "GSTR-2A invoices and notes", lambda f: _t(f["b2b"]) + _t(f["notes"])),
     ("gstr2b", "GSTR-2B (available, reverse charge and not available)",
      lambda f: _t(f["other_itc"]) - _t(f["credit_notes"]) + _t(f["rcm"]) + _t(f["unavailable"])),
     "2A follows the supplier's return period and 2B the filing cut-off date, so months differ; read the year line."),
)


def run(fy, data):
    """data: {kind: {period: figures}} -> list of check results, in display order."""
    out = []
    for cid, area, title, ref, (ka, la, fa), (kb, lb, fb), note in CHECKS:
        rows, missing, skip = [], [], False
        for p in months(fy):
            a_src, b_src = (data.get(ka) or {}).get(p), (data.get(kb) or {}).get(p)
            if a_src is None or b_src is None:
                missing.append((p, [LABEL[k] for k, src in ((ka, a_src), (kb, b_src)) if src is None]))
                continue
            a, b = fa(a_src), fb(b_src)
            if a is None or b is None:   # this month's file has no such section (older portal layout)
                skip = True
                continue
            rows.append(dict(period=p, month=month_name(p), a=a, b=b, diff=a - b))
        ta, tb = sum((r["a"] for r in rows), ZERO), sum((r["b"] for r in rows), ZERO)
        gaps = [r for r in rows if abs(r["diff"]) > TOLERANCE]
        if missing:
            state = "needs"
        elif skip and not rows:
            continue
        elif gaps or abs(ta - tb) > TOLERANCE:
            state = "point"
        else:
            state = "ok"
        out.append(dict(id=cid, area=area, title=title, ref=ref, a_label=la, b_label=lb, rows=rows, total_a=ta, total_b=tb,
                        diff=ta - tb, gaps=len(gaps), state=state, note=note,
                        missing=_missing_text(missing), timing=bool(gaps) and abs(ta - tb) <= TOLERANCE))
    out.append(_next_year(fy, data, "gstr2b"))
    out.append(_next_year(fy, data, "gstr2a"))
    for c in out:
        c["sig"] = _sig(c)
    return out


def _missing_text(missing):
    if not missing:
        return ""
    kinds = {}
    for p, labels in missing:
        for lab in labels:
            kinds.setdefault(lab, []).append(month_name(p))
    return "; ".join("%s: %s" % (k, ", ".join(v) if len(v) < 12 else "all 12 months") for k, v in sorted(kinds.items()))


def _next_year(fy, data, kind):
    """This year's invoices that reached GSTR-2B (or GSTR-2A) only in April to October of the next year (tables 8C and 13).
    A supplier who files late can still report this year's invoice in a return of the next year."""
    rows, missing = [], []
    for p in next_months(fy):
        f = (data.get(kind) or {}).get(p)
        if f is None:
            missing.append((p, [LABEL[kind]]))
            continue
        t = (f.get("by_fy") or {}).get(fy) or {}
        amount = sum((t.get(k, ZERO) for k in TAXES), ZERO)
        rows.append(dict(period=p, month=month_name(p), a=amount, b=ZERO, diff=amount, documents=t.get("documents", 0)))
    ta = sum((r["a"] for r in rows), ZERO)
    state = "needs" if missing else ("point" if abs(ta) > TOLERANCE else "ok")
    return dict(id="next_year_" + kind[-2:], area="Input tax credit", ref="8C, 13",
                title="FY %s invoices that reached %s in April to October of the next year" % (fy, LABEL[kind]),
                a_label="ITC on FY %s documents" % fy, b_label="", rows=rows, total_a=ta, total_b=ZERO, diff=ta,
                gaps=len([r for r in rows if abs(r["diff"]) > TOLERANCE]), state=state, timing=False,
                missing=_missing_text(missing),
                note="If this credit was taken in next year's GSTR-3B it goes in tables 8C and 13; confirm against the books." if kind == "gstr2b" else
                     "Suppliers who filed late. GSTR-2A counts every document, including reverse charge and credit not available; "
                     "compare with the GSTR-2B line above before taking any of it to table 8C.")


def _sig(c):
    """Changes when any figure of the check changes, so a cleared point re-opens on new data."""
    h = hashlib.sha256()
    h.update(("%s|%s|%s|%s" % (c["id"], c["state"], c["total_a"], c["total_b"])).encode())
    for r in c["rows"]:
        h.update(("%s:%s:%s" % (r["period"], r["a"], r["b"])).encode())
    h.update(c["missing"].encode())
    return h.hexdigest()[:16]
