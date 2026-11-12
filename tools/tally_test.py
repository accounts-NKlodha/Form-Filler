"""Find which Tally request is slow or hangs.  Usage:  python tools\\tally_test.py "Company name" [2025]
Sends simple requests first, then adds one field at a time. Stops at the first one that does not answer in 90 s.
Nothing is written to Tally."""
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sch3" / "engine"))
import tally  # noqa: E402

co = sys.argv[1] if len(sys.argv) > 1 else ""
y = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
frm, to = dt.date(y, 4, 1), dt.date(y + 1, 3, 31)
orig = tally._post
tally._post = lambda xml, host="localhost", port=9000, timeout=90: orig(xml, host, port, timeout=90)

steps = [
    ("Open companies", lambda: tally._collection("T1", "Company", ["StartingFrom"])),
    ("Group list", lambda: tally._collection("T2", "Group", ["Parent"], company=co)),
    ("Ledger names", lambda: tally._collection("T3", "Ledger", ["Parent"], company=co)),
    ("Ledger balances, no dates", lambda: tally._collection("T4", "Ledger", ["Parent", "OpeningBalance", "ClosingBalance"], company=co)),
    ("Trial balance for the year (new)", lambda: tally.trial_balance(co, frm, to)),
]
print(f"Company: {co!r}, year {frm} to {to}\n")
for name, fn in steps:
    t = time.time()
    print(f"{name:32}", end=" ", flush=True)
    try:
        rows = fn()
        print(f"OK  {len(rows):5} rows  {time.time() - t:6.1f} s")
    except Exception as e:  # noqa: BLE001
        print(f"FAILED after {time.time() - t:.0f} s: {str(e)[:150]}")
        print("\nStopped here. Send this window to Claude. If Tally says Not responding, close it from Task Manager.")
        break
else:
    print("\nAll requests answered.")
input("\nPress Enter to close")
