"""Turn technical_report.md into a print-ready HTML page (figures embedded).

    pip install markdown
    python scripts/report_to_html.py
Then open out/technical_report.html in Chrome, press Ctrl+P, destination "Save as PDF",
Margins "Default", tick "Background graphics", and save.
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("Run first:  pip install markdown")

ROOT = Path(__file__).resolve().parents[1]
md = (ROOT / "technical_report.md").read_text(encoding="utf-8")
body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])


def embed(m):
    p = ROOT / m.group(1)
    if not p.exists():
        return ""                                   # missing figure: drop it rather than show a broken icon
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f'src="data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"'


body = re.sub(r'src="([^"]+\.(?:png|jpg|jpeg|svg))"', embed, body)
body = re.sub(r"<img[^>]*alt=\"[^\"]*\"\s*/?>", lambda m: m.group(0) if "src=" in m.group(0) else "", body)

css = """
@page { size: A4; margin: 15mm 16mm; }
body { font: 10pt/1.42 Georgia, 'Times New Roman', serif; color: #1a1a1a; max-width: 178mm; margin: 0 auto; }
h1 { font-size: 20pt; margin: 0 0 6pt; } h2 { font-size: 13pt; margin: 14pt 0 4pt; border-bottom: 1px solid #bbb; padding-bottom: 2pt; }
p, li { margin: 3pt 0; } ul, ol { padding-left: 16pt; margin: 3pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font: 8.8pt/1.3 Arial, sans-serif; page-break-inside: avoid; }
th, td { border: 1px solid #999; padding: 2.5pt 5pt; text-align: left; } th { background: #eee; }
code { font: 8.6pt Consolas, monospace; background: #f3f3f3; padding: 0 2pt; }
img { max-width: 100%; max-height: 62mm; display: block; margin: 6pt auto; }
a { color: #0b5cad; text-decoration: none; }
"""
out = ROOT / "out"
out.mkdir(exist_ok=True)
html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Concordance technical report</title><style>{css}</style></head><body>{body}</body></html>"
(out / "technical_report.html").write_text(html, encoding="utf-8")
print("Wrote", out / "technical_report.html")