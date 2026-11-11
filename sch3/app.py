"""Schedule III app - local web UI (opens in the browser). Standard library only, plus openpyxl / pycel / pypdf.

    python app.py            -> this PC only, http://localhost:8765
    python app.py --lan      -> also reachable by team members at http://<this-PC-IP>:8765
"""
import datetime as dt, json, os, re, shutil, sys, threading, traceback, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))
import tally, approval, masters, ly_check, pipeline  # noqa: E402
from mapping import LINES  # noqa: E402
from setup_fields import FIELDS  # noqa: E402

SETTINGS_FILE = os.path.join(HERE, "settings.json")
SETTINGS = {"data_folder": os.path.join(HERE, "data"), "clients_folder": os.path.join(HERE, "clients"),
            "tally_host": "localhost", "tally_port": 9000, "port": 8765}
if os.path.exists(SETTINGS_FILE):
    SETTINGS.update(json.load(open(SETTINGS_FILE, encoding="utf-8")))
for k in ("data_folder", "clients_folder"):
    os.makedirs(SETTINGS[k], exist_ok=True)

BUILDS = {}  # slug -> {"state", "log": [...], "out"}
UPLOAD_KINDS = {"tb_cy": "tb_cy", "tb_py": "tb_py", "auditor": "auditor_master.xlsx", "roc": "roc_master.xlsx",
                "ly": "ly_schedule3.xlsx", "aoc4": "ly_aoc4.pdf"}


def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def cfg_path(slug): return os.path.join(SETTINGS["clients_folder"], slug + ".json")


def load_cfg(slug):
    return json.load(open(cfg_path(slug), encoding="utf-8"))


def save_cfg(slug, cfg):
    tmp = cfg_path(slug) + ".tmp"
    json.dump(cfg, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, cfg_path(slug))


def fy_dates(fy):
    y = int(fy[:4])
    return dt.date(y, 4, 1), dt.date(y + 1, 3, 31)


def work_dir(slug, fy):
    d = os.path.join(SETTINGS["data_folder"], slug, fy.replace("/", "-"))
    os.makedirs(d, exist_ok=True)
    return d


def files_of(slug, cfg):
    d = work_dir(slug, cfg["fy"])
    have = {}
    for k in ("tb_cy", "tb_py"):
        have[k] = os.path.exists(os.path.join(d, k + ".csv"))
    for k, fn in UPLOAD_KINDS.items():
        if k not in have: have[k] = os.path.exists(os.path.join(d, fn))
    have["output"] = os.path.exists(os.path.join(d, out_name(cfg)))
    return d, have


def out_name(cfg):
    return f"{cfg.get('client', 'Company')} - Schedule III FY{cfg['fy']}.xlsx".replace("/", "-")


def tb_rows(d, which):
    p = os.path.join(d, which + ".csv")
    return tally.read_tb(p) if os.path.exists(p) else []


def new_client(name, cin, fy):
    y = int(fy[:4])
    return {"client": name, "fy": fy, "tally_company_cy": name, "tally_company_py": name, "groups": [], "ledgers": [],
            "head_labels": {}, "approvals": {}, "review_points": [],
            "setup": {"Company name": name, "CIN": cin, "Current year - balance sheet date": f"31 March {y + 1}",
                      "Previous year - balance sheet date": f"31 March {y}",
                      "Rounding divisor (1 = Rs, 1000 = Rs '000, 100000 = Rs lakhs)": 1, "Amount label": "Amount in Rs",
                      "Annual return web link (or \"not hosted\")": "Not hosted"},
            "setup_notes": {}}


def roll_year(cfg):
    """Start next FY from this year's approved config: mappings and approvals are kept, year-specific inputs cleared."""
    y = int(cfg["fy"][:4]) + 1
    cfg = json.loads(json.dumps(cfg))
    cfg["fy"] = f"{y}-{str(y + 1)[2:]}"
    s = cfg["setup"]
    s["Current year - balance sheet date"] = f"31 March {y + 1}"
    s["Previous year - balance sheet date"] = f"31 March {y}"
    for k in ("Weighted avg. equity shares", "Authorised share capital (Rs)", "Long-term portion"):
        cur, prev = next((x for x in s if x.startswith(k) and x.endswith("current year")), None), \
            next((x for x in s if x.startswith(k) and x.endswith("previous year")), None)
        if cur and prev: s[prev] = s[cur]
    for k in list(s):
        if k.startswith(("Net profit", "Date of", "Board meeting", "UDIN", "Annual report number", "Directors present")):
            s.pop(k, None)
    cfg["setup_notes"] = {}
    cfg["review_points"] = []
    return cfg


def run_build(slug):
    st = BUILDS[slug] = {"state": "running", "log": [], "out": None}
    try:
        cfg = load_cfg(slug)
        d = work_dir(slug, cfg["fy"])
        cy, py = os.path.join(d, "tb_cy.csv"), os.path.join(d, "tb_py.csv")
        out = os.path.join(d, out_name(cfg))
        pipeline.build_workbook(cfg_path(slug), cy, py if os.path.exists(py) else None, out,
                                log=lambda m: st["log"].append(m.strip()) if m and m.strip() else None)
        st["out"] = out
        # checks summary
        import openpyxl
        ws = openpyxl.load_workbook(out, data_only=True)["Checks"]
        st["checks"] = [[str(c) if c is not None else "" for c in row[:4]] for row in ws.iter_rows(values_only=True)
                        if any(c not in (None, "") for c in row[:4])]
        div = float(cfg["setup"].get("Rounding divisor (1 = Rs, 1000 = Rs '000, 100000 = Rs lakhs)") or 1)
        if os.path.exists(os.path.join(d, "ly_schedule3.xlsx")):
            st["ly"] = ly_check.tie_ly_excel(out, os.path.join(d, "ly_schedule3.xlsx"), div)
        if os.path.exists(os.path.join(d, "ly_aoc4.pdf")):
            try:
                st["aoc4"] = ly_check.tie_aoc4(out, os.path.join(d, "ly_aoc4.pdf"), div)
            except Exception as e:
                st["aoc4"] = {"error": str(e)}
        st["state"] = "done"
        json.dump(st, open(os.path.join(d, "last_build.json"), "w", encoding="utf-8"), default=str)
    except Exception as e:
        st["state"] = "error"; st["log"].append(str(e)); st["log"].append(traceback.format_exc()[-1500:])


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        try: self.route("GET")
        except Exception as e: self._send(400, {"error": str(e)})

    def do_POST(self):
        try: self.route("POST")
        except Exception as e: self._send(400, {"error": str(e)})

    def route(self, method):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = [unquote(p) for p in u.path.strip("/").split("/") if p]
        if not parts or parts[0] in ("index.html",):
            return self._send(200, open(os.path.join(HERE, "ui", "index.html"), "rb").read(), "text/html; charset=utf-8")
        if parts[0] != "api": return self._send(404, {"error": "not found"})
        p = parts[1:]

        if p == ["settings"]:
            if method == "POST":
                SETTINGS.update(self._json()); json.dump(SETTINGS, open(SETTINGS_FILE, "w"), indent=1)
            return self._send(200, SETTINGS)
        if p == ["clients"]:
            if method == "POST":
                b = self._json(); slug = slugify(b["name"])
                if os.path.exists(cfg_path(slug)): raise ValueError("Client already exists")
                save_cfg(slug, new_client(b["name"].strip(), b.get("cin", "").strip().upper(), b["fy"]))
                return self._send(200, {"slug": slug})
            out = []
            for f in sorted(os.listdir(SETTINGS["clients_folder"])):
                if f.endswith(".json"):
                    try: c = json.load(open(os.path.join(SETTINGS["clients_folder"], f), encoding="utf-8"))
                    except Exception: continue
                    out.append({"slug": f[:-5], "name": c.get("client"), "fy": c.get("fy"), "cin": c.get("setup", {}).get("CIN", "")})
            return self._send(200, out)
        if p[:2] == ["tally", "companies"]:
            return self._send(200, tally.companies(q.get("host") or SETTINGS["tally_host"], int(q.get("port") or SETTINGS["tally_port"])))

        if p[0] != "client" or len(p) < 2: return self._send(404, {"error": "not found"})
        slug, act = p[1], (p[2] if len(p) > 2 else "")
        cfg = load_cfg(slug)
        d, have = files_of(slug, cfg)

        if act == "":
            return self._send(200, {"cfg": cfg, "files": have, "fields": FIELDS, "build": BUILDS.get(slug, {}).get("state")})

        if act == "nextyear" and method == "POST":
            if os.path.exists(os.path.join(d, out_name(cfg))):
                shutil.copy(os.path.join(SETTINGS["clients_folder"], slug + ".json"),
                            os.path.join(d, "client_config_final.json"))
            nc = roll_year(cfg); save_cfg(slug, nc)
            nd = work_dir(slug, nc["fy"])
            if os.path.exists(os.path.join(d, "tb_cy.csv")):
                shutil.copy(os.path.join(d, "tb_cy.csv"), os.path.join(nd, "tb_py.csv"))
            if have["output"]:
                shutil.copy(os.path.join(d, out_name(cfg)), os.path.join(nd, "ly_schedule3.xlsx"))
            return self._send(200, {"fy": nc["fy"]})

        if act == "tally" and method == "POST":
            b = self._json(); which = b["which"]
            fy = cfg["fy"] if which == "tb_cy" else f"{int(cfg['fy'][:4]) - 1}-{cfg['fy'][2:4]}"
            frm, to = fy_dates(fy)
            host, port = b.get("host") or SETTINGS["tally_host"], int(b.get("port") or SETTINGS["tally_port"])
            rows = tally.trial_balance(b["company"], frm, to, host, port)
            if not rows: raise ValueError("Tally returned no ledgers. Check the company is open and the FY dates.")
            tally.write_csv(rows, os.path.join(d, which + ".csv"))
            cfg["tally_company_cy" if which == "tb_cy" else "tally_company_py"] = b["company"]
            key = "Net profit as per Tally P&L - " + ("current year" if which == "tb_cy" else "previous year")
            cfg["setup"][key] = tally.net_profit(rows)
            cfg.setdefault("setup_notes", {})[key] = f"Tally '{b['company']}', {frm:%d-%b-%y} to {to:%d-%b-%y}, pulled {dt.date.today():%d-%b-%y}"
            save_cfg(slug, cfg)
            return self._send(200, {"ledgers": len(rows), "net_profit": cfg["setup"][key]})

        if act == "upload" and method == "POST":
            kind = q["kind"]; n = int(self.headers.get("Content-Length") or 0); data = self.rfile.read(n)
            fname = unquote(self.headers.get("X-Filename") or "")
            if kind in ("tb_cy", "tb_py"):
                ext = ".xlsx" if fname.lower().endswith((".xlsx", ".xlsm")) else ".csv"
                tmp = os.path.join(d, kind + "_upload" + ext)
                open(tmp, "wb").write(data)
                rows = tally.read_tb(tmp); tally.write_csv(rows, os.path.join(d, kind + ".csv"))
                key = "Net profit as per Tally P&L - " + ("current year" if kind == "tb_cy" else "previous year")
                cfg["setup"][key] = tally.net_profit(rows); save_cfg(slug, cfg)
                return self._send(200, {"ledgers": len(rows), "net_profit": cfg["setup"][key]})
            open(os.path.join(d, UPLOAD_KINDS[kind]), "wb").write(data)
            return self._send(200, {"saved": fname})

        if act == "rollforward":
            cy, py = tb_rows(d, "tb_cy"), tb_rows(d, "tb_py")
            if not cy or not py: return self._send(200, {"diffs": [], "note": "Fetch both years first"})
            return self._send(200, {"diffs": tally.roll_forward(py, cy),
                                    "cy_profit": tally.net_profit(cy), "py_profit": tally.net_profit(py)})

        if act == "mapping":
            cy, py = tb_rows(d, "tb_cy"), tb_rows(d, "tb_py")
            if method == "POST":
                b = self._json()
                rows = approval.analyse(cy, py, cfg)
                approval.apply_decisions(cfg, rows, b.get("decisions", {}), b.get("user") or "user", cfg["fy"])
                for k, v in (b.get("setup") or {}).items(): cfg["setup"][k] = v
                save_cfg(slug, cfg)
            rows = approval.analyse(cy, py, cfg)
            return self._send(200, {"rows": rows, "buckets": approval.BUCKETS, "heads": approval.head_options(),
                                    "lt": {k: cfg["setup"].get(k, 0) for k in (
                                        "Long-term portion of loans from related parties (Rs) - current year",
                                        "Long-term portion of loans from related parties (Rs) - previous year")}})

        if act == "masters" and method == "POST":
            b = self._json()
            agm = masters._d(b.get("agm") or cfg["setup"].get("Date of AGM (this year)") or "")
            r = masters.read(cfg["setup"].get("CIN", ""), fy_dates(cfg["fy"])[1],
                             os.path.join(d, "auditor_master.xlsx") if have["auditor"] else None,
                             os.path.join(d, "roc_master.xlsx") if have["roc"] else None, agm)
            return self._send(200, r)

        if act == "setup" and method == "POST":
            b = self._json()
            for k, v in b.get("values", {}).items():
                cfg["setup"][k] = v
            for k, v in b.get("notes", {}).items():
                cfg.setdefault("setup_notes", {})[k] = v
            save_cfg(slug, cfg)
            return self._send(200, {"ok": True})

        if act == "build":
            if method == "POST":
                if BUILDS.get(slug, {}).get("state") == "running": return self._send(200, {"state": "running"})
                if not have["tb_cy"]: raise ValueError("Fetch the current-year trial balance first")
                rows = approval.analyse(tb_rows(d, "tb_cy"), tb_rows(d, "tb_py"), cfg)
                pend = [r["ledger"] for r in rows if not r["approved"]]
                if pend and not self._json().get("force"):
                    return self._send(200, {"state": "blocked", "pending": pend})
                threading.Thread(target=run_build, args=(slug,), daemon=True).start()
                return self._send(200, {"state": "running"})
            if slug not in BUILDS and os.path.exists(os.path.join(d, "last_build.json")):
                return self._send(200, json.load(open(os.path.join(d, "last_build.json"), encoding="utf-8")))
            return self._send(200, BUILDS.get(slug, {"state": "idle"}))

        if act == "download":
            fn = out_name(cfg)
            data = open(os.path.join(d, fn), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{fn}"')
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            return
        if act == "openfolder":
            if os.name == "nt": os.startfile(d)
            return self._send(200, {"folder": d})
        return self._send(404, {"error": "unknown action"})


def main():
    lan = "--lan" in sys.argv
    port = int(SETTINGS.get("port", 8765))
    srv = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), H)
    url = f"http://localhost:{port}"
    print(f"Schedule III app running at {url}" + ("  (LAN: http://<this-PC-IP>:%d)" % port if lan else ""))
    print("Keep this window open. Close it to stop the app.")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
