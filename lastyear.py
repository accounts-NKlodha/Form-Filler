"""Read last year's filed MGT-7A PDF (the MCA e-form print) into plain facts.

The print is a fixed layout, so facts are found by the label text that precedes them.
Radio buttons are read from the drawing: a selected option has a small filled dot
inside its circle, just left of the option word.
"""
import re
from pathlib import Path

import pdfplumber

NUM = r"-?\d+(?:\.\d+)?"


def _radios(pdf):
    """[(page, top, chosen option word, line text)] for every radio row in the print."""
    out = []
    for pi, pg in enumerate(pdf.pages):
        dots = [c for c in pg.curves if c.get("fill") and (c["x1"] - c["x0"]) < 6 and c.get("non_stroking_color") in (0, 0.0, (0,), (0.0,), [0])]
        if not dots:
            continue
        words = pg.extract_words()
        for d in dots:
            cx, cy = (d["x0"] + d["x1"]) / 2, (d["top"] + d["bottom"]) / 2
            cand = [w for w in words if 0 < w["x0"] - cx < 18 and abs((w["top"] + w["bottom"]) / 2 - cy) < 6]
            if not cand:
                continue
            w = min(cand, key=lambda w: w["x0"] - cx)
            line = " ".join(x["text"] for x in words if abs(x["top"] - w["top"]) < 4 and x["x0"] < w["x0"])
            # The question often wraps: take the nearest text line above too.
            above = [x for x in words if 0 < w["top"] - x["top"] < 14 and x["x0"] < w["x0"] - 30]
            out.append((pi, w["top"], w["text"], (" ".join(x["text"] for x in above) + " " + line).strip()))
    return out


def _after(lines, pat, n=1, start=0):
    """Text of the n lines after the first line matching pat."""
    for i in range(start, len(lines)):
        if re.search(pat, lines[i], re.I):
            return lines[i + 1:i + 1 + n], i
    return [], -1


def _nums(s):
    return [float(x) for x in re.findall(NUM, s or "")]


def _int(x):
    return int(round(x)) if x is not None else None


def read_mgt7a(path):
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        radios = _radios(pdf)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    f = {"source": path.name}

    def radio(*keys):
        for _, _, word, line in radios:
            if all(k.lower() in line.lower() for k in keys):
                return word
        return None

    m = re.search(r"\(From date\).*?(\d\d/\d\d/\d{4})", text)
    f["fy_from"] = m.group(1) if m else None
    m = re.search(r"\(To date\).*?(\d\d/\d\d/\d{4})", text)
    f["fy_to"] = m.group(1) if m else None
    f["opc_or_small"] = "Small Company" if radio("filed for") == "Small" else ("OPC" if radio("filed for") == "OPC" else None)
    f["has_share_capital"] = radio("share capital")
    f["agm_held"] = radio("Annual General Meeting")
    f["agm_extension"] = radio("extension")
    f["compliance_ok"] = radio("compliances and disclosures")
    for key, pat in (("class", r"\(a\) \*?Class of Company"), ("category", r"\(b\) \*?Category of the Company"),
                     ("subcategory", r"\(c\) \*?Sub-category of the Company")):
        nxt, _ = _after(lines, pat)
        f[key] = nxt[0] if nxt else None
    m = re.search(r"Date of Incorporation.*?\n?(\d\d/\d\d/\d{4})", text)
    f["incorporation"] = m.group(1) if m else None
    nxt, _ = _after(lines, r"Website")
    f["website"] = None if not nxt or nxt[0].lower().startswith(("iv", "*date")) else nxt[0]

    # II business activities: "1 G 47 100" (S.No, group code, activity code, % turnover)
    f["activities"] = [{"group": g, "code": c, "pct": p} for _, g, c, p in
                       re.findall(r"^(\d+) ([A-U]) (\d{2,4}) (" + NUM + r")$", text, re.M)]
    nxt, _ = _after(lines, r"No\. of Companies for which information")
    f["associates"] = _int((_nums(nxt[0]) or [0])[0]) if nxt else 0

    # IV share capital (equity)
    eq = {}
    _, i = _after(lines, r"\(a\) Equity share capital")
    nxt, j = _after(lines, r"^Total number of equity shares", 1, i)
    eq["count"] = _nums(nxt[0]) if nxt else []
    nxt, j = _after(lines, r"^Total amount of equity", 1, j)
    eq["amount"] = _nums(nxt[0]) if nxt else []
    nxt, j = _after(lines, r"^Number of classes", 1, j)
    eq["classes"] = _int(_nums(nxt[0])[0]) if nxt and _nums(nxt[0]) else None
    nxt, j = _after(lines, r"^Class of shares", 1, j)
    eq["class_name"] = nxt[0] if nxt else None
    nxt, j = _after(lines, r"^Number of equity shares", 1, j)
    eq["class_count"] = _nums(nxt[0]) if nxt else []
    nxt, j = _after(lines, r"^Nominal value per share", 1, j)
    eq["nominal"] = _nums(nxt[0]) if nxt else []
    f["equity"] = eq
    _, i = _after(lines, r"\(b\) Preference share capital")
    nxt, _ = _after(lines, r"^Number of classes", 1, i)
    f["preference_classes"] = _int(_nums(nxt[0])[0]) if nxt and _nums(nxt[0]) else 0
    m = re.search(r"\(d\) Break-up of paid-up share capital.*?At the end of the year\s+(" + NUM + r")\s+(" + NUM + r")\s+(" + NUM + r")", text, re.S)
    f["equity_year_end"] = [float(x) for x in m.groups()] if m else None

    m = re.search(r"\*Turnover\s+(" + NUM + ")", text)
    f["turnover"] = float(m.group(1)) if m else None

    # VI shareholding pattern: 16 category rows each "equity no, %, preference no, %"
    def pattern(start_pat, end_pat):
        s = re.search(start_pat, text)
        e = re.search(end_pat, text[s.end():]) if s else None
        if not s or not e:
            return []
        block = text[s.end():s.end() + e.start()]
        rows = re.findall(r"(" + NUM + r") (" + NUM + r") (" + NUM + r") (" + NUM + r")\s*$", block, re.M)
        return [[float(x) for x in r] for r in rows][:16]
    f["promoters"] = pattern(r"A Promoters", r"Total number of shareholders \(promoters\)")
    f["others"] = pattern(r"B Other than promoters", r"Total number of shareholders \(other than promoters\)")
    nxt, _ = _after(lines, r"^Total number of shareholders \(promoters\)$")
    f["n_promoters"] = _int(_nums(nxt[0])[0]) if nxt and _nums(nxt[0]) else None
    nxt, _ = _after(lines, r"^Total number of shareholders \(other than promoters\)$")
    f["n_others"] = _int(_nums(nxt[0])[0]) if nxt and _nums(nxt[0]) else None
    g = {}
    for k, pat in (("female", r"Individual - Female (\d+)"), ("male", r"Individual - Male (\d+)"),
                   ("transgender", r"Individual - Transgender (\d+)"), ("other", r"Other than individuals (\d+)")):
        m = re.search(pat, text)
        g[k] = int(m.group(1)) if m else 0
    f["gender"] = g
    # VII promoters / members / debenture holders: beginning, end
    vii = {}
    for k, pat in (("promoters", r"^Promoters$"), ("members", r"^Members \(other than promoters\)$"), ("debenture", r"^Debenture holders$")):
        nxt, _ = _after(lines, pat)
        n = _nums(nxt[0]) if nxt else []
        vii[k] = [int(x) for x in n[:2]] if len(n) >= 2 else None
    f["holders"] = vii
    # VIII meetings
    f["member_meetings"] = [{"type": t, "date": d, "entitled": int(a), "attended": int(b), "pct": p}
                            for t, d, a, b, p in re.findall(r"^(AGM|EGM)\s+(\d\d/\d\d/\d{4})\s+(\d+)\s+(\d+)\s+(" + NUM + ")", text, re.M)]
    f["board_meetings"] = [{"date": d, "directors": int(a), "attended": int(b), "pct": p}
                           for _, d, a, b, p in re.findall(r"^(\d+)\s+(\d\d/\d\d/\d{4})\s+(\d+)\s+(\d+)\s+(" + NUM + r")$", text, re.M)]
    f["directors"] = [{"din": din, "name": name.strip(), "entitled": int(a), "attended": int(b), "agm": agm}
                      for _, din, name, a, b, _p, agm in
                      re.findall(r"^(\d+) (\d{8}) (.+?) (\d+) (\d+) (" + NUM + r") (Yes|No|NA)$", text, re.M)]
    # IX remuneration of MD / WTD / Manager: amounts row "1 900000 0 0 0 900000.00"
    rem = []
    s = re.search(r"A \*Number of Managing Director", text)
    e = re.search(r"B \*Number of other directors", text)
    if s and e:
        block = text[s.start():e.start()]
        for sno, gross, comm, stock, oth, tot in re.findall(
                r"^(\d+)\s+(" + NUM + r")\s+(" + NUM + r")\s+(\d+\s*\d*)\s+(" + NUM + r")\s+(" + NUM + r")$", block, re.M):
            rem.append({"sno": int(sno), "gross": float(gross), "total": float(tot),
                        "designation": "Whole-time director" if "Whole-time" in block else "Managing Director"})
    for r_ in rem:  # names: same order as the attendance table in practice
        if r_["sno"] - 1 < len(f["directors"]):
            r_["name"] = f["directors"][r_["sno"] - 1]["name"]
    f["remuneration"] = rem
    nxt, _ = _after(lines, r"\(a\) DIN/PAN/Membership number of Designated Person")
    m = re.search(r"Designated Person\s+(\S+)", text)
    f["designated_din"] = m.group(1) if m else None
    nxt, _ = _after(lines, r"\(b\) Name of the Designated Person")
    f["designated_name"] = nxt[0] if nxt else None
    m = re.search(r"Number of shareholder/ debenture holder\s+(\d+)", text)
    f["n_holders_listed"] = int(m.group(1)) if m else None
    m = re.search(r"resolution number\*?\s*(\S+)\s+dated", text)
    f["resolution_no"] = m.group(1) if m else None
    m = re.search(r"DIN1\s+(\d{8})", text)
    f["signing_din"] = m.group(1) if m else None
    f["penalties_nil"] = bool(re.search(r"PUNISHMENT IMPOSED ON COMPANY/\s*Nil", text))
    f["compounding_nil"] = bool(re.search(r"COMPOUNDING OF OFFENCES\s+Nil", text))
    return f


def find_last_mgt7a(folder):
    for p in sorted(Path(folder).rglob("*.pdf")):
        if re.search(r"mgt[-_ ]?7a", p.name, re.I):
            return p
    return None


def read_aoc4(path):
    """Last year's filed AOC-4: the non-financial facts that usually carry forward."""
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        radios = _radios(pdf)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    f = {"source": path.name}

    def radio(*keys):
        for _, _, word, line in radios:
            if all(k.lower() in line.lower() for k in keys):
                return word
        return None

    def after(pat, n=1):
        nxt, _ = _after(lines, pat, n)
        return nxt[0] if nxt else None

    m = re.search(r"\*From \(DD/MM/YYYY\)\s+(\d\d/\d\d/\d{4})\s+\*To \(DD/MM/YYYY\)\s+(\d\d/\d\d/\d{4})", text)
    f["fy_from"], f["fy_to"] = (m.group(1), m.group(2)) if m else (None, None)
    m = re.search(r"financial statements are approved\s+(\d\d/\d\d/\d{4})", text)
    f["board_fs_date"] = m.group(1) if m else None
    f["nature_fs"] = after(r"\(b\) \(i\) \*Nature of financial statements")
    # signatories: "00972002 CHITRA RAJENDIRAN Director 29/09/2025" (name may wrap to next line)
    sig = []
    for din, name, desig, d in re.findall(r"^(\d{8}|[A-Z]{5}\d{4}[A-Z])\s+(.*?)\s*(Director|Managing Director|Whole-time director|CFO|CEO|Company Secretary|Manager)\s+(\d\d/\d\d/\d{4})$", text, re.M):
        sig.append({"din": din, "name": name.strip(), "designation": desig, "date": d})
    half = len(sig) // 2 if len(sig) >= 2 and len(sig) % 2 == 0 else len(sig)
    f["fs_signatories"], f["report_signatories"] = sig[:half], sig[half:]
    m = re.search(r"boards' report referred under section\s+(\d\d/\d\d/\d{4})", text)
    f["board_report_date"] = m.group(1) if m else None
    m = re.search(r"by the auditors \(DD/MM/YYYY\)\s+(\d\d/\d\d/\d{4})", text)
    f["auditor_report_date"] = m.group(1) if m else None
    f["agm_held"] = radio("annual general meeting") or radio("AGM Details")
    m = re.search(r"\(b\) If yes, date of AGM \(DD/MM/YYYY\)\s+(\d\d/\d\d/\d{4})", text)
    f["agm_date"] = m.group(1) if m else None
    if not f["agm_held"]:
        f["agm_held"] = "Yes" if f["agm_date"] else None
    f["agm_extension"] = radio("extension for AGM")
    f["is_subsidiary"] = radio("is a subsidiary company")
    f["has_subsidiary"] = radio("has a subsidiary company")
    m = re.search(r"\*SRN of Form ADT-1\s+(\S+)\s+\*Number of Auditors\s+(\d+)", text)
    f["adt1_srn"], f["n_auditors"] = (m.group(1), int(m.group(2))) if m else (None, None)
    f["auditor"] = {
        "pan": after(r"\(a\) \*Income-tax PAN of auditor"),
        "category": radio("Category of auditor"),
        "membership_or_frn": after(r"\(c\) \*Membership number of auditor"),
        "name": after(r"\(d\) \*Name of the auditor"),
        "address1": after(r"^\*Address Line 1$"), "address2": after(r"^Address Line 2$"),
        "country": after(r"^\*Country$"), "pin": after(r"^\*Pin Code/Zip Code$"),
        "area": after(r"^\*Area/Locality$"), "city": after(r"^\*City$"),
        "district": after(r"^\*District$"), "state": after(r"^\*State/UT$"),
    }
    f["industry"] = after(r"10 \(a\) \*Type of Industry")
    f["sch3_applicable"] = radio("Schedule III")
    f["consolidated"] = radio("consolidated financial statements")
    f["books_electronic"] = radio("electric form") or radio("maintaining books of account")
    f["lease_converted"] = radio("operating lease")
    f["cost_records"] = radio("maintenance of cost records")
    f["related_party"] = radio("transactions entered with related party")
    f["secretarial_audit"] = radio("Secretarial Audit is applicable")
    f["csr"] = after(r"1 CSR applicability pursuant to")
    m = re.search(r"\*Total number of product/ services category\(ies\)\s+(\d+)", text)
    f["n_products"] = int(m.group(1)) if m else None
    # product rows: "<4-digit code> ... <turnover> <8-digit code> <turnover>"
    # Product description: the capitalised words of the product block (e.g. "WHOLESALE TRADE SERVICES")
    blk = re.search(r"service category.*?digit code\)(.*?)Note - Please refer", text, re.S)
    words = re.findall(r"\b[A-Z][A-Z&/-]{2,}\b", blk.group(1)) if blk else []
    f["product_desc"] = " ".join(w for w in words if w not in ("ITC", "NPCS")) or None
    f["products"] = [{"code4": a, "turnover4": b, "code8": c, "turnover8": d}
                     for a, b, c, d in re.findall(r"^(\d{4})\s+.*?(\d+(?:\.\d+)?)\s+(\d{8})\s+(\d+(?:\.\d+)?)$", text, re.M)]
    m = re.search(r"resolution number\*\s+dated\*\s+(\S+)", text)
    f["resolution_no"] = m.group(1) if m else None
    m = re.search(r"DIN1\s+(\d{8})", text)
    f["signing_din"] = m.group(1) if m else None
    m = re.search(r"Rent paid\s+(\d+)", text)
    f["has_rent"] = bool(m)
    return f


def find_last_aoc4(folder):
    for p in sorted(Path(folder).rglob("*.pdf")):
        if re.search(r"aoc[-_ ]?4", p.name, re.I):
            return p
    return None


# ---------------------------------------------------------------- last year's AOC-4 figures

_NUM = r"-?\(?\d[\d,]*(?:\.\d+)?\)?"


def _fig(s):
    s = s.replace(",", "")
    neg = s.startswith("(") or s.startswith("-")
    v = float(s.strip("()-"))
    return -v if neg else v


def _key(label):
    """Row label without numbering / punctuation, for matching portal rows to PDF rows."""
    s = label.lower().replace("&", "and")
    s = re.sub(r"^\s*(\(?[ivxlc]+\)|\(?[a-z]\)|\d+|[a-z])\s+", "", s)   # (iv) (d) 2 a
    s = re.sub(r"^\s*(\(?[ivxlc]+\)|\(?[a-z]\))\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def read_aoc4_figures(path):
    """Ordered [(row label, current-year figure)] from last year's AOC-4: balance sheet, its break-ups and P&L.
    Last year's current-year column is this year's previous-year column."""
    with pdfplumber.open(Path(path)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines) if re.search(r"PART I\s*.\s*BALANCE SHEET", l, re.I)), 0)
    rows, pending = [], ""
    for l in lines[start:]:
        if re.match(r"^Page \d+ of \d+$", l):
            continue
        m = re.match(rf"^(.*?)\s*({_NUM})\s+({_NUM})$", l)
        if m and re.search(r"[A-Za-z]", m.group(1) or ""):
            rows.append((m.group(1), _fig(m.group(2))))
            pending = ""
            continue
        if m and not m.group(1):
            if pending:
                rows.append((pending, _fig(m.group(2))))
            pending = ""
            continue
        mm = re.match(rf"^({_NUM})\s+({_NUM})$", l)
        if mm:
            if pending:
                rows.append((pending, _fig(mm.group(1))))
            pending = ""
            continue
        # a label (or the first line of one that wraps)
        pending = l
    return rows


def match_previous(fields, rows, window=60):
    """fields: ordered [(key, row label)] of this year's previous-year inputs.
    Returns {key: figure} for the rows found, walking both lists in order."""
    out, j = {}, 0
    for key, label in fields:
        want = _key(label)
        if len(want) < 4:
            continue
        for k in range(j, min(len(rows), j + window)):
            have = _key(rows[k][0])
            if have and (have == want or (min(len(have), len(want)) >= 10 and (have.startswith(want) or want.startswith(have)))):
                out[key] = rows[k][1]
                j = k + 1
                break
    return out
