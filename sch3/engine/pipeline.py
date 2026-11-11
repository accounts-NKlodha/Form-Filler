"""Build -> cache formula values (pycel) -> hide nil sub-head rows. Used by the app and from the command line."""
import os, sys, subprocess, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, log):
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=HERE)
    if log: log((p.stdout or "") + (p.stderr or ""))
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "failed")[-2000:])


def build_workbook(cfg_path, cy_csv, py_csv, out_path, log=None):
    tmp = tempfile.mkdtemp(prefix="sch3_")
    raw, cached = os.path.join(tmp, "raw.xlsx"), os.path.join(tmp, "cached.xlsx")
    if log: log("Building workbook...")
    run([os.path.join(HERE, "build_sch3.py"), cfg_path, cy_csv, py_csv or "-", raw], log)
    if log: log("Calculating every formula (1-3 minutes)...")
    run([os.path.join(HERE, "cache_values.py"), raw, cached], log)
    run([os.path.join(HERE, "hide_zero_rows.py"), cached, raw + ".subrows.json", out_path], log)
    shutil.rmtree(tmp, ignore_errors=True)
    if log: log("Done: " + out_path)
    return out_path


if __name__ == "__main__":
    build_workbook(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], print)
