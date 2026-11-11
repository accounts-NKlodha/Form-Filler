"""Read figures from the firm's Schedule III workbook (Setup / BS / PL / Notes sheets).

Figures are looked up by label, never by cell address, so rows can move between
clients. A source expression names one or more terms joined by + or -:

    BS:Long-term borrowings
    PL:Finance costs
    Notes:Other expenses/Insurance            note heading / row label
    Notes:Property, plant and equipment/Total@Closing WDV   pick a column by header
    Setup:Authorised share capital (Rs) - current year
    0

Labels match after normalising (case, punctuation and leading "(a)", "IV.", "(ii)"
numbering are ignored); an exact match wins, otherwise a unique prefix match.
Each term is read for the period asked for: CY = first amount column, PY = second.
"""
import re
from pathlib import Path

import openpyxl

ENUM = re.compile(r"^\s*(\(?([ivxlc]+|[a-z]|\d+)[\).]\s*)+", re.I)


def norm(s):
    s = ENUM.sub("", str(s or ""))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class FSError(Exception):
    pass


class Schedule3:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.wb = openpyxl.load_workbook(self.path, data_only=True, read_only=False)
        except Exception as e:  # noqa: BLE001 - surfaced to the user as is
            raise FSError(f"cannot open {self.path.name}: {e}")
        missing = [s for s in ("BS", "PL", "Notes") if s not in self.wb.sheetnames]
        if missing:
            raise FSError(f"{self.path.name} is not a Schedule III workbook (missing sheets {', '.join(missing)})")
        self._check_cached_values()
        try:
            self.divisor = float(self.setup("Rounding divisor") or 1)
        except (TypeError, ValueError):
            raise FSError("Setup rounding divisor is not a number")
        if self.divisor <= 0:
            raise FSError("Setup rounding divisor must be 1, 100, 1000 or 100000")
        # Figures on BS / PL / Notes are divided by this; MCA needs absolute rupees, so they are
        # multiplied back (the workbook keeps full precision, so nothing is lost).

    # ---- checks -------------------------------------------------------
    def _check_cached_values(self):
        ws = self.wb["BS"]
        nums = [c.value for row in ws.iter_rows(min_col=3, max_col=4) for c in row if isinstance(c.value, (int, float))]
        if not nums:
            raise FSError(f"{self.path.name} has no saved figures on the BS sheet. Open it in Excel, "
                          "let it recalculate, save, close, and try again.")

    def checks(self):
        """Lines of the workbook's own Checks sheet that do not read OK."""
        if "Checks" not in self.wb.sheetnames:
            return []
        bad = []
        ws = self.wb["Checks"]
        for row in ws.iter_rows(min_row=4, values_only=True):
            if not row or not row[0] or len(row) < 4 or not isinstance(row[3], str):
                break  # the status block ends at the first row without a text status
            if row[3].strip() != "OK":
                bad.append(f"{row[0]}: {row[3]}")
        return bad

    # ---- lookups ------------------------------------------------------
    def setup(self, label):
        ws = self.wb["Setup"] if "Setup" in self.wb.sheetnames else None
        if ws is None:
            return None
        want = norm(label)
        for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
            if row[0] and norm(row[0]).startswith(want):
                return row[1]
        return None

    @staticmethod
    def _pick(rows, want, what):
        exact = [r for r in rows if r[0] == want]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise FSError(f"{what}: label appears {len(exact)} times")
        pre = [r for r in rows if r[0].startswith(want)]
        if len(pre) == 1:
            return pre[0]
        if len(pre) > 1:
            raise FSError(f"{what}: label is ambiguous ({len(pre)} rows start with it)")
        raise FSError(f"{what}: label not found")

    def _amount_cols(self, ws, header_row, label_col):
        """Amount columns of a block: (header text, column index) after the label column."""
        cols = []
        for c in range(label_col + 1, ws.max_column + 1):
            h = ws.cell(header_row, c).value
            if isinstance(h, str) and h.strip() and not norm(h).startswith("note"):
                cols.append((h, c))
        return cols

    def _statement(self, sheet, label, period, col):
        ws = self.wb[sheet]
        header = next((r for r in range(1, 15) if norm(ws.cell(r, 1).value) == "particulars"), None)
        if header is None:
            raise FSError(f"{sheet}: no 'Particulars' header row")
        rows = [(norm(ws.cell(r, 1).value), r) for r in range(header + 1, ws.max_row + 1) if ws.cell(r, 1).value]
        _, r = self._pick(rows, norm(label), f"{sheet}:{label}")
        return self._value(ws, header, 1, r, period, col, f"{sheet}:{label}")

    def _note(self, heading, label, period, col):
        ws = self.wb["Notes"]
        heads = [(norm(ws.cell(r, 2).value), r) for r in range(1, ws.max_row + 1)
                 if isinstance(ws.cell(r, 1).value, (int, float)) and ws.cell(r, 2).value]
        _, h = self._pick(heads, norm(heading), f"Notes:{heading}")
        nxt = min([r for _, r in heads if r > h], default=ws.max_row + 1)
        header = h + 1
        rows = [(norm(ws.cell(r, 2).value), r) for r in range(header + 1, nxt) if ws.cell(r, 2).value]
        _, r = self._pick(rows, norm(label), f"Notes:{heading}/{label}")
        return self._value(ws, header, 2, r, period, col, f"Notes:{heading}/{label}")

    def _value(self, ws, header, label_col, r, period, col, what):
        cols = self._amount_cols(ws, header, label_col)
        if col:
            match = [c for h, c in cols if norm(h).startswith(norm(col))]
            if not match:
                raise FSError(f"{what}: no column '{col}'")
            c = match[0]
        else:
            if len(cols) < 2:
                raise FSError(f"{what}: block has no current / previous year columns")
            c = cols[0][1] if period == "CY" else cols[1][1]
        v = ws.cell(r, c).value
        if v is None or v == "" or v == "-":
            return 0
        if not isinstance(v, (int, float)):
            raise FSError(f"{what}: cell {ws.cell(r, c).coordinate} is not a number")
        return v * self.divisor

    def term(self, term, period):
        term = term.strip()
        # "Notes:Other expenses/Payment to auditor - statutory audit|Audit fees": row labels differ
        # between clients, so try each alternative in turn (same sheet and note heading).
        if "|" in term:
            first, *alts = term.split("|")
            sheet_, rest_ = first.split(":", 1) if ":" in first else ("", first)
            head = f"{sheet_}:{rest_.split('/', 1)[0]}/" if sheet_.strip().lower() == "notes" else f"{sheet_}:"
            last_err = None
            for cand in [first] + [head + a.strip() for a in alts]:
                try:
                    return self.term(cand, period)
                except FSError as e:
                    last_err = e
            raise last_err
        if re.fullmatch(r"-?\d+(\.\d+)?", term):
            return float(term)
        col = None
        if "@" in term:
            term, col = term.rsplit("@", 1)
        if ":" not in term:
            raise FSError(f"'{term}': expected Sheet:Label")
        sheet, label = term.split(":", 1)
        sheet = sheet.strip()
        if sheet.lower() == "setup":
            v = self.setup(label)
            if v is None:
                raise FSError(f"Setup:{label} not found or blank")
            return v
        if sheet.upper() in ("BS", "PL"):
            return self._statement(sheet.upper(), label, period, col)
        if sheet.lower() == "notes":
            if "/" not in label:
                raise FSError(f"Notes:{label}: expected Notes:Heading/Row label")
            heading, row = label.split("/", 1)
            return self._note(heading, row, period, col)
        raise FSError(f"unknown sheet '{sheet}' (use BS, PL, Notes or Setup)")

    def eval(self, expr, period="CY"):
        """Evaluate a source expression for CY or PY. Returns a number."""
        expr = str(expr or "").strip()
        if not expr:
            raise FSError("empty expression")
        total, sign = 0.0, 1
        # Split on + / - only where they stand alone between terms (labels contain hyphens).
        for part in re.split(r"\s+([+-])\s+(?=(?:BS|PL|Notes|Setup)\s*:|\d)", expr, flags=re.I):
            if part == "+":
                sign = 1
            elif part == "-":
                sign = -1
            else:
                total += sign * float(self.term(part, period))
        return round(total, 2)


def find_schedule3(folder):
    """The Schedule III workbook in a client folder: an .xlsx with BS, PL and Notes sheets.

    filing.json "schedule3" (set when Form Filler builds the workbook from Tally) wins over any other copy."""
    try:
        import json
        pick = json.loads((Path(folder) / "filing.json").read_text(encoding="utf-8")).get("schedule3")
        if pick and (Path(folder) / pick).exists():
            return Path(folder) / pick
    except Exception:  # noqa: BLE001
        pass
    for p in sorted(Path(folder).glob("*.xlsx")):
        if p.name.startswith("~$") or "mca inputs" in p.name.lower():
            continue
        try:
            names = openpyxl.load_workbook(p, read_only=True).sheetnames
        except Exception:  # noqa: BLE001
            continue
        if {"BS", "PL", "Notes"} <= set(names):
            return p
    return None
