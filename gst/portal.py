"""Readers for files that come off the GST portal.

A file is recognised by what is inside it, never by its name: clients and the portal name files inconsistently
(the portal gives every month's GSTR-2A zip the same name). Each reader returns plain figures as Decimal.

Kinds: gstr3b (filed return figures), gstr1_summary (section summary with HSN), gstr2b, gstr2a, gstr1 (invoice detail).
"""
import io
import json
import re
import zipfile
from decimal import Decimal

KINDS = ("gstr3b", "gstr1_summary", "gstr1", "gstr2a", "gstr2b")
LABEL = {"gstr3b": "GSTR-3B", "gstr1_summary": "GSTR-1 summary", "gstr1": "GSTR-1 invoice detail", "gstr2a": "GSTR-2A", "gstr2b": "GSTR-2B"}
PERIOD = re.compile(r"^(0[1-9]|1[0-2])(20[0-9]{2})$")
TAXES = ("igst", "cgst", "sgst", "cess")
ZERO = Decimal("0")


class Unrecognised(ValueError):
    pass


def D(x):
    if x in (None, ""):
        return ZERO
    try:
        return Decimal(str(x))
    except ArithmeticError:
        return ZERO


def tax(o, keys=("igst", "cgst", "sgst", "cess")):
    """A {igst, cgst, sgst, cess} dict from a portal object, whatever spelling that return uses."""
    o = o or {}
    return {t: D(o.get(k)) for t, k in zip(TAXES, keys)}


def add(a, b):
    return {t: a.get(t, ZERO) + b.get(t, ZERO) for t in TAXES}


def total(t):
    return sum((t.get(k, ZERO) for k in TAXES), ZERO)


def months(fy):
    """'2025-26' -> ['042025', ..., '032026']"""
    y = int(fy[:4])
    return ["%02d%d" % (m, y) for m in range(4, 13)] + ["%02d%d" % (m, y + 1) for m in range(1, 4)]


def next_months(fy):
    """April to October of the next year: the window for tables 8C and 10 to 13."""
    y = int(fy[:4]) + 1
    return ["%02d%d" % (m, y) for m in range(4, 11)]


def month_name(period):
    return "%s %s" % ("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()[int(period[:2]) - 1], period[2:])


def read(raw, name=""):
    """bytes -> dict(kind, gstin, period, figures). Raises Unrecognised."""
    if raw[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            inner = [n for n in z.namelist() if n.lower().endswith(".json")]
            if len(inner) != 1 or z.getinfo(inner[0]).file_size > 200_000_000:
                raise Unrecognised("The zip does not hold exactly one JSON file.")
            raw = z.read(inner[0])
        except zipfile.BadZipFile:
            raise Unrecognised("The zip file is damaged.")
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise Unrecognised("Not a JSON file from the GST portal.")
    if not isinstance(doc, dict):
        raise Unrecognised("Not a JSON file from the GST portal.")
    d = doc.get("data") if isinstance(doc.get("data"), dict) else doc
    if "sup_details" in d and "itc_elg" in d:
        out = dict(kind="gstr3b", gstin=d.get("gstin"), period=d.get("ret_period"), figures=_g3b(d))
    elif "sec_sum" in d:
        out = dict(kind="gstr1_summary", gstin=d.get("gstin"), period=d.get("ret_period"), figures=_g1sum(d))
    elif "itcsumm" in d:
        out = dict(kind="gstr2b", gstin=d.get("gstin"), period=d.get("rtnprd"), figures=_g2b(d))
    elif "fp" in d and "gstin" in d and any(k in d for k in ("filing_typ", "fil_dt", "gt", "hsn", "doc_issue", "b2cs", "b2cl", "exp", "nil")):
        out = dict(kind="gstr1", gstin=d.get("gstin"), period=d.get("fp"), figures=_g1(d))   # its b2b rows carry "cfs" too, like GSTR-2A
    elif "fp" in d and "gstin" in d and (("b2b" in d and d["b2b"] and "cfs" in d["b2b"][0]) or "tds" in d or "tcs" in d or
                                         ("cdn" in d and d["cdn"] and "cfs" in d["cdn"][0])):
        out = dict(kind="gstr2a", gstin=d.get("gstin"), period=d.get("fp"), figures=_g2a(d))
    elif "fp" in d and "gstin" in d:
        out = dict(kind="gstr1", gstin=d.get("gstin"), period=d.get("fp"), figures=_g1(d))
    else:
        raise Unrecognised("This is not a GSTR-1, 2A, 2B or 3B file.")
    out["gstin"] = str(out["gstin"] or "").upper()
    out["period"] = str(out["period"] or "")
    if not PERIOD.match(out["period"]):
        raise Unrecognised("The file does not say which month it is for.")
    return out


# ---------------------------------------------------------------- GSTR-3B
def _sup(o):
    o = o or {}
    return dict(tax(o, ("iamt", "camt", "samt", "csamt")), taxable=D(o.get("txval")))


def _g3b(d):
    s = d.get("sup_details") or {}
    itc = d.get("itc_elg") or {}
    rows = lambda key: {r.get("ty"): tax(r, ("iamt", "camt", "samt", "csamt")) for r in itc.get(key) or [] if isinstance(r, dict)}
    return dict(outward=_sup(s.get("osup_det")), zero_rated=_sup(s.get("osup_zero")), nil_exempt=_sup(s.get("osup_nil_exmp")),
                non_gst=_sup(s.get("osup_nongst")), rcm=_sup(s.get("isup_rev")),
                itc_availed=rows("itc_avl"), itc_reversed=rows("itc_rev"), itc_ineligible=rows("itc_inelg"),
                itc_net=tax(itc.get("itc_net"), ("iamt", "camt", "samt", "csamt")))


# ---------------------------------------------------------------- GSTR-1 summary
def _g1sum(d):
    out = {}
    for s in d.get("sec_sum") or []:
        if isinstance(s, dict) and s.get("sec_nm"):
            out[s["sec_nm"]] = dict(tax(s, ("ttl_igst", "ttl_cgst", "ttl_sgst", "ttl_cess")), taxable=D(s.get("ttl_tax")),
                                    value=D(s.get("ttl_val")), records=int(s.get("ttl_rec") or 0))
            if any(k in s for k in ("ttl_expt_amt", "ttl_nilsup_amt", "ttl_ngsup_amt")):   # table 8: no tax, three values
                out[s["sec_nm"]].update(exempt=D(s.get("ttl_expt_amt")), nil_rated=D(s.get("ttl_nilsup_amt")), non_gst=D(s.get("ttl_ngsup_amt")), split=True)
    return out


# ---------------------------------------------------------------- GSTR-2B
def _g2b(d):
    avl = (d.get("itcsumm") or {}).get("itcavl") or {}
    una = (d.get("itcsumm") or {}).get("itcunavl") or {}
    part = lambda src, key: tax(src.get(key))
    return dict(other_itc=part(avl, "nonrevsup"), credit_notes=part(avl, "othersup"), rcm=part(avl, "revsup"),
                isd=part(avl, "isdsup"), imports=part(avl, "imports"),
                unavailable=add(add(part(una, "nonrevsup"), part(una, "revsup")), part(una, "isdsup")),
                by_fy=_g2b_by_fy(d.get("docdata") or {}),
                documents=sum(len(s.get("inv") or s.get("nt") or []) for k in ("b2b", "b2ba", "cdnr", "cdnra")
                              for s in (d.get("docdata") or {}).get(k) or [] if isinstance(s, dict)))


def fy_of(date):
    """'15-03-2026' -> '2025-26'; '' when the date cannot be read."""
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", str(date or ""))
    if not m:
        return ""
    y = int(m.group(3)) - (1 if int(m.group(2)) < 4 else 0)
    return "%d-%02d" % (y, (y + 1) % 100)


def _g2b_by_fy(docdata):
    """Available, forward-charge ITC in this GSTR-2B split by the financial year of the document date.
    Credit notes count as minus. Used to find last year's invoices that reached 2B only in the next year."""
    out = {}
    for key, docs, sign_of in (("b2b", "inv", lambda d: 1), ("b2ba", "inv", lambda d: 1),
                               ("cdnr", "nt", lambda d: -1 if str(d.get("typ", "")).upper().startswith("C") else 1),
                               ("cdnra", "nt", lambda d: -1 if str(d.get("typ", "")).upper().startswith("C") else 1)):
        for s in docdata.get(key) or []:
            for doc in (s.get(docs) or []) if isinstance(s, dict) else []:
                if str(doc.get("itcavl", "Y")).upper() != "Y" or str(doc.get("rev", "N")).upper() == "Y":
                    continue
                fy = fy_of(doc.get("dt"))
                row = out.setdefault(fy, dict(tax({}), taxable=ZERO, documents=0))
                t = tax(doc) if any(k in doc for k in TAXES) else {k: v for k, v in _items(doc).items() if k in TAXES}
                for k in TAXES:
                    row[k] += sign_of(doc) * t[k]
                row["taxable"] += sign_of(doc) * (D(doc.get("txval")) if "txval" in doc else _items(doc)["taxable"])
                row["documents"] += 1
    return out


# ---------------------------------------------------------------- GSTR-2A and GSTR-1 invoice files
def _items(doc):
    t = dict(tax({}), taxable=ZERO)
    for it in doc.get("itms") or []:
        det = it.get("itm_det") or it
        for k, src in zip(TAXES, ("iamt", "camt", "samt", "csamt")):
            t[k] += D(det.get(src))
        t["taxable"] += D(det.get("txval"))
    return t


def _g2a(d):
    out = dict(b2b=dict(tax({}), taxable=ZERO, documents=0), notes=dict(tax({}), taxable=ZERO, documents=0),
               tds=tax({}), tcs=tax({}), suppliers=0, by_fy={})
    sup = set()
    for key, docs, into in (("b2b", "inv", "b2b"), ("b2ba", "inv", "b2b"), ("cdn", "nt", "notes"), ("cdna", "nt", "notes")):
        for s in d.get(key) or []:
            sup.add(s.get("ctin"))
            for doc in s.get(docs) or []:
                t = _items(doc)
                sign = -1 if into == "notes" and str(doc.get("ntty", "")).upper() == "C" else 1
                year = out["by_fy"].setdefault(fy_of(doc.get("idt") or doc.get("nt_dt")), dict(tax({}), taxable=ZERO, documents=0))
                for k in TAXES + ("taxable",):
                    out[into][k] += sign * t[k]
                    year[k] += sign * t[k]
                out[into]["documents"] += 1
                year["documents"] += 1
    for key in ("tds", "tcs"):
        for r in d.get(key) or []:
            out[key] = add(out[key], tax(r, ("iamt", "camt", "samt", "csamt")))
    out["suppliers"] = len(sup - {None})
    return out


def _g1(d):
    """GSTR-1 as filed, from the portal's offline download: invoice counts and totals by section, and the HSN rows."""
    row = lambda: dict(tax({}), taxable=ZERO, documents=0)
    out = dict(b2b=row(), b2cl=row(), b2cs=row(), notes=row(), hsn=row(), einv=dict(documents=0, taxable=ZERO))
    for key, docs, into in (("b2b", "inv", "b2b"), ("b2cl", "inv", "b2cl"), ("cdnr", "nt", "notes")):
        for s in d.get(key) or []:
            for doc in s.get(docs) or []:
                t = _items(doc)
                sign = -1 if into == "notes" and str(doc.get("ntty", "")).upper() == "C" else 1
                for k in TAXES + ("taxable",):
                    out[into][k] += sign * t[k]
                out[into]["documents"] += 1
                if into == "b2b" and (doc.get("irn") or str(doc.get("srctyp", "")).lower().startswith("e-inv")):
                    out["einv"]["documents"] += 1
                    out["einv"]["taxable"] += t["taxable"]
    flat = lambda r: dict(tax(r, ("iamt", "camt", "samt", "csamt")), taxable=D(r.get("txval")))
    for r in d.get("b2cs") or []:
        for k, v in flat(r).items():
            out["b2cs"][k] += v
        out["b2cs"]["documents"] += 1
    hsn = d.get("hsn") if isinstance(d.get("hsn"), dict) else {}
    rows = [dict(flat(r), hsn=str(r.get("hsn_sc") or ""), rate=D(r.get("rt")), uqc=str(r.get("uqc") or ""), qty=D(r.get("qty")), part=part)
            for part, key in (("", "data"), ("B2B", "hsn_b2b"), ("B2C", "hsn_b2c")) for r in hsn.get(key) or [] if isinstance(r, dict)]
    for r in rows:
        for k in TAXES + ("taxable",):
            out["hsn"][k] += r[k]
    out["hsn"]["documents"] = len(rows)
    out["hsn_rows"] = rows
    out["filed_on"] = str(d.get("fil_dt") or "")
    return out
