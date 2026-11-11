"""Party-wise interest on loans taken, for the SAP related-party table.
Reusable across clients. Steps:
 1. In Tally, call ledger-account for each lender ledger (FY dates) -> tableIDs.
 2. Save "Party|tableID" lines to a file; run:  rp_interest.py sql <pairs.txt>
    and pass the printed SQL to query-database (one compact row per party).
 3. Save that JSON result; run:  rp_interest.py split <result.json> <client.json> [--net TDS%]
    Prints totals by related-party class (KMP / relatives incl. HUFs / enterprise / unrelated).
Amounts are journal credits to the party (interest). Use --net 10 when credits are net of TDS
(gross worked back); omit when the journal credits are already gross."""
import sys, json, math
from collections import defaultdict

def sql(pairs):
    rows = [l.strip().split("|") for l in open(pairs) if "|" in l]
    return " UNION ALL ".join(
        f"SELECT '{n.replace(chr(39), chr(39)*2)}' AS p, SUM(amount) AS a FROM {t} WHERE voucher_type='Journal' AND amount>0"
        for n, t in rows)

def gross(n, pct):
    r = pct / 100
    for g in range(int(n / (1 - r)) - 3, int(n / (1 - r)) + 4):
        if g - math.floor(g * r + 0.5) == n or g - math.ceil(g * r) == n: return g
    return round(n / (1 - r))

def split(res, cfg, pct=None):
    data = {x["p"]: round(x["a"] or 0) for x in json.load(open(res))}
    rp = json.load(open(cfg))["related_parties"]
    cls = {r[1]: r[2] for r in rp if r[3] == "loan_taken"}
    kmp = next((r[2] for r in rp if "Key management" in r[2]), "")
    ent = next((r[2] for r in rp if r[2].startswith("Enterprises")), "")
    out = defaultdict(int); parties = {}
    for p, v in data.items():
        if not v: continue
        g = gross(v, pct) if pct else v
        c = cls.get(p); k = "unrelated" if c is None else "kmp" if c == kmp else "ent" if c == ent else "rel"
        out[k] += g; parties[p] = (k, v, g)
    return dict(out), parties

if __name__ == "__main__":
    if sys.argv[1] == "sql": print(sql(sys.argv[2]))
    else:
        pct = float(sys.argv[sys.argv.index("--net") + 1]) if "--net" in sys.argv else None
        tot, parties = split(sys.argv[2], sys.argv[3], pct)
        print(json.dumps({"totals": tot, "total": sum(tot.values()), "parties": parties}, indent=0))
