# Hide Notes sub-head rows whose cached values are all zero, then add page breaks so a note is not split across pages.
# Usage: hide_zero_rows.py <cached.xlsx> <subrows.json> <out.xlsx>
import sys, re, json, zipfile
src, js, dst = sys.argv[1:4]
meta = json.load(open(js))
if isinstance(meta, list): meta = {"subrows": meta}
rows = meta["subrows"]
z = zipfile.ZipFile(src)
wbxml = z.read('xl/workbook.xml').decode(); rels = z.read('xl/_rels/workbook.xml.rels').decode()
rid = re.search(r'<sheet [^>]*?name="Notes"[^>]*r:id="(rId\d+)"', wbxml).group(1)
tgt = re.search(r'Id="%s"[^>]*Target="([^"]+)"' % rid, rels) or re.search(r'Target="([^"]+)"[^>]*Id="%s"' % rid, rels)
path = 'xl/' + tgt.group(1).lstrip('/').replace('xl/', '')
xml = z.read(path).decode()
def val(ref):
    m = re.search(r'<c r="%s"[^>]*>(?:<f>.*?</f>)?<v>([^<]*)</v>' % ref, xml, re.S)
    if not m or m.group(1) == '': return 0.0
    try: return float(m.group(1))
    except ValueError: return 1.0
hide = [n for n, cols in rows if all(abs(val(f"{c}{n}")) < 0.005 for c in cols)]
for n in hide:
    xml = re.sub(r'<row r="%d"((?![^>]*hidden)[^>]*)>' % n, r'<row r="%d"\1 hidden="1">' % n, xml, count=1)
# page breaks: keep each note on one page where it fits (A4 portrait, fit to width)
if meta.get("notes"):
    hidden = set(hide) | set(meta.get("hidden", []))
    hidden |= {int(m.group(1)) for m in re.finditer(r'<row r="(\d+)"[^>]*hidden="1"', xml)}
    H = {int(k): v for k, v in meta.get("heights", {}).items()}
    h = lambda n: 0 if n in hidden else H.get(n, 13.5)
    CAP = 800  # unscaled points per A4 portrait page (fit to width ~0.92)
    title = sum(h(n) for n in range(1, 6))
    used, breaks = title, []
    cap = CAP - title
    first = meta["notes"][0][0]
    used = sum(h(n) for n in range(6, first))
    for s, e in meta["notes"]:
        blk = sum(h(n) for n in range(s, e + 2))
        if blk == 0: continue
        if used + blk > cap and used > 0:
            if blk <= cap:
                breaks.append(s - 1); used = 0
            else:
                # long note: break inside it at row boundaries
                if used > cap * 0.6: breaks.append(s - 1); used = 0
                for n in range(s, e + 2):
                    if used + h(n) > cap: breaks.append(n - 1); used = 0
                    used += h(n)
                continue
        used += blk
    if breaks:
        brk = '<rowBreaks count="%d" manualBreakCount="%d">%s</rowBreaks>' % (len(breaks), len(breaks),
              "".join('<brk id="%d" max="16383" man="1"/>' % b for b in breaks))
        xml = re.sub(r'<rowBreaks.*?</rowBreaks>', '', xml, flags=re.S)
        # rowBreaks goes after pageSetup / headerFooter
        m = re.search(r'(<headerFooter.*?</headerFooter>|<headerFooter[^>]*/>)', xml, re.S) or re.search(r'(<pageSetup[^>]*/>)', xml)
        xml = xml[:m.end()] + brk + xml[m.end():]
    print('page breaks', breaks)
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zo:
    for item in z.infolist():
        zo.writestr(item, xml.encode() if item.filename == path else z.read(item.filename))
print('hidden', len(hide), 'of', len(rows))
