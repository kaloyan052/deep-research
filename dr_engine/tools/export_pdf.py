#!/usr/bin/env python3
"""Deep Research v15.0 Attested Executive PDF Exporter.

Deterministically compiles deep research Markdown reports into executive,
publication-grade A4 PDF documents with table support, typography hierarchy,
and automated layout formatting using local headless Chromium/Edge engines.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows cp1252 resilience
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


HTML_A4_TEMPLATE = """<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
    @page {{
        size: A4;
        margin: 20mm 15mm 20mm 15mm;
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        font-size: 10pt;
        line-height: 1.5;
        color: #1a1a1a;
        background-color: #ffffff;
        padding: 0;
        margin: 0;
    }}
    h1 {{
        font-size: 18pt;
        color: #0f172a;
        border-bottom: 2px solid #2563eb;
        padding-bottom: 8px;
        margin-top: 0;
    }}
    h2 {{
        font-size: 14pt;
        color: #1e3a8a;
        border-bottom: 1px solid #cbd5e1;
        padding-bottom: 4px;
        margin-top: 24px;
        page-break-after: avoid;
    }}
    h3 {{
        font-size: 11pt;
        color: #1e293b;
        margin-top: 16px;
        page-break-after: avoid;
    }}
    h4 {{
        font-size: 10pt;
        color: #334155;
        margin-top: 12px;
        page-break-after: avoid;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 12px 0;
        font-size: 8.5pt;
        page-break-inside: avoid;
    }}
    th, td {{
        border: 1px solid #cbd5e1;
        padding: 6px 8px;
        text-align: left;
        vertical-align: top;
    }}
    th {{
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: 600;
    }}
    tr:nth-child(even) {{
        background-color: #f8fafc;
    }}
    code {{
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 8.5pt;
        background-color: #f1f5f9;
        padding: 1px 4px;
        border-radius: 3px;
        color: #0969da;
    }}
    pre {{
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        padding: 10px;
        overflow-x: auto;
        font-size: 8pt;
        line-height: 1.4;
        page-break-inside: avoid;
    }}
    pre code {{
        background-color: transparent;
        padding: 0;
        color: #1e293b;
    }}
    blockquote {{
        border-left: 3px solid #2563eb;
        margin: 10px 0;
        padding: 4px 12px;
        color: #475569;
        background-color: #f8fafc;
        font-style: italic;
    }}
    ul, ol {{
        margin: 8px 0;
        padding-left: 20px;
    }}
    li {{
        margin-bottom: 4px;
    }}
    a {{
        color: #2563eb;
        text-decoration: none;
    }}
    hr {{
        border: 0;
        border-top: 1px solid #e2e8f0;
        margin: 20px 0;
    }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def find_browser_engine() -> str | None:
    """Find local headless browser binary (Edge, Chrome, Chromium)."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return str(Path(c).resolve())
    return None


def convert_md_to_pdf(md_path: Path | str, pdf_out_path: Path | str) -> tuple[bool, str]:
    """Compile Markdown to styled PDF via headless browser."""
    import markdown_it

    md_p = Path(md_path).resolve()
    pdf_p = Path(pdf_out_path).resolve()

    if not md_p.exists():
        return False, f"Source Markdown file not found: {md_p}"

    browser_bin = find_browser_engine()
    if not browser_bin:
        return False, "No headless browser engine (Edge/Chrome/Chromium) found on PATH or standard locations."

    content = md_p.read_text(encoding="utf-8")
    md = markdown_it.MarkdownIt("commonmark", {"html": True}).enable("table")
    body_html = md.render(content)

    title = md_p.stem.replace("_", " ").title()
    full_html = HTML_A4_TEMPLATE.format(title=title, body=body_html)

    tmp_html = pdf_p.with_suffix(".tmp.html")
    tmp_html.write_text(full_html, encoding="utf-8")

    cmd = [
        browser_bin,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_p}",
        str(tmp_html),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if pdf_p.exists() and pdf_p.stat().st_size > 1000:
            return True, f"Successfully exported PDF ({pdf_p.stat().st_size} bytes) -> {pdf_p}"
        return False, f"Browser PDF generation failed (code {res.returncode}): {res.stderr}"
    except Exception as e:
        return False, f"Exception while executing browser export: {e}"
    finally:
        if tmp_html.exists():
            tmp_html.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Markdown to Attested A4 PDF")
    parser.add_argument("input_md", help="Path to source Markdown file")
    parser.add_argument("--out", "-o", help="Target PDF output path")
    args = parser.parse_args()

    in_p = Path(args.input_md)
    out_p = Path(args.out) if args.out else in_p.with_suffix(".pdf")

    ok, msg = convert_md_to_pdf(in_p, out_p)
    if ok:
        print(f"[PDF EXPORT OK] {msg}")
        return 0
    else:
        print(f"[PDF EXPORT FAILED] {msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
