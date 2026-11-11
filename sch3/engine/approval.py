"""Mapping approval: compares the plain Tally default with the proposed Schedule III head for every ledger
and sorts the differences into the buckets the approval screen shows."""
import datetime as dt
from mapping import HEAD, LINES, HEADS, G_DEF, L_BASE, resolve, suggest, line_of, group_code

SECTION = {}
for _s, _ls in [("Shareholders' funds", "SC RS MRSW SAM"), ("Non-current liabilities", "LTB DTL OLTL LTP"),
                ("Current liabilities", "STB TP OCL STP"), ("Non-current assets", "PPE INT CWIP IAUD NCI DTA LTLA ONCA"),
                ("Current assets", "CI INV TR CCE STLA OCA"), ("Income", "REV OI"),
                ("Expenses", "COMC PUR CHINV EMP FIN DEP OEXP"), ("Exceptional items and tax", "EXC EXO TAXC TAXD")]:
    for _l in _ls.split(): SECTION[_l] = _s

BUCKETS = [
    ("section", "Section changes", "Tally places the ledger in one Schedule III section; the proposal moves it to another (e.g. Indirect Expenses to Tax expense, Current Liabilities to Long-term borrowings)."),
    ("head", "Head changes within the same section", "Same section, different line or sub-head (e.g. Provisions to Other current liabilities)."),
    ("contra", "Contra balances (firm default)", "Ledger balance is opposite to its group's nature: debtor Cr to advance from customer, creditor Dr to advance to supplier, bank Cr to OD."),
    ("unmapped", "Not mapped", "No rule found. Pick a head."),
    ("borrow", "Borrowings - confirm related party and LT/ST", "Loans taken. Confirm whether each lender is a director/related party. LT/ST split is entered below and never moved automatically."),
    ("same", "No change from Tally", "Tally group maps straight to a Schedule III head."),
]


def head_options():
    return [{"code": h[0], "label": f"{LINES[h[1]]} - {h[3]}", "line": h[1], "section": SECTION.get(h[1], "")} for h in HEADS]


def _desc(code):
    if not code or code not in HEAD: return {"code": code or "", "line": "", "label": "-", "section": ""}
    h = HEAD[code]
    return {"code": code, "line": LINES[h[1]], "label": h[3], "section": SECTION.get(h[1], "")}


def _client_groups(cfg):
    return [tuple(g) for g in cfg.get("groups", [])] + list(G_DEF)


def _client_ledgers(cfg):
    return [tuple(l) for l in L_BASE] + [tuple(l) for l in cfg.get("ledgers", [])]


def analyse(cy_rows, py_rows, cfg):
    groups, ledgers = _client_groups(cfg), _client_ledgers(cfg)
    lmap = {l[0].lower() for l in ledgers}
    gset = {g[0].lower() for g in cfg.get("groups", [])}
    approvals = {k.lower(): v for k, v in cfg.get("approvals", {}).items()}
    py = {r["ledger_name"]: r for r in py_rows}
    cy = {r["ledger_name"]: r for r in cy_rows}
    out = []
    for name in list(cy) + [n for n in py if n not in cy]:
        r = cy.get(name) or py[name]
        c_amt = cy[name]["closing_balance"] if name in cy else 0.0
        p_amt = py[name]["closing_balance"] if name in py else 0.0
        if abs(c_amt) < 0.005 and abs(p_amt) < 0.005 and name.lower() != "profit & loss a/c":
            continue
        g, prim = r["group_name"], r["primary_group"]
        amt = c_amt if abs(c_amt) >= 0.005 else p_amt
        base = resolve(name, g, prim, amt, list(L_BASE), list(G_DEF))
        base_nc = group_code(g, prim, list(G_DEF))[0]
        src, reason = "Tally default", ""
        appr = approvals.get(name.lower())
        if name.lower() in lmap or g.lower() in gset or prim.lower() in gset or appr:
            prop = resolve(name, g, prim, amt, ledgers, groups)
            src = "Approved earlier"
            note = next((l[3] for l in ledgers if l[0].lower() == name.lower()), "") or \
                next((x[3] for x in groups if x[0].lower() in (g.lower(), prim.lower())), "")
            reason = note
            if appr: reason = f"Approved by {appr.get('by','')} on {appr.get('on','')}" + (f" - {note}" if note else "")
        else:
            s = suggest(name, g, prim)
            if s:
                prop, src, reason = s[0], "Rule", s[2]
                if s[1] and amt * HEAD[s[0]][4] < 0: prop = s[1]
            else:
                prop = resolve(name, g, prim, amt, ledgers, groups)
                reason = next((x[3] for x in groups if x[0].lower() in (g.lower(), prim.lower())), "")
        bl, pl = line_of(base), line_of(prop)
        if not prop:
            kind = "unmapped"
        elif pl in ("LTB", "STB") and HEAD[prop][3].lower().find("unsecured") >= 0 or pl in ("LTB", "STB") and "related" in HEAD[prop][3].lower():
            kind = "borrow"
        elif prop == base:
            kind = "contra" if base != base_nc else "same"
        elif SECTION.get(bl) != SECTION.get(pl):
            kind = "section"
        else:
            kind = "head"
        warn = ""
        if base and prop and HEAD[base][2] != HEAD[prop][2]:
            warn = "Tally treats this as a " + ("Profit and Loss" if HEAD[base][2] == "PL" else "Balance Sheet") + \
                   " ledger; this head is in the " + ("Profit and Loss" if HEAD[prop][2] == "PL" else "Balance Sheet")
        out.append({"warn": warn, "ledger": name, "group": g, "primary": prim, "cy": round(c_amt, 2), "py": round(p_amt, 2),
                    "tally": _desc(base), "proposed": _desc(prop), "kind": kind, "source": src, "reason": reason,
                    "approved": src == "Approved earlier" or kind == "same"})
    return out


def apply_decisions(cfg, rows, decisions, user, fy):
    """decisions: {ledger: code} for accepted rows. Writes ledger overrides only where the group rules
    would give a different answer, and records who approved what."""
    groups = _client_groups(cfg)
    byname = {r["ledger"]: r for r in rows}
    led = {l[0].lower(): list(l) for l in cfg.get("ledgers", [])}
    appr = cfg.setdefault("approvals", {})
    today = dt.date.today().strftime("%d-%m-%Y")
    for name, code in decisions.items():
        r = byname.get(name)
        if not r or code not in HEAD: continue
        amt = r["cy"] if abs(r["cy"]) >= 0.005 else r["py"]
        by_group = resolve(name, r["group"], r["primary"], amt, list(L_BASE), groups)
        if code == by_group:
            led.pop(name.lower(), None)
        else:
            led[name.lower()] = [name, code, "", f"Approved by {user} on {today} (FY {fy})"]
        appr[name] = {"code": code, "by": user, "on": today, "fy": fy}
    cfg["ledgers"] = sorted(led.values(), key=lambda l: l[0].lower())
    return cfg
