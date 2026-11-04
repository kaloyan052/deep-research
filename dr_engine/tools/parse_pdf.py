#!/usr/bin/env python3
"""
dr_engine/tools/parse_pdf.py — PDF -> citable snapshot (prose + structured tables)

Turns annual reports, regulatory annexes, gazettes and papers into a snapshot that
`evidence.py add` can quote line by line:
1. Prose per page (pdfplumber; pypdf fallback), with running headers/footers and page
   numbers stripped and ligatures/hyphenation normalised. Each page starts "=== Page N ===".
2. Every table pdfplumber detects is cut out of the prose and rendered after the page as a
   block of self-describing rows, so ONE quoted line carries its row label, column headers
   and the table's scale:

     [TABLE p3.t1]
     p3.t1 units: Figures in thousands of USD
     p3.t1 header: Item | 2025 | 2024
     p3.t1 r1: Revenue | 2025: 1,234 | 2024: 1,100
     [/TABLE]

   Quote a row exactly as it appears ("p3.t1 r1: Revenue | 2025: 1,234 | 2024: 1,100" or a
   part of it) - and check the `units` line: "1,234" in thousands is 1.234 million.
3. `evidence.py fetch <pdf-url>` uses the same function, so fetched and imported PDFs look
   the same. A PDF with no text layer (scanned image) is refused: OCR it first.

  python dr_engine/tools/parse_pdf.py report.pdf [-o out.txt]
  python dr_engine/tools/parse_pdf.py report.pdf --import-dir research/<dir> --url <original URL>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


LIGATURES = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "\xa0": " ",
}
MIN_TEXT_CHARS = 200  # less than this from a whole PDF means no text layer (scanned)
SCALE_RE = re.compile(
    r"in\s+(?:thousands|millions|billions)\b|(?:thousands|millions|billions)\s+of\b|"
    r"\b(?:USD|EUR|GBP|BGN|CHF|JPY)\s?(?:'000|000s|thousands?|millions?|mn|m|bn)\b|"
    r"[€$£]\s?(?:'000|mn|m|bn)\b|\bin\s+%|\(%\)|\bpercent(?:age)?\b|"
    r"в\s+хиляди|хил\.\s?лв|млн\.\s?лв|в\s+милиони", re.I)
PERIOD_RE = re.compile(r"^(?:FY\s?|Q[1-4]\s?|H[12]\s?)?(?:19|20)\d{2}(?:[/-]\d{2,4})?[A-Z]?$", re.I)
NUMERIC_RE = re.compile(r"^[\s(+\-−]*[$€£]?\s*\d[\d,.\s]*%?\)?$")


def clean_scientific_text(text: str) -> str:
    """Normalizes ligatures, hyphens, and whitespace while preserving numbers and quotes."""
    for k, v in LIGATURES.items():
        text = text.replace(k, v)

    # Fix broken hyphenated words at line endings: e.g. "insti-\ntutional" -> "institutional"
    text = re.sub(r"(\b[a-zA-Z]{3,})-\s*\n\s*([a-zA-Z]{3,}\b)", r"\1\2", text)

    # Normalize multiple blank lines to double newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_pages(pdf_path: Path) -> List[str]:
    if pypdf is None:
        raise ImportError("pypdf is required. Install it via: pip install pypdf")

    reader = pypdf.PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        raw_text = page.extract_text() or ""
        pages.append(raw_text)
    return pages


def strip_headers_and_footers(pages: List[str]) -> List[str]:
    """Detects and removes recurring header/footer lines across pages."""
    if len(pages) < 2:
        return pages

    # Extract first and last non-empty lines of each page
    first_lines: Dict[str, int] = {}
    last_lines: Dict[str, int] = {}

    for p in pages:
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        if lines:
            f = lines[0]
            l = lines[-1]
            first_lines[f] = first_lines.get(f, 0) + 1
            last_lines[l] = last_lines.get(l, 0) + 1

    # Candidate headers/footers appear on >= 40% of pages
    threshold = max(2, int(len(pages) * 0.4))
    headers_to_strip = {k for k, count in first_lines.items() if count >= threshold}
    footers_to_strip = {k for k, count in last_lines.items() if count >= threshold}

    # Also detect page numbers e.g. "Page 12 of 45" or just standalone numbers
    page_num_re = re.compile(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?$", re.I)

    cleaned_pages = []
    for p in pages:
        lines = [l.strip() for l in p.splitlines()]
        if lines and lines[0] in headers_to_strip:
            lines = lines[1:]
        if lines and (lines[-1] in footers_to_strip or page_num_re.match(lines[-1])):
            lines = lines[:-1]
        cleaned_pages.append("\n".join(lines))

    return cleaned_pages


# ------------------------------------------------------------------ tables
def _cell(c: Any) -> str:
    s = str(c) if c is not None else ""
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).replace("|", "/").strip()


def _is_header(row: List[str]) -> bool:
    """First row is a header when its cells are labels or period names (2025, FY2024, Q3 2025),
    not data figures like 1,234 or (35)."""
    cells = [c for c in row if c]
    if not cells:
        return False
    return all(PERIOD_RE.match(c) or not NUMERIC_RE.match(c) for c in cells)


def units_line(text: str) -> str:
    """The line that states the table's scale or unit ('in thousands of USD', '%'), if any."""
    for line in reversed((text or "").splitlines()):
        if SCALE_RE.search(line):
            return _cell(line)
    return ""


def render_table(rows: List[List[Any]], label: str, units: str = "") -> List[str]:
    """Rows -> self-describing lines: each data row repeats the column headers, so one
    quoted line is enough to know what every number in it means."""
    rows = [[_cell(c) for c in r] for r in rows if r and any(_cell(c) for c in r)]
    if not rows:
        return []
    lines = [f"[TABLE {label}]"]
    if units:
        lines.append(f"{label} units: {units}")
    header = rows[0] if len(rows) >= 2 and _is_header(rows[0]) else None
    body = rows[1:] if header else rows
    if header:
        lines.append(f"{label} header: " + " | ".join(header))
    if body and not any(r and r[0] for r in body):
        lines.append(f"{label} note: no row labels in the PDF text layer - the table does not say "
                     f"what each row measures; do not cite a row of this table for its meaning")
    for i, r in enumerate(body, 1):
        if header:
            cells = [r[0]] + [f"{h}: {v}" if h and v else v
                              for h, v in zip(header[1:], r[1:])] + r[len(header):]
        else:
            cells = r
        lines.append(f"{label} r{i}: " + " | ".join(cells))
    lines.append("[/TABLE]")
    return lines


def pdf_snapshot(source: bytes | str | Path, clean: bool = True) -> tuple[str, Dict[str, Any]]:
    """PDF bytes or path -> (snapshot text, info). Raises ValueError when the PDF has no
    text layer, so nobody cites an empty or OCR-less scan."""
    data = source if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
    pages: List[str] = []
    blocks_by_page: List[List[str]] = []
    if pdfplumber is not None:
        parser = "pdfplumber"
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for n, page in enumerate(pdf.pages, 1):
                try:
                    found = page.find_tables()
                except Exception:  # malformed page objects: keep the prose
                    found = []
                prose = page
                for t in found:
                    prose = prose.outside_bbox(t.bbox)
                pages.append(prose.extract_text() or "")
                blocks = []
                for i, t in enumerate(found, 1):
                    rows = t.extract()
                    top = t.bbox[1]
                    try:
                        above = page.within_bbox((0, max(0, top - 80), page.width, top)).extract_text()
                    except ValueError:
                        above = ""
                    units = units_line(above or "") or units_line(" ".join(_cell(c) for c in (rows[0] if rows else [])))
                    rendered = render_table(rows, f"p{n}.t{i}", units)
                    if rendered:
                        blocks.append("\n".join(rendered))
                blocks_by_page.append(blocks)
    elif pypdf is not None:
        parser = "pypdf"
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
        blocks_by_page = [[] for _ in pages]
    else:
        raise ImportError("no PDF library: python -m pip install pdfplumber")
    if clean:
        pages = strip_headers_and_footers(pages)
    parts = []
    for n, (text, blocks) in enumerate(zip(pages, blocks_by_page), 1):
        body = clean_scientific_text(text) if clean else text.strip()
        parts.append(f"=== Page {n} ===\n{body}" + ("\n\n" + "\n\n".join(blocks) if blocks else ""))
    snapshot = "\n\n".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    prose_chars = sum(len(p.strip()) for p in pages) + sum(len(b) for bl in blocks_by_page for b in bl)
    if prose_chars < MIN_TEXT_CHARS:
        raise ValueError(f"PDF has {prose_chars} characters of text across {len(pages)} page(s): "
                         f"it is a scanned image without a text layer. OCR it first (e.g. ocrmypdf), "
                         f"then import the OCR'd PDF; never cite it from memory or a snippet.")
    return snapshot, {"parser": parser, "pages": len(pages),
                      "tables": sum(len(b) for b in blocks_by_page)}


def parse_pdf(
    pdf_path: str | Path,
    output_path: Optional[str | Path] = None,
    clean: bool = True,
) -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")
    full_text, _ = pdf_snapshot(path, clean=clean)

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8", newline="\n") as f:
            f.write(full_text)
        print(f"[+] Saved parsed PDF text ({len(full_text)} chars) to: {out_p}")

    return full_text


def import_into_evidence(
    pdf_path: str | Path,
    research_dir: str | Path,
    url: str,
    title: str = "",
) -> Dict[str, Any]:
    """Parses a PDF into research_dir/sources/S###.txt + index.jsonl, exactly like
    `evidence.py fetch` would for the same document."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from evidence import _append, _canon, _jsonl, _next_id, sha256_text  # local: evidence imports us

    res_p = Path(research_dir)
    if not (res_p / "plan.md").exists():
        raise FileNotFoundError(f"{res_p} is not a study folder (no plan.md). "
                                f"Create one with: evidence.py init <slug>")
    sources_dir = res_p / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    index_file = sources_dir / "index.jsonl"
    index = _jsonl(index_file)
    for r in index:
        if _canon(r["url"]) == _canon(url):
            print(f"{r['id']}  already imported  {url} - cite it as --source {r['id']}")
            return r

    text, info = pdf_snapshot(pdf_path, clean=True)
    next_id = _next_id(index, "S")
    with open(sources_dir / f"{next_id}.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    rec = {
        "id": next_id,
        "url": url,
        "final_url": url,
        "http_status": None,
        "content_type": "application/pdf",
        "via": "parse_pdf",
        "parser": info["parser"],
        "tables": info["tables"],
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "chars": len(text),
        "sha256": sha256_text(text),
        "title": title or Path(pdf_path).stem,
    }
    _append(index_file, rec)
    print(f"{next_id}  imported  {url}  ({len(text)} chars, {info['pages']} pages, "
          f"{info['tables']} tables via {info['parser']})")
    print(f"    Cite with: evidence.py add --dir {research_dir} --source {next_id} --quote \"...\" "
          f"(table rows: quote the 'pN.tM rK:' line, and read its 'units' line)")
    return rec


def main(argv: List[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="PDF -> citable snapshot (prose + structured tables).")
    parser.add_argument("pdf", help="Path to input PDF file")
    parser.add_argument("-o", "--output", help="Path to write output text file")
    parser.add_argument("--no-clean", action="store_true", help="Disable header/footer stripping and normalization")
    parser.add_argument("--import-dir", help="Research dir to import directly as sources/S###.txt")
    parser.add_argument("--url", default="", help="Original URL of the document (required with --import-dir)")
    parser.add_argument("--title", default="", help="Document title for evidence metadata")
    args = parser.parse_args(argv)

    try:
        if args.import_dir:
            if not args.url:
                print("ERROR: --url is required with --import-dir: give the address you downloaded the "
                      "PDF from, so the source can be re-checked (gate --live).")
                return 2
            import_into_evidence(args.pdf, args.import_dir, args.url, args.title)
        else:
            text = parse_pdf(args.pdf, args.output, clean=not args.no_clean)
            if not args.output:
                print(text[:3000])
    except (FileNotFoundError, ValueError, ImportError) as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
