"""Offline quality gate for a deep-research Markdown report.

Checks the things a model cannot be trusted to self-assess:
  * citation coverage  - share of claim-bearing units (paragraphs, bullets,
                         table rows containing numbers/dates/money) that carry
                         a resolvable citation in the same unit
  * unlinkable cites   - "[Source: Some Title]" with no URL behind it
  * required sections  - bottom line, confidence, limitations, sources
  * research date      - an explicit as-of date (YYYY-MM-DD)
  * overclaiming       - "guaranteed", "proven", "certain", ...
  * leftovers          - TODO / TBD / [citation needed] / placeholder URLs

Usage:
  python dr_engine/tools/check_report.py report.md [--min-coverage 0.8] [--json]

Exit code 0 = pass, 1 = fail (any hard check), 2 = usage error.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traps import (  # noqa: E402
    check_known_traps_in_text,
    check_source_tier_inflation,
    check_uncalibrated_probabilities,
    load_known_traps,
)

URL_RE = re.compile(r"https?://[^\s<>\)\]\"'`|]+")
LOCAL_REF_RE = re.compile(r"\]\(file:///[^)\s]+\)")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
FOOTNOTE_REF_RE = re.compile(r"\[\^[\w-]+\]")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([\w-]+)\]:\s*(.*)$")
NUMERIC_REF_RE = re.compile(r"\[(?:S|E|R|C)?\d{1,3}(?:\s*[,–-]\s*(?:S|E|R|C)?\d{1,3})*\]")
NUMREF_DEF_RE = re.compile(r"^\s*(?:[-*]\s*)?\[((?:S|E|R|C)?\d{1,3})\]\s*[:.\-–]?\s*(.*)$")
NUMREF_TABLE_DEF_RE = re.compile(r"^\|\s*\[?((?:S|E|R|C)?\d{1,3})\]?\s*\|(.*)$")
SOURCE_TAG_RE = re.compile(r"\[(?:Source|Sources|Източник|Източници)\s*:\s*([^\]]*)\]", re.I)

# A unit is "claim-bearing" if it states a number, percentage, money amount,
# multiplier or a year. Pure section numbering ("1.", "2.3") is stripped first.
CLAIM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?\s?(?:%|‰|x\b|×|bps|bp\b|pp\b))"
    r"|([$€£¥]\s?\d)|(\d\s?(?:USD|EUR|BGN|лв|евро|долара))"
    r"|\b(?:19|20)\d{2}\b"
    r"|\b\d+(?:[.,]\d+)+\b"
    r"|\b\d{2,}\b",
    re.I,
)
META_RE = re.compile(r"^\*{0,2}[\w /()-]{2,40}:\*{0,2}\s")
# A unit that only says where the preceding block came from ("*Source:* [..]").
SOURCE_LINE_RE = re.compile(
    r"^[\s>*_-]*(?:\*|_)*(Sources?|Източни(?:к|ци)|Evidence|Ref(?:erence)?s?)"
    r"(?:\*|_)*\s*:", re.I)
LEADING_ENUM_RE = re.compile(r"^\s*(?:[-*+]|\d+(?:\.\d+)*[.)]?)\s+")

OVERCLAIM_RE = re.compile(
    r"\b(guarantee[sd]?|guaranteed|certified|proven|provably|definitive(?:ly)?|"
    r"undeniabl[ey]|indisputabl[ey]|irrefutabl[ey]|risk[- ]free|zero[- ]risk|"
    r"certain ruin|guaranteed ruin|death sentence|always works|never fails|"
    r"гарантиран\w*|доказан\w*|безрисков\w*|сигурна печалба|без риск)\b",
    re.I,
)
LEFTOVER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|\[citation needed\]|\?\?\?", re.I)
PLACEHOLDER_HOST_RE = re.compile(r"(^|\.)(example\.(com|org|net)|localhost|your[-_]?domain)$", re.I)
ISO_DATE_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")

SECTION_PATTERNS = {
    "bottom_line": r"(bottom line|executive summary|key findings|tl;?dr|"
                   r"резюме|изводи|основни изводи|кратък отговор|отговор)",
    "confidence": r"(confidence|certainty|увереност|степен на сигурност)",
    "limitations": r"(limitation|caveat|uncertaint|open question|what would change|"
                   r"ограничения|неизвестни|отворени въпроси|какво би промени)",
    "sources": r"(sources|bibliography|references|works cited|evidence log|"
               r"източници|литература|библиография)",
}


@dataclass
class Unit:
  line: int
  text: str
  kind: str  # paragraph | bullet | table_row


@dataclass
class Result:
  path: str
  units: int = 0
  claim_units: int = 0
  cited_claim_units: int = 0
  uncited: list[dict] = field(default_factory=list)
  unique_urls: int = 0
  unique_domains: int = 0
  unlinkable_citations: list[dict] = field(default_factory=list)
  placeholder_urls: list[dict] = field(default_factory=list)
  overclaims: list[dict] = field(default_factory=list)
  leftovers: list[dict] = field(default_factory=list)
  missing_sections: list[str] = field(default_factory=list)
  has_iso_date: bool = False
  uncalibrated_probabilities: list[dict] = field(default_factory=list)
  source_tier_inflations: list[dict] = field(default_factory=list)
  known_trap_violations: list[dict] = field(default_factory=list)
  failures: list[str] = field(default_factory=list)
  warnings: list[str] = field(default_factory=list)

  @property
  def coverage(self) -> float:
    return self.cited_claim_units / self.claim_units if self.claim_units else 1.0


def _strip_non_prose(lines: list[str]) -> list[tuple[int, str]]:
  """Drops fenced code / mermaid / $$ math blocks and HTML comments."""
  out: list[tuple[int, str]] = []
  in_fence = in_math = in_comment = False
  for i, line in enumerate(lines, 1):
    s = line.strip()
    if s.startswith("```") or s.startswith("~~~"):
      in_fence = not in_fence
      continue
    if s == "$$" or (s.startswith("$$") and not s.endswith("$$")) or (
        in_math and s.endswith("$$")):
      in_math = not in_math
      continue
    if "<!--" in s and "-->" not in s:
      in_comment = True
      continue
    if in_comment:
      if "-->" in s:
        in_comment = False
      continue
    if in_fence or in_math:
      continue
    out.append((i, line))
  return out


def _units(lines: list[tuple[int, str]]) -> list[Unit]:
  units: list[Unit] = []
  para: list[str] = []
  para_line = 0
  table_row_idx = 0

  def flush() -> None:
    nonlocal para
    if para:
      units.append(Unit(para_line, " ".join(para), "paragraph"))
      para = []

  for n, raw in lines:
    s = raw.strip()
    if s.startswith("#"):
      flush()
      table_row_idx = 0
      units.append(Unit(n, s, "heading"))
      continue
    if not s or re.fullmatch(r"[-*_]{3,}", s):
      flush()
      table_row_idx = 0
      continue
    if s.startswith("|"):
      flush()
      if re.fullmatch(r"\|?[\s:|-]+\|?", s) and "-" in s:
        # GFM delimiter row: pop the preceding header row, keep all subsequent data rows.
        if table_row_idx == 1 and units and units[-1].kind == "table_row":
          units.pop()
        table_row_idx += 1
        continue
      units.append(Unit(n, s, "table_row"))
      table_row_idx += 1
      continue
    table_row_idx = 0
    if re.match(r"^([-*+]|\d+[.)])\s+", s):
      flush()
      units.append(Unit(n, s, "bullet"))
      continue
    if s.startswith(">"):
      s = s.lstrip("> ").strip()
      if not s or s.startswith("[!"):
        continue
    if not para:
      para_line = n
    para.append(s)
  flush()

  cleaned: list[Unit] = []
  seen_h2 = False
  for u in units:
    if u.kind == "heading":
      seen_h2 = seen_h2 or u.text.startswith("##")
      cleaned.append(u)
      continue
    if not seen_h2 and META_RE.match(LEADING_ENUM_RE.sub("", u.text)):
      continue  # title-block metadata (Date:, Author:, Status: ...)
    cleaned.append(u)
  return cleaned


def _defined_refs(lines: list[str]) -> tuple[dict[str, str], dict[str, str]]:
  """Returns footnote and numeric-reference definitions (id -> text)."""
  foot, num = {}, {}
  for line in lines:
    m = FOOTNOTE_DEF_RE.match(line.strip())
    if m:
      foot[m.group(1)] = m.group(2)
      continue
    m = NUMREF_DEF_RE.match(line) or NUMREF_TABLE_DEF_RE.match(line.strip())
    # A reference may resolve to a local document (e.g. an audited earlier report),
    # but only http(s) URLs count toward the public-source minimums in check().
    if m and (URL_RE.search(m.group(2) or "") or LOCAL_REF_RE.search(m.group(2) or "")):
      num[m.group(1)] = m.group(2)
  return foot, num


def _is_cited(text: str, foot: dict[str, str], num: dict[str, str]) -> bool:
  if URL_RE.search(text):
    return True
  for ref in FOOTNOTE_REF_RE.findall(text):
    if URL_RE.search(foot.get(ref[2:-1], "")):
      return True
  for ref in NUMERIC_REF_RE.findall(text):
    ids = re.findall(r"(?:S|E|R|C)?\d{1,3}", ref)
    if any(i in num for i in ids):
      return True
  return False


EXEMPT_HEADING_RE = re.compile(
    r"^(?:sources|references|bibliography|verification|източници|литература|проверка)"
    r"(?:\s*\([^)]*\))?\s*$", re.I)


def heading_exempt(heading: str, current: bool) -> bool:
  """True inside the Sources / Verification sections (tool output and source lists, not
  audited as prose). A level-1/2 heading counts only when it IS that section
  ('## Проверка (Verification)'), not when it merely contains the word
  ('## Проверка на убиващите хипотези' is the kill section and must be audited).
  Deeper headings inherit from their parent."""
  level = len(heading) - len(heading.lstrip("#"))
  if level >= 3:
    return current
  return bool(EXEMPT_HEADING_RE.match(heading.lstrip("#").strip()))


def _is_claim(text: str) -> bool:
  body = LEADING_ENUM_RE.sub("", text)
  body = re.sub(r"https?://\S+", "", body)
  body = FOOTNOTE_REF_RE.sub("", body)
  body = NUMERIC_REF_RE.sub("", body)
  return bool(CLAIM_RE.search(body))


def check(path: Path, min_coverage: float = 0.8, min_urls: int = 5,
          min_domains: int = 3) -> Result:
  text = path.read_text(encoding="utf-8", errors="replace")
  lines = text.splitlines()
  res = Result(str(path))
  prose = _strip_non_prose(lines)
  foot, num = _defined_refs(lines)

  units = _units(prose)
  # Reference / footnote definition lines are the bibliography, not claims.
  units = [u for u in units
           if not FOOTNOTE_DEF_RE.match(u.text)
           and not (NUMREF_DEF_RE.match(u.text) and URL_RE.search(u.text))]
  # A "Source:" line cites what sits directly above it: the previous paragraph,
  # or the contiguous run of bullets / table rows right before it.
  block_cited: dict[int, bool] = {}
  for idx, u in enumerate(units):
    if u.kind == "heading" or not SOURCE_LINE_RE.match(u.text) or not _is_cited(
        u.text, foot, num):
      continue
    j = idx - 1
    while j >= 0 and units[j].kind != "heading" and not SOURCE_LINE_RE.match(units[j].text):
      block_cited[j] = True
      if units[j].kind == "paragraph":
        break
      prev = units[j - 1] if j > 0 else None
      if not prev or prev.kind != units[j].kind or prev.line < units[j].line - 2:
        break
      j -= 1

  res.units = sum(1 for u in units if u.kind != "heading")
  for idx, u in enumerate(units):
    if u.kind == "heading" or not _is_claim(u.text):
      continue
    res.claim_units += 1
    if _is_cited(u.text, foot, num) or block_cited.get(idx):
      res.cited_claim_units += 1
    else:
      res.uncited.append({"line": u.line, "kind": u.kind, "text": u.text[:160]})

  urls = {m.rstrip(".,;:") for m in URL_RE.findall(text)}
  hosts = set()
  for u in urls:
    host = (urlparse(u).hostname or "").lower()
    if PLACEHOLDER_HOST_RE.search(host):
      res.placeholder_urls.append({"url": u})
    elif host:
      hosts.add(host[4:] if host.startswith("www.") else host)
  res.unique_urls = len(urls) - len(res.placeholder_urls)
  res.unique_domains = len(hosts)

  for n, line in prose:
    for m in SOURCE_TAG_RE.finditer(line):
      if not URL_RE.search(m.group(1)):
        res.unlinkable_citations.append({"line": n, "text": m.group(0)[:120]})
    for m in OVERCLAIM_RE.finditer(line):
      prefix = line[:m.start()].lower()
      if re.search(r"\b(not|never|no|hardly|scarcely|не е|не са|не беше|не може да се|не се|без да е)\s+$", prefix):
        continue
      res.overclaims.append({"line": n, "word": m.group(0)})
    if LEFTOVER_RE.search(line):
      res.leftovers.append({"line": n, "text": line.strip()[:120]})
    # Check for source tier inflation in references/tables
    tier_m = re.search(r"\b(?:Tier[- ]?([1-5])|T([1-5]))\b", line, re.I)
    url_m = URL_RE.search(line)
    if tier_m and url_m:
      tier_val = f"T{tier_m.group(1) or tier_m.group(2)}"
      url_val = url_m.group(0)
      inf_err = check_source_tier_inflation(url_val, tier_val)
      if inf_err:
        res.source_tier_inflations.append({"line": n, "error": inf_err, "text": line[:120]})

  # Check for uncalibrated subjective probabilities
  for u in units:
    if u.kind == "heading":
      continue
    uncal_err = check_uncalibrated_probabilities(u.text)
    if uncal_err:
      res.uncalibrated_probabilities.append({"line": u.line, "error": uncal_err, "text": u.text[:120]})

  # Check for known killed edges and traps
  traps = load_known_traps()
  for u in units:
    v_list = check_known_traps_in_text(u.text, traps)
    for v in v_list:
      res.known_trap_violations.append({"line": u.line, "trap": v, "text": u.text[:120]})

  headings = "\n".join(l for l in lines if l.lstrip().startswith("#")).lower()
  for name, pat in SECTION_PATTERNS.items():
    if not re.search(pat, headings, re.I):
      res.missing_sections.append(name)
  res.has_iso_date = bool(ISO_DATE_RE.search("\n".join(lines[:40])))

  # Hard failures
  if res.coverage < min_coverage:
    res.failures.append(
        f"citation coverage {res.coverage:.0%} < {min_coverage:.0%} "
        f"({res.cited_claim_units}/{res.claim_units} claim units cited)")
  if res.unique_urls < min_urls:
    res.failures.append(f"only {res.unique_urls} unique source URLs (< {min_urls})")
  if res.unique_domains < min_domains:
    res.failures.append(
        f"only {res.unique_domains} independent domains (< {min_domains})")
  if res.unlinkable_citations:
    res.failures.append(
        f"{len(res.unlinkable_citations)} citation(s) without a URL")
  if res.placeholder_urls:
    res.failures.append(f"{len(res.placeholder_urls)} placeholder URL(s)")
  if res.leftovers:
    res.failures.append(f"{len(res.leftovers)} TODO/TBD/[citation needed] marker(s)")
  if res.uncalibrated_probabilities:
    for item in res.uncalibrated_probabilities:
      res.failures.append(f"L{item['line']}: {item['error']}")
  if res.source_tier_inflations:
    for item in res.source_tier_inflations:
      res.failures.append(f"L{item['line']}: {item['error']}")
  if res.known_trap_violations:
    for item in res.known_trap_violations:
      res.failures.append(
          f"L{item['line']}: asserts known killed edge / trap '{item['trap']['name']}' without acknowledging lab refutation"
      )
  if "sources" in res.missing_sections or "bottom_line" in res.missing_sections:
    res.failures.append("missing required section(s): " + ", ".join(
        s for s in ("bottom_line", "sources") if s in res.missing_sections))
  # Soft warnings
  for s in ("confidence", "limitations"):
    if s in res.missing_sections:
      res.warnings.append(f"no '{s}' section")
  if not res.has_iso_date:
    res.warnings.append("no as-of date (YYYY-MM-DD) in the first 40 lines")
  if res.overclaims:
    res.warnings.append(
        f"{len(res.overclaims)} overclaiming word(s): " + ", ".join(
            sorted({o['word'].lower() for o in res.overclaims})))
  return res


def _print(res: Result, max_items: int) -> None:
  status = "PASS" if not res.failures else "FAIL"
  print(f"[{status}] {res.path}")
  print(f"  citation coverage : {res.coverage:.0%}  "
        f"({res.cited_claim_units}/{res.claim_units} claim units)")
  print(f"  sources           : {res.unique_urls} URLs, "
        f"{res.unique_domains} domains")
  for f in res.failures:
    print(f"  FAIL  {f}")
  for w in res.warnings:
    print(f"  WARN  {w}")
  if res.uncited:
    print(f"  Uncited claim units (first {min(max_items, len(res.uncited))} "
          f"of {len(res.uncited)}):")
    for u in res.uncited[:max_items]:
      print(f"    L{u['line']:<5} {u['text']}")
  for key, label in (("unlinkable_citations", "Citation without URL"),
                     ("leftovers", "Leftover marker")):
    for item in getattr(res, key)[:max_items]:
      print(f"    L{item['line']:<5} {label}: {item['text']}")
  if res.uncalibrated_probabilities:
    print(f"  Uncalibrated probabilities (first {min(max_items, len(res.uncalibrated_probabilities))}):")
    for item in res.uncalibrated_probabilities[:max_items]:
      print(f"    L{item['line']:<5} {item['error']}")
  if res.source_tier_inflations:
    print(f"  Source tier inflations:")
    for item in res.source_tier_inflations[:max_items]:
      print(f"    L{item['line']:<5} {item['error']}")
  if res.known_trap_violations:
    print(f"  Known killed edges / trap violations:")
    for item in res.known_trap_violations[:max_items]:
      print(f"    L{item['line']:<5} {item['trap']['name']}: {item['trap']['refutation']}")
  if res.overclaims:
    print("  Overclaims at lines: " + ", ".join(
        f"L{o['line']}" for o in res.overclaims[:max_items * 2]))


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("reports", nargs="+", type=Path)
  ap.add_argument("--min-coverage", type=float, default=0.8)
  ap.add_argument("--min-urls", type=int, default=5)
  ap.add_argument("--min-domains", type=int, default=3)
  ap.add_argument("--max-items", type=int, default=15,
                  help="max listed items per category")
  ap.add_argument("--json", action="store_true")
  args = ap.parse_args(argv)

  results = []
  for p in args.reports:
    if not p.is_file():
      print(f"not a file: {p}", file=sys.stderr)
      return 2
    results.append(check(p, args.min_coverage, args.min_urls, args.min_domains))
  if args.json:
    out = []
    for r in results:
      d = r.__dict__.copy()
      d["coverage"] = round(r.coverage, 3)
      out.append(d)
    print(json.dumps(out if len(out) > 1 else out[0], ensure_ascii=False, indent=2))
  else:
    for r in results:
      _print(r, args.max_items)
  return 1 if any(r.failures for r in results) else 0


if __name__ == "__main__":
  sys.exit(main())
