"""Mapping rules that decide a statutory line. Run: python tests/test_mapping_rules.py (synthetic names only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sch3" / "engine"))
from mapping import PL_AC, std_ledger, suggest  # noqa: E402
import approval  # noqa: E402


def row(name, group, closing, opening=0.0):
    return {"ledger_name": name, "group_name": group, "primary_group": group, "opening_balance": opening,
            "net_debit": 0.0, "net_credit": 0.0, "closing_balance": closing}


def main():
    # Tally's P&L account keeps its standard name however the company numbered it
    assert std_ledger("300001 Profit & Loss A/c", "Primary") == PL_AC
    assert std_ledger("Profit and Loss A/c", "") == PL_AC
    assert std_ledger("Profit & Loss A/c written off", "Indirect Expenses") != PL_AC
    # reserves kept under Capital Account go to Reserves and surplus, not Share capital
    assert suggest("113001 RESERVES & SURPLUS", "Capital Account", "Capital Account")[0] == "RS.SURP"
    assert suggest("General Reserve", "Capital Account", "Capital Account")[0] == "RS.GEN"
    assert suggest("Securities Premium", "Capital Account", "Capital Account")[0] == "RS.SEC"
    assert suggest("A B Shah - Share Capital A/c", "Capital Account", "Capital Account") is None
    cfg = {"groups": [], "ledgers": [], "approvals": {}}
    cy = [row("Reserves & Surplus", "Capital Account", 500.0), row("X - Share Capital", "Capital Account", 1000.0),
          row("Old ledger", "Indirect Expenses", 0.0), row("Odd ledger", "No Such Group", 0.0)]
    got = {r["ledger"]: r for r in approval.analyse(cy, [], cfg)}
    assert got["Reserves & Surplus"]["proposed"]["code"] == "RS.SURP" and not got["Reserves & Surplus"]["approved"]
    assert got["X - Share Capital"]["approved"]            # follows Tally's group: nothing to approve
    assert "Old ledger" not in got                          # nil in both years: not listed
    assert got["Odd ledger"]["kind"] == "unmapped"          # nil but no head at all: listed, the workbook flags it
    print("mapping rules: ok")


if __name__ == "__main__":
    main()


def test_coded_names_and_fdr():
    assert suggest("451120 INCOME TAX", "Indirect Expenses", "Indirect Expenses")[0] == "TAX.CUR"
    assert suggest("FDR NO 100200300400 - X01", "Investments", "Investments")[0] == "CCE.FD"
    assert suggest("452002 AUDIT FEES", "Indirect Expenses", "Indirect Expenses")[0] == "OEXP.AUD"
    assert suggest("330002 - INT FROM BANK FDR - ABC", "Indirect Incomes", "Indirect Incomes")[0] == "OI.INT"


test_coded_names_and_fdr()
print("coded names: ok")
