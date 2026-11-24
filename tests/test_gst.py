"""GST annual returns: portal readers, month-wise checks, the client-folder work area. Synthetic data only.

    python tests/test_gst.py
"""
import io
import json
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gst import checks, gstr9, portal, work  # noqa: E402

G = "33ABCDE1234F1Z5"
FY = "2025-26"


def t(i=0, c=0, s=0, cs=0):
    return dict(iamt=i, camt=c, samt=s, csamt=cs)


def g3b(p, taxable=1000, c=90, s=90, itc=(50, 50), rcm=0):
    return json.dumps({"status": 1, "data": {"gstin": G, "ret_period": p, "sup_details": {
        "osup_det": dict(t(0, c, s), txval=taxable), "osup_zero": dict(t(), txval=0), "isup_rev": dict(t(0, rcm, rcm), txval=rcm * 10)},
        "itc_elg": {"itc_avl": [dict(t(0, *itc), ty="OTH"), dict(t(0, rcm, rcm), ty="ISRC")], "itc_net": t(0, *itc)}}}).encode()


def g1s(p, taxable=1000, c=90, s=90, hsn_c=None):
    sec = lambda n, cg: dict(sec_nm=n, ttl_rec=1, ttl_val=taxable + 2 * cg, ttl_tax=taxable, ttl_igst=0, ttl_cgst=cg, ttl_sgst=s, ttl_cess=0)
    return json.dumps({"data": {"gstin": G, "ret_period": p, "sec_sum": [sec("TTL_LIAB", c), sec("B2B", c), sec("B2B_4A", c), sec("HSN", c if hsn_c is None else hsn_c),
                                                                         dict(sec_nm="NIL", ttl_rec=0, ttl_expt_amt=10, ttl_nilsup_amt=0, ttl_ngsup_amt=5)]}}).encode()


def g2b(p, c=50, s=50, cn=0, docs=()):
    return json.dumps({"data": {"gstin": G, "rtnprd": p, "itcsumm": {"itcavl": {
        "nonrevsup": dict(igst=0, cgst=c, sgst=s, cess=0), "othersup": dict(igst=0, cgst=cn, sgst=cn, cess=0)}},
        "docdata": {"b2b": [{"ctin": "33AAAAA0000A1Z5", "inv": list(docs)}]}}}).encode()


def g2a(p, c=50, s=50):
    doc = {"gstin": G, "fp": p, "b2b": [{"ctin": "33AAAAA0000A1Z5", "cfs": "Y", "inv": [{"inum": "1", "itms": [{"itm_det": dict(t(0, c, s), txval=1000)}]}]}]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("returns_R2A.json", json.dumps(doc))
    return buf.getvalue()


def year(**over):
    """A year where everything ties; over = {kind: {period: bytes}} to replace months."""
    files = []
    for p in portal.months(FY):
        files += [over.get("gstr3b", {}).get(p) or g3b(p), over.get("gstr1_summary", {}).get(p) or g1s(p),
                  over.get("gstr2b", {}).get(p) or g2b(p), g2a(p)]
    files += [over.get("gstr2b", {}).get(p) or g2b(p) for p in portal.next_months(FY)]
    return files


def data_of(files):
    data = {}
    for raw in files:
        d = portal.read(raw)
        data.setdefault(d["kind"], {})[d["period"]] = d["figures"]
    return data


class Readers(unittest.TestCase):
    def test_kinds_are_recognised_by_content(self):
        self.assertEqual([portal.read(f("042025"))["kind"] for f in (g3b, g1s, g2b, g2a)], ["gstr3b", "gstr1_summary", "gstr2b", "gstr2a"])
        d = portal.read(g3b("032026", taxable=2500.5))
        self.assertEqual((d["gstin"], d["period"], d["figures"]["outward"]["taxable"]), (G, "032026", Decimal("2500.5")))

    def test_rubbish_is_refused(self):
        for raw in (b"hello", b"[]", b'{"data": {}}', b"PK\x03\x04broken", json.dumps({"data": {"gstin": G, "sec_sum": []}}).encode()):
            with self.assertRaises(portal.Unrecognised):
                portal.read(raw)

    def test_months(self):
        self.assertEqual(portal.months(FY)[0], "042025")
        self.assertEqual(portal.months(FY)[-1], "032026")
        self.assertEqual(portal.next_months(FY), ["042026", "052026", "062026", "072026", "082026", "092026", "102026"])
        self.assertEqual(portal.fy_of("15-03-2026"), "2025-26")
        self.assertEqual(portal.fy_of("01-04-2026"), "2026-27")


class Checks(unittest.TestCase):
    def by(self, files):
        return {c["id"]: c for c in checks.run(FY, data_of(files))}

    def test_a_year_that_ties(self):
        r = self.by(year())
        self.assertEqual({c["state"] for c in r.values()}, {"ok"})
        self.assertEqual(r["outward_taxable"]["total_a"], Decimal(12000))

    def test_tax_paid_a_month_late_is_a_timing_point(self):
        r = self.by(year(gstr3b={"042025": g3b("042025", c=40), "052025": g3b("052025", c=140)}))["outward_tax"]
        self.assertEqual((r["state"], r["gaps"], r["timing"], r["diff"]), ("point", 2, True, Decimal(0)))

    def test_credit_notes_reduce_itc_available_in_2b(self):
        # 2B shows invoices 80+80 and credit notes 30+30: ITC available is 100, which is what 3B took
        r = self.by(year(gstr2b={"062025": g2b("062025", c=80, s=80, cn=30)}))["itc_2b"]
        self.assertEqual((r["state"], r["diff"]), ("ok", Decimal(0)))

    def test_itc_above_2b_is_a_point(self):
        r = self.by(year(gstr3b={"062025": g3b("062025", itc=(75, 75))}))["itc_2b"]
        self.assertEqual((r["state"], r["diff"]), ("point", Decimal(50)))

    def test_a_missing_month_is_needs_input_never_zero(self):
        files = [f for f in year() if not (portal.read(f)["kind"] == "gstr3b" and portal.read(f)["period"] == "012026")]
        r = self.by(files)["outward_taxable"]
        self.assertEqual(r["state"], "needs")
        self.assertIn("Jan 2026", r["missing"])
        self.assertEqual(len(r["rows"]), 11)

    def test_hsn_must_add_up(self):
        r = self.by(year(gstr1_summary={"082025": g1s("082025", hsn_c=95)}))["hsn_tax"]
        self.assertEqual((r["state"], r["diff"]), ("point", Decimal(5)))

    def test_last_years_invoice_in_next_years_2b(self):
        doc = dict(dt="20-03-2026", cgst=7, sgst=7, igst=0, cess=0, txval=100, itcavl="Y", rev="N")
        new = dict(doc, dt="02-04-2026")
        r = self.by(year(gstr2b={"042026": g2b("042026", docs=[doc, new])}))["next_year_2b"]
        self.assertEqual((r["state"], r["total_a"], r["rows"][0]["documents"]), ("point", Decimal(14), 1))

    def test_tolerance_is_one_rupee(self):
        r = self.by(year(gstr3b={"042025": g3b("042025", taxable=1000.9)}))["outward_taxable"]
        self.assertEqual(r["state"], "ok")


class Draft(unittest.TestCase):
    def line(self, d, table):
        return next(l for l in d["lines"] if l["table"] == table)

    def test_no_draft_until_all_twelve_months_are_in(self):
        files = [f for f in year() if not (portal.read(f)["kind"] == "gstr3b" and portal.read(f)["period"] == "012026")]
        d = gstr9.build(FY, data_of(files))
        self.assertEqual((d["ready"], d["missing"], d["lines"]), (False, [("GSTR-3B", ["Jan 2026"])], []))

    def test_tables_4_to_9(self):
        over = {p: g3b(p, rcm=5) for p in portal.months(FY)}
        d = gstr9.build(FY, data_of(year(gstr3b=over)))
        self.assertEqual(self.line(d, "4B")["amounts"]["taxable"], Decimal(12000))
        self.assertEqual(self.line(d, "4G")["amounts"], dict(taxable=Decimal(600), igst=0, cgst=Decimal(60), sgst=Decimal(60), cess=0))
        self.assertEqual(self.line(d, "4N")["amounts"]["taxable"], Decimal(12600))
        self.assertEqual((self.line(d, "5D")["amounts"]["taxable"], self.line(d, "5F")["amounts"]["taxable"]), (Decimal(120), Decimal(60)))
        self.assertEqual(d["totals"]["turnover"], Decimal(12180))          # 4N + 5M - 4G
        self.assertEqual(self.line(d, "6A")["amounts"]["cgst"], Decimal(660))
        self.assertEqual(self.line(d, "6C")["amounts"]["cgst"], Decimal(60))   # 2B shows no registered RCM, so all of it is unregistered
        self.assertEqual(self.line(d, "8D")["amounts"]["cgst"], Decimal(0))
        self.assertEqual((d["totals"]["tax_gap"], d["totals"]["gstr9c"]), (Decimal(0), False))
        self.assertEqual(self.line(d, "6H")["state"], "needs")
        self.assertIsNone(self.line(d, "6H")["amounts"])                   # needs input is never a zero

    def test_tax_short_paid_shows_as_a_gap(self):
        d = gstr9.build(FY, data_of(year(gstr3b={"062025": g3b("062025", c=80)})))
        self.assertEqual(d["totals"]["tax_gap"], Decimal(10))

    def test_credit_notes_and_downward_amendments(self):
        def with_notes(p):
            j = json.loads(g1s(p))
            mk = lambda n, v: dict(sec_nm=n, ttl_rec=1, ttl_val=0, ttl_tax=v, ttl_igst=0, ttl_cgst=v / 10, ttl_sgst=v / 10, ttl_cess=0)
            j["data"]["sec_sum"] += [mk("CDNR", -100), mk("B2CSA", -50)]
            return json.dumps(j).encode()
        d = gstr9.build(FY, data_of(year(gstr1_summary={"072025": with_notes("072025")})))
        self.assertEqual((self.line(d, "4I")["amounts"]["taxable"], self.line(d, "4I")["state"]), (Decimal(100), "check"))
        self.assertEqual(self.line(d, "4L")["amounts"]["taxable"], Decimal(50))
        self.assertEqual(self.line(d, "4N")["amounts"]["taxable"], Decimal(12000 - 150))


class WorkArea(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = Path(self.tmp.name) / "clients" / "Sample Traders"
        self.client.mkdir(parents=True)
        self.log = []
        work._trail = lambda folder, text, by, **data: self.log.append((text, by))
        work.add_registration(self.client, G.lower(), "Asha")

    def tearDown(self):
        work._trail = None
        self.tmp.cleanup()

    def test_gstin_is_checked(self):
        for bad in ("", "33ABCDE1234F1Z", "hello world 123"):
            with self.assertRaises(ValueError):
                work.add_registration(self.client, bad)
        self.assertEqual(work.registrations(self.client.parent), [(self.client, G)])

    def test_ingest_files_by_content_and_guards_gstin_and_year(self):
        r = work.ingest(self.client, G, FY, g3b("042025"), "Asha")
        self.assertEqual((r["kind"], r["state"], r["file"]), ("gstr3b", "saved", "GST_%s_2025-26_GSTR3B_042025.json" % G))
        self.assertEqual(work.ingest(self.client, G, FY, g2b("052026"), "Asha")["file"], "GST_%s_2026-27_GSTR2B_052026.json" % G)
        self.assertTrue((work.area(self.client, G, FY) / "portal" / "gstr2b_next_year").is_dir())
        self.assertTrue(work.ingest(self.client, G, FY, g2a("042025"), "Asha")["file"].endswith(".zip"))
        with self.assertRaises(ValueError):
            work.ingest(self.client, G, FY, g3b("042024"), "Asha")            # another year
        with self.assertRaises(ValueError):
            work.ingest(self.client, "33ZZZZZ9999Z1Z5", FY, g3b("042025"), "Asha")   # another GSTIN
        with self.assertRaises(ValueError):
            work.ingest(self.client, G, FY, b"not a portal file", "Asha")

    def test_same_file_twice_and_a_changed_file(self):
        work.ingest(self.client, G, FY, g3b("042025"), "Asha")
        self.assertEqual(work.ingest(self.client, G, FY, g3b("042025"), "Asha")["state"], "same")
        self.assertEqual(work.ingest(self.client, G, FY, g3b("042025", taxable=5), "Asha")["state"], "replaced")
        portal_dir = work.area(self.client, G, FY) / "portal"
        self.assertEqual(len(list((portal_dir / "_replaced").iterdir())), 1)       # the old file is kept
        self.assertEqual(len(list((portal_dir / "gstr3b").iterdir())), 1)
        man = json.loads((portal_dir / "_manifest.json").read_text())
        self.assertEqual((len(man), man[0]["by"], len(man[0]["sha256"])), (1, "Asha", 64))
        data, problems = work.load(self.client, G, FY)
        self.assertEqual((data["gstr3b"]["042025"]["outward"]["taxable"], problems), (Decimal(5), []))

    def test_files_copied_in_by_hand_are_read_and_wrong_ones_listed(self):
        d = work.area(self.client, G, FY) / "portal" / "from client"
        d.mkdir(parents=True)
        (d / "april.json").write_bytes(g3b("042025"))
        (d / "old.json").write_bytes(g3b("042023"))
        (d / "notes.json").write_text("{}")
        data, problems = work.load(self.client, G, FY)
        self.assertEqual(sorted(data["gstr3b"]), ["042025"])
        self.assertEqual(len(problems), 2)

    def test_clearing_a_point_needs_a_person_and_a_reason_and_reopens_on_new_figures(self):
        for raw in year(gstr3b={"062025": g3b("062025", itc=(75, 75))}):
            work.ingest(self.client, G, FY, raw, "Asha")
        self.assertEqual((work.status(self.client, G, FY)["open"], work.status(self.client, G, FY)["needs"]), (1, 0))
        for user, note, treat in (("", "Supplier filed late, credit is in March 2B", work.TREATMENTS[0]), ("Ravi", "ok", work.TREATMENTS[0]),
                                  ("Ravi", "Supplier filed late, credit is in March 2B", "anything")):
            with self.assertRaises(ValueError):
                work.clear_point(self.client, G, FY, "itc_2b", user, note, treat)
        with self.assertRaises(ValueError):
            work.clear_point(self.client, G, FY, "outward_tax", "Ravi", "This one ties so there is nothing to clear", work.TREATMENTS[0])
        work.clear_point(self.client, G, FY, "itc_2b", "Ravi", "Supplier filed late, credit is in March 2B", work.TREATMENTS[0])
        st = work.status(self.client, G, FY)
        self.assertEqual((st["open"], st["points"]), (0, 1))
        self.assertIn("cleared", self.log[-1][0])
        work.ingest(self.client, G, FY, g3b("062025", itc=(80, 80)), "Asha")      # the figure changes
        self.assertEqual(work.status(self.client, G, FY)["open"], 1)              # so the point is open again

    def test_default_year(self):
        import datetime as dt
        self.assertEqual(work.default_fy(dt.date(2026, 11, 23)), "2025-26")
        self.assertEqual(work.default_fy(dt.date(2027, 2, 1)), "2025-26")
        self.assertEqual(work.default_fy(dt.date(2027, 4, 1)), "2026-27")
        self.assertTrue(work.valid_fy("2025-26") and not work.valid_fy("2025-27") and not work.valid_fy("../x"))


if __name__ == "__main__":
    unittest.main()
