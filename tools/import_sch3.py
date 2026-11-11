"""Bring clients from the old Schedule III app (port 8765) into Form Filler.

    python tools\\import_sch3.py "E:\\Projects\\Schedule III\\_Schedule III App\\Schedule-III-App"

For each clients\\<slug>.json of the old app: finds the Form Filler client folder with the same name (or
creates one), copies the config to <client>\\financials\\config.json and the old app's data\\<slug>\\<FY>
files (trial balances, last year's Schedule III and AOC-4) to <client>\\financials\\<FY>. Nothing in the
old app's folder is changed. A client that already has financials\\config.json is skipped unless --force.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402


def key(s):
    s = re.sub(r"\b(private|pvt|limited|ltd|llp|opc)\b", " ", str(s).lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def main(src, force=False):
    src = Path(src)
    have = {key(p.name): p for p in app.CLIENTS.iterdir() if p.is_dir()} if app.CLIENTS.exists() else {}
    for cf in sorted((src / "clients").glob("*.json")):
        cfg = json.loads(cf.read_text(encoding="utf-8"))
        name = cfg.get("client") or cf.stem
        folder = have.get(key(name)) or have.get(key(cf.stem))
        if not folder:
            folder = app.folder_of(re.sub(r"\s+(Private|Pvt\.?)\s+(Limited|Ltd\.?)$", " Pvt Ltd", name.strip()))
            folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "financials" / "config.json"
        if dest.exists() and not force:
            print(f"skip   {name}: {folder.name} already has financials")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cf, dest)
        fy = cfg.get("fy", "2025-26")
        n = 0
        for d in (src / "data" / cf.stem).glob("*"):
            if d.is_dir():
                out = folder / "financials" / d.name
                out.mkdir(parents=True, exist_ok=True)
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() in (".csv", ".xlsx", ".pdf", ".json") and not f.name.endswith(" - Schedule III FY" + d.name + ".xlsx"):
                        shutil.copyfile(f, out / f.name)
                        n += 1
        f = app.load(folder)
        if not f.get("forms"):
            s = cfg.get("setup", {})
            ar = str(s.get("Annual return form (MGT-7 or MGT-7A)", "")).upper().replace(" ", "")
            forms = ["aoc4"] + (["mgt7a"] if ar in ("", "MGT-7A") else [])
            app.save(folder, cin=f.get("cin") or s.get("CIN", ""), fy_end=f.get("fy_end") or f"31/03/{int(fy[:4]) + 1}", forms=forms)
        print(f"import {name} -> {folder.name} ({n} data files)")


if __name__ == "__main__":
    main(sys.argv[1], "--force" in sys.argv)
