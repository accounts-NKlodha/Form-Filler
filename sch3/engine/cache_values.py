import sys, re, zipfile, shutil, time, math
from pycel import ExcelCompiler
from xml.sax.saxutils import escape
src, dst = sys.argv[1], sys.argv[2]
x = ExcelCompiler(filename=src)
z = zipfile.ZipFile(src)
wbxml = z.read('xl/workbook.xml').decode()
rels = z.read('xl/_rels/workbook.xml.rels').decode()
rid2t = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels)) or {}
for m in re.finditer(r'Target="([^"]+)"[^>]*Id="(rId\d+)"', rels): rid2t[m.group(2)] = m.group(1)
sheets = {name: 'xl/' + rid2t[rid].lstrip('/').replace('xl/','') for name, rid in re.findall(r'<sheet [^>]*?name="([^"]+)"[^>]*r:id="(rId\d+)"', wbxml)}
pat = re.compile(r'<c r="([A-Z]+\d+)"([^>]*)><f>(.*?)</f>(?:<v\s*/>|<v></v>)?</c>', re.S)  # openpyxl writes <v/> or <v></v> (lxml)
out = {}
t0 = time.time(); n = 0; bad = 0
for name, path in sheets.items():
    xml = z.read(path).decode()
    def sub(m):
        global n, bad
        ref, attrs, f = m.group(1), m.group(2), m.group(3)
        try:
            v = x.evaluate(f"'{name}'!{ref}")
        except Exception as e:
            v = None; bad += 1
            if bad <= 8: print("  eval error", name, ref, str(e)[:120], file=sys.stderr)
        n += 1
        if hasattr(v, 'item'): v = v.item()
        if v is None or v == '':
            return f'<c r="{ref}"{attrs} t="str"><f>{f}</f><v></v></c>'
        if isinstance(v, bool):
            return f'<c r="{ref}"{attrs} t="b"><f>{f}</f><v>{int(v)}</v></c>'
        if isinstance(v, (int, float)):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): bad += 1; return m.group(0)
            return f'<c r="{ref}"{attrs}><f>{f}</f><v>{repr(float(v)) if isinstance(v,float) else v}</v></c>'
        s = str(v)
        if s.startswith('#'):
            bad += 1
            if bad <= 8: print("  error value", name, ref, s, f[:120], file=sys.stderr)
            return f'<c r="{ref}"{attrs} t="e"><f>{f}</f><v>{escape(s)}</v></c>'
        return f'<c r="{ref}"{attrs} t="str"><f>{f}</f><v>{escape(s)}</v></c>'
    out[path] = pat.sub(sub, xml)
    print(name, n, round(time.time()-t0,1), flush=True)
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zo:
    for item in z.infolist():
        data = out[item.filename].encode() if item.filename in out else z.read(item.filename)
        zo.writestr(item, data)
print('formulas', n, 'bad', bad)
