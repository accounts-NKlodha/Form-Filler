"""Tally Prime / ERP 9 XML client (Tally must run with the HTTP server on, default port 9000).

F1 Help > Settings > Connectivity (Tally Prime): "TallyPrime acts as" = Both / Server, port 9000.
Sign convention kept as Tally exports it: Dr negative, Cr positive.
"""
import csv, datetime as dt, re, threading, urllib.request
import xml.etree.ElementTree as ET


class TallyError(Exception):
    pass


_ONE_AT_A_TIME = threading.Lock()  # Tally answers one request at a time; never send two together


def _post(xml, host="localhost", port=9000, timeout=300):
    req = urllib.request.Request(f"http://{host}:{port}", data=xml.encode("utf-8"),
                                 headers={"Content-Type": "text/xml;charset=utf-8"})
    if not _ONE_AT_A_TIME.acquire(timeout=timeout):
        raise TallyError("Tally is still busy with an earlier request")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except Exception as e:
        if "timed out" in str(e).lower():
            raise TallyError(f"Tally did not answer within {timeout // 60} minutes. If Tally shows 'Not responding', "
                             "close it from Task Manager, open it again with the company loaded, then Retry.")
        raise TallyError(f"Cannot reach Tally at {host}:{port}. Open Tally and enable the server (F1 > Settings > "
                         f"Connectivity, port {port}). Detail: {e}")
    finally:
        _ONE_AT_A_TIME.release()
    txt = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    # strip characters Tally sometimes emits that are invalid in XML 1.0
    txt = re.sub(r"&#(?:[0-8]|1[124-9]|2[0-9]|3[01]);", "", txt)
    txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
    return txt


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _tdate(d):
    """Tally's own date text, e.g. 1-Apr-2025. TallyPrime can hang on 20250401 in period variables."""
    return f"{d.day}-{d:%b-%Y}"


_AMT = "$$StringFindAndReplace:(if $$IsDebit:${f} then -$$NumValue:${f} else $$NumValue:${f}):\"(-)\":\"-\""


def _report(collection, fields, company=None, frm=None, to=None, host="localhost", port=9000):
    """Export a small TDL report (one ROW per object). fields: {tag: TDL expression}.
    The same request shape the Tally MCP connector uses, which TallyPrime answers quickly for a period."""
    sv = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
    if frm: sv += f"<SVFROMDATE>{_tdate(frm)}</SVFROMDATE>"
    if to: sv += f"<SVTODATE>{_tdate(to)}</SVTODATE>"
    if company: sv += f"<SVCURRENTCOMPANY>{_esc(company)}</SVCURRENTCOMPANY>"
    names = ",".join(f"F{i}" for i in range(len(fields)))
    flds = "".join(f"<FIELD NAME=\"F{i}\"><SET>{_esc(expr)}</SET><XMLTAG>{tag}</XMLTAG></FIELD>"
                   for i, (tag, expr) in enumerate(fields.items()))
    xml = ("<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>FFReport</ID></HEADER>"
           f"<BODY><DESC><STATICVARIABLES>{sv}</STATICVARIABLES><TDL><TDLMESSAGE>"
           "<REPORT NAME=\"FFReport\"><FORMS>FFForm</FORMS></REPORT><FORM NAME=\"FFForm\"><PARTS>FFPart</PARTS><XMLTAG>DATA</XMLTAG></FORM>"
           "<PART NAME=\"FFPart\"><LINES>FFLine</LINES><REPEAT>FFLine : FFColl</REPEAT><SCROLLED>Vertical</SCROLLED></PART>"
           f"<LINE NAME=\"FFLine\"><FIELDS>{names}</FIELDS><XMLTAG>ROW</XMLTAG></LINE>{flds}"
           f"<COLLECTION NAME=\"FFColl\"><TYPE>{collection}</TYPE></COLLECTION>"
           "</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>")
    txt = _post(xml, host, port)
    if "<LINEERROR>" in txt:
        raise TallyError(re.search(r"<LINEERROR>(.*?)</LINEERROR>", txt, re.S).group(1).strip())
    try:
        root = ET.fromstring(txt)
    except ET.ParseError as e:
        raise TallyError(f"Unreadable reply from Tally: {e}")
    return [{ch.tag: (ch.text or "").strip() for ch in row} for row in root.iter("ROW")]


def _collection(cid, typ, fields, company=None, frm=None, to=None, host="localhost", port=9000):
    sv = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
    if company: sv += f"<SVCURRENTCOMPANY>{_esc(company)}</SVCURRENTCOMPANY>"
    if frm: sv += f"<SVFROMDATE>{_tdate(frm)}</SVFROMDATE>"
    if to: sv += f"<SVTODATE>{_tdate(to)}</SVTODATE>"
    fetch = "".join(f"<NATIVEMETHOD>{f}</NATIVEMETHOD>" for f in fields if not f.startswith("_"))
    comp = "".join(f"<COMPUTE>{f[1:]}:${f}</COMPUTE>" for f in fields if f.startswith("_"))
    xml = f"""<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>{cid}</ID></HEADER>
<BODY><DESC><STATICVARIABLES>{sv}</STATICVARIABLES><TDL><TDLMESSAGE>
<COLLECTION NAME="{cid}" ISMODIFY="No"><TYPE>{typ}</TYPE>{fetch}{comp}</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""
    txt = _post(xml, host, port)
    if "<LINEERROR>" in txt:
        raise TallyError(re.search(r"<LINEERROR>(.*?)</LINEERROR>", txt, re.S).group(1).strip())
    try:
        root = ET.fromstring(txt)
    except ET.ParseError as e:
        raise TallyError(f"Unreadable reply from Tally: {e}")
    out = []
    for el in root.iter(typ.upper()):
        row = {"NAME": el.get("NAME") or ""}
        for ch in el:
            row[ch.tag.upper()] = (ch.text or "").strip()
        out.append(row)
    return out


def amount(s):
    """Tally amount text -> float, Dr negative. Handles '-1,234.50', '1234.50 Dr', '(-)1234'."""
    if s is None: return 0.0
    s = str(s).strip().replace(",", "")
    if not s: return 0.0
    neg = False
    if s.endswith("Dr"): neg, s = True, s[:-2]
    elif s.endswith("Cr"): s = s[:-2]
    s = s.replace("(-)", "-").strip()
    m = re.match(r"^-?\d+(\.\d+)?", s.replace(" ", ""))
    v = float(m.group(0)) if m else 0.0
    return -abs(v) if neg else v


def tdate(s):
    for f in ("%Y%m%d", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y"):
        try: return dt.datetime.strptime(s.strip(), f).date()
        except Exception: pass
    return None


def companies(host="localhost", port=9000):
    """Companies currently open in Tally."""
    rows = _collection("SchIIICompanies", "Company", ["StartingFrom", "BooksFrom"], host=host, port=port)
    return [{"name": r["NAME"], "starting_from": str(tdate(r.get("STARTINGFROM", "")) or ""),
             "books_from": str(tdate(r.get("BOOKSFROM", "")) or "")} for r in rows if r["NAME"]]


def _groups(company, host, port):
    rows = _collection("SchIIIGroups", "Group", ["Parent"], company=company, host=host, port=port)
    return {r["NAME"]: r.get("PARENT", "") for r in rows}


def _primary(name, parents):
    seen = set()
    while name in parents and parents[name] and parents[name] not in ("Primary", "&#4; Primary", "\x04 Primary") \
            and name not in seen:
        seen.add(name); name = parents[name]
    return name


def trial_balance(company, frm, to, host="localhost", port=9000):
    """Ledger-wise TB for the period. Returns list of dicts in the engine CSV layout."""
    amt = lambda f: _AMT.replace("{f}", f)
    led = _report("Ledger", {"NAME": "$Name", "PARENT": "$Parent", "PRIMARYGROUP": "$_PrimaryGroup",
                             "OPENINGBALANCE": amt("OpeningBalance"), "DEBITTOTALS": amt("DebitTotals"),
                             "CREDITTOTALS": amt("CreditTotals"), "CLOSINGBALANCE": amt("ClosingBalance")},
                  company=company, frm=frm, to=to, host=host, port=port)
    parents = None
    out = []
    for r in led:
        name, grp = r["NAME"], r.get("PARENT", "")
        if not name: continue
        cl = amount(r.get("CLOSINGBALANCE"))
        o = amount(r.get("OPENINGBALANCE"))
        dr, cr = -abs(amount(r.get("DEBITTOTALS"))), abs(amount(r.get("CREDITTOTALS")))
        if abs(dr) < 0.005 and abs(cr) < 0.005 and abs(cl - o) >= 0.005:  # totals not returned: use net movement
            mv = round(cl - o, 2); dr, cr = (mv, 0) if mv < 0 else (0, mv)
        prim = r.get("PRIMARYGROUP", "")
        if not prim:
            if parents is None: parents = _groups(company, host, port)
            prim = _primary(grp, parents)
        out.append({"ledger_name": name, "group_name": grp, "primary_group": prim,
                    "opening_balance": round(o, 2), "net_debit": round(dr, 2) + 0.0, "net_credit": round(cr, 2) + 0.0,
                    "closing_balance": round(cl, 2)})
    return out


FIELDS = ["ledger_name", "group_name", "primary_group", "opening_balance", "net_debit", "net_credit", "closing_balance"]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def read_tb(path):
    """Read a TB from the engine CSV, or from an Excel export with the same headers (first sheet)."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        it = ws.iter_rows(values_only=True)
        hdr = [str(h or "").strip().lower().replace(" ", "_") for h in next(it)]
        rows = [dict(zip(hdr, r)) for r in it if any(v not in (None, "") for v in r)]
    else:
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    missing = [f for f in ("ledger_name", "group_name", "closing_balance") if f not in (rows[0] if rows else {})]
    if missing:
        raise ValueError("TB file needs columns: " + ", ".join(FIELDS))
    for r in rows:
        r["primary_group"] = r.get("primary_group") or r["group_name"]
        for k in ("opening_balance", "net_debit", "net_credit", "closing_balance"):
            r[k] = amount(r.get(k))
    return rows


def roll_forward(py_rows, cy_rows, tol=1.0):
    """PY closing vs CY opening per balance-sheet ledger. Returns list of differences."""
    pl = {"sales accounts", "purchase accounts", "direct incomes", "direct expenses", "indirect incomes", "indirect expenses"}
    py = {r["ledger_name"]: r for r in py_rows}
    cy = {r["ledger_name"]: r for r in cy_rows}
    diffs = []
    for n in sorted(set(py) | set(cy)):
        p, c = py.get(n), cy.get(n)
        prim = ((c or p)["primary_group"] or "").lower()
        if prim in pl or n.lower() == "profit & loss a/c": continue
        a = p["closing_balance"] if p else 0.0
        b = c["opening_balance"] if c else 0.0
        if abs(a - b) > tol:
            diffs.append({"ledger": n, "group": (c or p)["group_name"], "py_closing": a, "cy_opening": b,
                          "difference": round(b - a, 2)})
    return diffs


def net_profit(rows):
    """Tally TB excludes the current-year profit, so closing balances sum to the profit (Cr positive)."""
    return round(sum(r["closing_balance"] for r in rows), 2)
