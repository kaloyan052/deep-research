"""Is this machine ready to run the research toolkit? Prints the exact fix for each problem.

Run it once after cloning (and again after updating Python or the requirements):

  python dr_engine/tools/doctor.py

Exit code: 0 = ready (optional extras may be missing), 1 = something required is missing.
It never installs anything and never touches the network.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIP = "python -m pip install -r requirements.txt"

# (name, import statement, what it is for, fix)
REQUIRED = [
    ("requests", "import requests", "HTTP fetches", PIP),
    ("beautifulsoup4", "from bs4 import BeautifulSoup", "HTML to text snapshots", PIP),
    ("pdfplumber", "import pdfplumber", "PDF snapshots with tables as quotable rows", PIP),
    ("pypdf", "import pypdf", "fallback PDF text", PIP),
    ("python-dotenv", "import dotenv", "optional keys for the science CLIs", PIP),
    ("trafilatura", "from trafilatura import extract_metadata",
     "page title / date / author in the source index", PIP + "  (lxml >= 5.2 also needs lxml_html_clean)"),
]
OPTIONAL = [
    ("langextract", "import langextract",
     "extract_doc.py online extraction and its interactive HTML view", "python -m pip install langextract"),
    ("primp", "import primp",
     "Tier-0 native TLS impersonation for polyglot HTTP transport", "python -m pip install primp"),
    ("ddgs", "import ddgs", "scanner.py web search", "python -m pip install ddgs"),
    ("polite-http", "import polite_http", "science CLIs (a stdlib fallback is bundled)",
     "python -m pip install polite-http"),
]


def _try(stmt: str) -> str:
  """'' when the import works, otherwise the error in one line."""
  try:
    exec(stmt, {})
    return ""
  except Exception as e:  # ImportError, or a broken dependency raising something else
    return f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}".strip()


def _fts5() -> str:
  try:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    con.close()
    return ""
  except sqlite3.Error as e:
    return f"sqlite {sqlite3.sqlite_version} without FTS5 ({e})"


def checks() -> list[tuple[str, str, str, str]]:
  """(status, name, detail, fix) rows; status is OK, FAIL (required) or MISSING (optional)."""
  rows = []
  py = sys.version.split()[0]
  rows.append(("OK" if sys.version_info >= (3, 10) else "FAIL", "python", f"{py} (needs >= 3.10)",
               "install Python 3.10 or newer, then recreate the venv"))
  for name, stmt, why, fix in REQUIRED:
    err = _try(stmt)
    rows.append(("FAIL" if err else "OK", name, err or why, fix))
  err = _fts5()
  rows.append(("FAIL" if err else "OK", "sqlite FTS5", err or "corpus.py passage index",
               "use a Python whose sqlite3 has FTS5 (python.org installers and most distros do)"))
  for name, stmt, why, fix in OPTIONAL:
    err = _try(stmt)
    rows.append(("MISSING" if err else "OK", name, why, fix))
  for rel in (".agents/skills/deep-research/SKILL.md", "dr_engine/tools/evidence.py", "research"):
    rows.append(("OK" if (ROOT / rel).exists() else "FAIL", rel, "workspace file",
                 "run from a full clone of the repository"))
  rows.append(("OK", "OPENALEX_MAILTO", "set (OpenAlex polite pool)" if os.environ.get("OPENALEX_MAILTO")
               else "not set (optional: your email in this variable gets faster OpenAlex answers)", ""))
  if os.environ.get("DR_ALLOW_JINA") == "1":
    rows.append(("WARN", "DR_ALLOW_JINA", "=1: pages that block a direct fetch are sent to r.jina.ai",
                 "unset it unless you want that third-party fallback"))
  return rows


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):  # Windows pipes default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  rows = checks()
  width = max(len(r[1]) for r in rows) + 2
  for status, name, detail, fix in rows:
    line = f"{status:<8}{name:<{width}}{detail}"
    if status in ("FAIL", "MISSING", "WARN") and fix:
      line += f"\n{'':<{8 + width}}fix: {fix}"
    print(line)
  failed = [r for r in rows if r[0] == "FAIL"]
  print(f"\nRESULT: {'NOT READY - ' + str(len(failed)) + ' required check(s) failed' if failed else 'READY'}")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main())
