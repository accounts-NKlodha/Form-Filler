"""Time-saved figures on the partner review screen, and the order of the signed set. Synthetic data only.
Run: python tests/test_partner.py"""
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ff_partner  # noqa: E402
import ff_signed  # noqa: E402

T0 = datetime(2026, 11, 25, 5, 0, tzinfo=timezone.utc)


def iso(sec):
    return (T0 + timedelta(seconds=sec)).isoformat().replace("+00:00", "Z")


def test_runs():
    logs = [{"startedAt": iso(0), "finishedAt": iso(20), "counts": {"filled": 40}},
            {"startedAt": iso(25), "finishedAt": iso(60), "counts": {"filled": 30}},
            {"startedAt": iso(66), "finishedAt": iso(92), "counts": {"filled": 12, "manual": 1}},
            {"finishedAt": iso(5000), "counts": {"filled": 3}},          # old log, no start: a run of its own, 0 s
            {"finishedAt": iso(5060), "counts": {"filled": 4}}]
    rs = ff_partner.runs(logs)
    assert len(rs) == 2
    assert (rs[0]["seconds"], rs[0]["rounds"], rs[0]["filled"], rs[0]["left"], rs[0]["timed"]) == (92, 3, 82, 1, True)
    assert (rs[1]["seconds"], rs[1]["timed"]) == (60, False)            # first Save to last Save: "at least"
    assert ff_partner.best(rs) is rs[1]
    assert ff_partner.best(ff_partner.runs(logs[:3]))["seconds"] == 92
    assert ff_partner.best(ff_partner.runs([{"finishedAt": iso(0), "counts": {"filled": 0}}])) is None


def test_dur():
    assert ff_partner.dur(92) == "1 min 32 s"
    assert ff_partner.dur(9 * 60 - 92) == "7 min 28 s"
    assert ff_partner.dur(45) == "45 s"
    assert ff_partner.dur(3 * 3600 + 120) == "3 h 2 min"


def test_signed_order():
    from pypdf import PdfReader, PdfWriter
    with tempfile.TemporaryDirectory() as t:
        folder = Path(t)
        sd = ff_signed.signed_dir(folder)
        slot = folder / "mca_attachments" / ff_signed.SLOT
        assert ff_signed.attachment(folder, slot)[0] is None
        for name, pages in (("notice.pdf", 1), ("Board report.pdf", 2), ("Balance sheet and notes.pdf", 3), ("Auditor report.pdf", 4)):
            w = PdfWriter()
            for _ in range(pages):
                w.add_blank_page(595, 842)
            with open(sd / name, "wb") as fh:
                w.write(fh)
        assert [p.name for p in ff_signed.signed_files(folder)] == ["Balance sheet and notes.pdf", "Auditor report.pdf", "Board report.pdf", "notice.pdf"]
        path, _ = ff_signed.attachment(folder, slot)
        assert path.name == ff_signed.MERGED and len(PdfReader(str(path)).pages) == 10
        (sd / "Last year AOC-4.pdf").write_bytes((sd / "notice.pdf").read_bytes())   # a filed form by its name: never attached
        assert len(ff_signed.signed_files(folder)) == 4 and len(ff_signed.rejected(folder)) == 1


if __name__ == "__main__":
    for f in (test_runs, test_dur, test_signed_order):
        f()
        print("ok", f.__name__)
