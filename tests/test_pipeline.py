"""End-to-end check on the mock form: dump -> mapping -> inputs workbook -> plan -> fill.

    python tests/test_pipeline.py <schedule III workbook> <scratch dir>
Uses the slug 'mocktest' and removes its dump / mapping afterwards. Prints statuses
and pass/fail only, never figures from the workbook.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import mca  # noqa: E402

VENV_PY = HERE.parents[1] / "spike" / ".venv" / "Scripts" / "python.exe"


def main():
    fs_src, scratch = Path(sys.argv[1]), Path(sys.argv[2])
    client = scratch / "Test Client"
    shutil.rmtree(client, ignore_errors=True)
    client.mkdir(parents=True)
    shutil.copy(fs_src, client / fs_src.name)
    try:
        subprocess.run([str(VENV_PY), str(HERE / "run_page.py"), "dump", str(scratch / "dump.json")], check=True)
        mca.DUMPS.mkdir(exist_ok=True)
        shutil.copy(scratch / "dump.json", mca.DUMPS / "mocktest.json")

        path, n, hits = mca.build_map("mocktest")
        wb = openpyxl.load_workbook(path)
        ws = wb["Map"]
        for row in ws.iter_rows(min_row=3):
            lab = row[2].value
            if lab.startswith("(a) Share capital"):
                row[4].value = "BS:Share capital"
            if lab.startswith("(b) Reserves"):
                row[4].value = "BS:Reserves and surplus"
            print("map", row[0].value, row[3].value, "|", lab[:40])
        wb.save(path)

        out, problems, fs_error = mca.build_workbook(client, ["mocktest"])
        print("workbook", out.name, "fs_error", fs_error, "problems", problems)
        wb = openpyxl.load_workbook(out)
        ws = wb["MOCKTEST"]
        vals = {"Corporate identity number": "U12345TN2000PTC000001", "Date of Board meeting": "29/09/2025",
                "Nature of financial statements": "Adopted Financial statements", "Whether AGM held": "No"}
        green = 0
        for row in ws.iter_rows(min_row=4):
            lab = str(row[2].value or "")
            for k, v in vals.items():
                if k in lab:
                    row[5].value = v
            if row[5].fill.fgColor.rgb.endswith("E2F0D9"):
                green += 1
        print("green (from FS) cells:", green)
        ts = wb["MOCKTEST T1"]
        ts["A5"], ts["B5"], ts["A6"], ts["B6"] = "00000001", "First Signatory", "00000002", "Second Signatory"
        wb.save(out)

        # Rebuild must keep typed values.
        mca.build_workbook(client, ["mocktest"])
        plan = mca.make_plan(out, "mocktest")
        print("plan fields", [(f["code"], f["type"]) for f in plan["fields"]], "tables", len(plan["tables"]),
              "rows", [len(t["rows"]) for t in plan["tables"]], "errors", plan["errors"])
        (scratch / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        subprocess.run([str(VENV_PY), str(HERE / "run_page.py"), "fill", str(scratch / "plan.json"), str(scratch / "fill.json")], check=True)
        res = json.loads((scratch / "fill.json").read_text(encoding="utf-8"))
        for e in res["log"]:
            print("log", e.get("code"), e["status"], e.get("method", ""), e.get("msg", ""), "|", e["label"][:50])
        print("save", res["save"], "clicks", res["clicks"])
        dom, model = res["dom"], res["model"]
        checks = {
            "cin": dom["partA-guidetextbox_cin___widget"] == vals["Corporate identity number"],
            "date": dom["partA-guidedatepicker_bm___widget"] == "29/09/2025",
            "dropdown": dom["partA-guidedropdownlist_nat___widget"] == "A",
            "radio": dom["partA-guideradiobutton_agm__-2_widget"] is True,
            "readonly kept": dom["partA-guidetextbox_mail___widget"] == "x@y.z",
            "sc cy filled": dom["bs-table-Row1-numericbox_sc_cy___widget"] != "",
            "sc py untouched": dom["bs-table-Row1-numericbox_sc_py___widget"] == "",
            "table row 2": model.get("guide[0].guide1[0].guideRootPanel[0].sig[0].sigrow[1].nm[0]") == "Second Signatory",
            "no button clicked (staff click Save)": res["clicks"] == [] and res["save"].get("highlighted"),
        }
        for k, ok in checks.items():
            print("PASS" if ok else "FAIL", k)
        return all(checks.values())
    finally:
        for p in (mca.DUMPS / "mocktest.json", mca.map_path("mocktest")):
            p.unlink(missing_ok=True)
        for p in (mca.DUMPS / "archive").glob("mocktest_*.json") if (mca.DUMPS / "archive").exists() else []:
            p.unlink()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
