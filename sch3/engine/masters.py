"""Read the firm's master Excels by CIN and propose Setup values, each with its source (file / sheet / column / row).

Only the sheets named below are opened. The ROC master also holds portal credentials in other sheets and columns:
those are never read, stored or shown.
"""
import datetime as dt, re
import openpyxl
from openpyxl.utils import get_column_letter as L


def _d(v):
    if isinstance(v, dt.datetime): return v.date()
    if isinstance(v, dt.date): return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(v))).date()
    if isinstance(v, str):
        for f in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %B %Y", "%d/%m/%y"):
            try: return dt.datetime.strptime(v.strip()[:10] if f == "%Y-%m-%d" else v.strip(), f).date()
            except Exception: pass
    return None


def fmt(d): return d.strftime("%d/%m/%Y") if d else ""


def _norm(s): return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _header(ws, must=("cin",), scan=6):
    """Return (header_row_no, {normalised header: column index}) for the first row containing all `must` words."""
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=scan, values_only=True), 1):
        h = {_norm(v): j for j, v in enumerate(row) if v not in (None, "")}
        if all(any(m in k for k in h) for m in must):
            return i, h
    return None, {}


def _col(h, *names):
    for n in names:
        n = _norm(n)
        for k, j in h.items():
            if k == n: return j
    for n in names:
        n = _norm(n)
        for k, j in h.items():
            if k.startswith(n): return j
    return None


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def annual_report_number(inc, fy_end):
    """First FY ends on the 31 March after incorporation; if incorporated 1 Jan - 31 Mar it extends to the next
    31 March (s.2(41)), so that stub has no separate AGM."""
    # Companies Act 2013 s.2(41): Jan-Mar incorporations may extend the first FY to the following 31 March.
    # Before 1 April 2014 the first FY of a Jan-Mar incorporation ended on the coming 31 March (Parekh: inc 06/01/1995, 31st AGM in 2025).
    if inc.month <= 3 and (inc.year, inc.month) < (2014, 4): first = inc.year
    else: first = inc.year + 1
    return fy_end.year - first + 1


def read(cin, fy_end, auditor_file=None, roc_file=None, agm=None):
    """Returns {"values": {setup label: value}, "sources": {label: text}, "issues": [text], "directors": [...]}"""
    cin = (cin or "").strip().upper()
    vals, src, issues, directors = {}, {}, [], []

    def put(k, v, s):
        vals[k] = v; src[k] = s

    if auditor_file:
        wb = openpyxl.load_workbook(auditor_file, read_only=True, data_only=True)
        fn = auditor_file.replace("\\", "/").split("/")[-1]
        if "Auditor" in wb.sheetnames:
            ws = wb["Auditor"]; hr, h = _header(ws)
            ci = _col(h, "CIN")
            hit = None
            for i, row in enumerate(ws.iter_rows(min_row=hr + 1, values_only=True), hr + 1):
                if ci is not None and str(row[ci] or "").strip().upper() == cin: hit = (i, row); break
            if hit:
                i, row = hit
                for lbl, names in [("Auditor firm name", ("New Auditor Firm Name",)), ("Auditor FRN", ("Firm Registration No",)),
                                   ("Signing partner name", ("New Partner Name",)), ("Partner membership number", ("Partner Membership No",))]:
                    j = _col(h, *names)
                    if j is not None and row[j] not in (None, ""):
                        put(lbl, str(row[j]).strip(), f"{fn} / Auditor / col {L(j + 1)} / row {i}")
                j = 10  # column K per partner instruction: AGM date of appointment
                d = _d(row[j]) if len(row) > j else None
                if d:
                    put("Date of AGM appointing auditor", fmt(d), f"{fn} / Auditor / col K / row {i}")
                    put("Auditor term ends in year", d.year + 5, "Computed: col K year + 5 (s.139(1), five consecutive AGMs)")
                else:
                    issues.append("Auditor sheet col K (AGM appointing auditor) is blank or not a date.")
            else:
                issues.append(f"CIN {cin} not found in Auditor sheet.")
        if "MCA Data" in wb.sheetnames:
            ws = wb["MCA Data"]; hr, h = _header(ws, ("cin", "din"))
            ci, di, ni, de, si, dsc = (_col(h, "CIN"), _col(h, "DIN"), _col(h, "Director Name"), _col(h, "Designation"),
                                       _col(h, "Signing of financials"), _col(h, "DSC for form Signer"))
            seen = set()
            for i, row in enumerate(ws.iter_rows(min_row=hr + 1, values_only=True), hr + 1):
                if ci is None or str(row[ci] or "").strip().upper() != cin: continue
                din = str(row[di] or "").strip()
                if din.isdigit(): din = din.zfill(8)
                if din in seen: continue
                seen.add(din)
                directors.append({"row": i, "din": din, "name": str(row[ni] or "").strip().title(),
                                  "designation": str(row[de] or "").strip() if de is not None else "",
                                  "signer": str(row[si] or "").strip().lower() == "yes" if si is not None else False,
                                  "dsc": str(row[dsc] or "").strip().lower() == "yes" if dsc is not None else False})
            ai = _col(h, "Registered Office Address")
            if directors and ai is not None:
                r0 = directors[0]["row"]
                addr = next((rw[ai] for k, rw in enumerate(ws.iter_rows(min_row=r0, max_row=r0, values_only=True))), None)
                if addr: put("Registered office address", " ".join(str(addr).split()), f"{fn} / MCA Data / col {L(ai + 1)} / row {r0}")
            if directors:
                put("Board strength (number of directors)", len(directors),
                    f"{fn} / MCA Data / count of DINs for CIN (rows {', '.join(str(d['row']) for d in directors)})")
                signers = [d for d in directors if d["signer"]] or []
                signers.sort(key=lambda d: not d["dsc"])
                for k, d in enumerate(signers[:2], 1):
                    put(f"Signing director {k} name", d["name"], f"{fn} / MCA Data / col {L(ni + 1)} / row {d['row']} (col {L(si + 1)} = Yes)")
                    put(f"Signing director {k} DIN", d["din"], f"{fn} / MCA Data / col {L(di + 1)} / row {d['row']}")
                if len(signers) < 2:
                    issues.append("Fewer than two directors marked 'Yes' under 'Signing of financials' in MCA Data.")
            else:
                issues.append(f"CIN {cin} not found in MCA Data sheet.")

    if roc_file:
        wb = openpyxl.load_workbook(roc_file, read_only=True, data_only=True)
        fn = roc_file.replace("\\", "/").split("/")[-1]
        fy_tag = f"FY{str(fy_end.year - 1)[2:]}-{str(fy_end.year)[2:]}"
        names = [n for n in wb.sheetnames if n.lower().startswith("roc companies")]
        names.sort(key=lambda n: fy_tag.lower() not in n.replace(" ", "").lower())
        for sn in names:
            ws = wb[sn]; hr, h = _header(ws, ("cin", "bm1"))
            if not hr: continue
            ci = _col(h, "CIN")
            hit = None
            for i, row in enumerate(ws.iter_rows(min_row=hr + 1, values_only=True), hr + 1):
                if str(row[ci] or "").strip().upper() == cin: hit = (i, row); break
            if not hit: continue
            i, row = hit
            j = _col(h, "Date of Incorporation")
            inc = _d(row[j]) if j is not None else None
            if inc:
                put("Date of incorporation", fmt(inc), f"{fn} / {sn} / col {L(j + 1)} / row {i}")
                n = annual_report_number(inc, fy_end)
                put("Annual report number (e.g. 32nd)", ordinal(n),
                    f"Computed from incorporation {fmt(inc)}" + (" (Jan-Mar: first period extended, no stub AGM)" if inc.month <= 3 and inc.year >= 2014 else ""))
            bms = []
            for k in range(1, 13):
                j = _col(h, f"BM-{k}")
                if j is None: break
                d = _d(row[j]) if len(row) > j else None
                if d: bms.append((d, L(j + 1)))
            bms.sort()
            if bms:
                put("Board meeting dates", ", ".join(fmt(d) for d, _ in bms),
                    f"{fn} / {sn} / cols {bms[0][1]}-{bms[-1][1]} / row {i}")
            ja = _col(h, "Auditor Name")
            if ja is not None and row[ja]:
                vals["_roc_auditor"] = str(row[ja]).strip()
                src["_roc_auditor"] = f"{fn} / {sn} / col {L(ja + 1)} / row {i}"
                af = vals.get("Auditor firm name", "")
                if af and _norm(af)[:8] not in _norm(row[ja]) and _norm(row[ja])[:8] not in _norm(af):
                    issues.append(f"Auditor differs: Auditor sheet says '{af}', ROC master says '{row[ja]}'. Confirm which firm signs.")
            # approving board meeting: latest BM after year end and at least 21 days before the AGM
            if agm:
                ok = [d for d, _ in bms if fy_end < d <= agm - dt.timedelta(days=21)]
                if ok:
                    put("Date of board meeting approving board's report", fmt(ok[-1]), "Latest BM after year end and >= 21 days before AGM")
                    put("Date of auditor's report", fmt(ok[-1]), "Same as approving board meeting (partner instruction)")
                else:
                    issues.append("No board meeting in the ROC master falls after year end and 21+ days before the AGM. "
                                  "Enter the approving board meeting date.")
            break
        else:
            issues.append(f"CIN {cin} not found in any 'ROC Companies' sheet.")
    return {"values": vals, "sources": src, "issues": issues, "directors": directors}
