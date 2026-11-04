"""One-command audit of a research folder. Run it before drafting and before delivering.

  python dr_engine/tools/gate.py research/<dir> --stage evidence   # before writing
  python dr_engine/tools/gate.py research/<dir>                    # full: evidence + report
  python dr_engine/tools/gate.py research/<dir> --live 5 --scorecard

Evidence stage
  E1  every snapshot in sources/ matches its fetch-time sha256 (no hand edits)
  E2  every evidence record points at a fetched snapshot and its quote is verbatim in it
  E3  plan.md has >= 3 kill hypotheses (K1..), each with >= 3 logged searches
  E4  kill-hypothesis searches are >= 30% of all logged searches; >= 12 searches total
  E5  every sub-question (SQ1..) has evidence; every kill hypothesis has evidence or
      is explicitly 'unresolved'
  E6  source tier integrity: no source tier inflation (community/blog platforms and
      unofficial GitHub repos must be T5; tertiary encyclopedias/explainers must be T4)
  E7  evidence depth & anti-duplication: no stance-flipping on identical quotes, no
      duplicate padding, and >= 50% of evidence (when >= 4 items) must be T1-T3
  E8  deterministic calculations: every [C###] in calculations.jsonl re-evaluates to
      its stored result, matches its SHA-256, and cites valid [E###] records
Report stage
  R1  check_report.py passes (coverage, sources, sections, no unlinked citations)
  R2  every claim-bearing sentence/row cites an existing [E###] (or verified [C###]
      linked to existing [E###])
  R3  every number in a cited unit appears in the quotes of cited [E###] or verified
      [C###] records; 'Inference:' / 'Извод:' cannot introduce unbound numbers;
      inline 'Calculation:' requires an explicit mathematical operator/equation
  R4  every 'contradicts' evidence record is cited somewhere in the report body
  R5  a Kill hypotheses / Red team section exists and plan.md verdicts are final
  R6  no self-assigned quality scores ("9/10", "rubric score")
  R7  no uncalibrated subjective probabilities: arbitrary probability intervals or
      Bayesian priors must have explicit sample size (n=...) or Calculation: label
  R8  no lab contradictions: claims asserting known killed edges (from registry) as
      viable without citing lab refutation (P31 / FXFIX01 / t = -5.2) are prohibited
  R9  anti-bypass ceiling: unverified inline 'Calculation:' units cannot exceed 40%
      of claim units (use calc.py [C###] for quantitative derivations)
  R10 mechanical confidence cap: declared overall report confidence cannot exceed
      the deterministic ceiling computed by formula.py
  R11 contradiction mapping: every conflict found by claims.py (same subject+attribute,
      different values) appears in the Conflicts section citing evidence from both
      sides; conflicts with no explaining axis must be marked unresolved
  R12 sampled audit (audit.py): all sampled claims judged by a fresh verifier, audit
      not stale, and the upper bound (hypergeometric / Clopper-Pearson) on the unsupported-claim rate
      <= --max-error (always checked when audit/sample.json exists; --require-audit
      makes it mandatory)
  R13 nothing hidden in exempt sections: the Sources / Verification sections are exempt only
      when the heading IS that section (not '## Проверка на убиващите хипотези'); in them a
      verdict ('confirmed', 'потвърдено', ...) without [E###]/[C###] fails, other uncited
      claims warn
  E9 discovery completeness: a screening audit (screening.py) with unjudged items, or with a
      lead judged relevant that was never fetched, fails; a loss bound > 20%, a coverage /
      saturation verdict other than SATURATED (corpus.py stats --save) or, on protocol
      >= 4.1, a missing measurement warns
  E4 (protocol >= 4.1) only kill searches that recorded what they returned count toward the
      30% budget and the >= 3 per kill hypothesis; archived studies (dated before
      E4_STRICT_FROM, no study.json) get a warning instead
Exit code 0 = pass, 1 = fail.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as audit_mod  # noqa: E402
import calc  # noqa: E402
import check_report as cr  # noqa: E402
import claims as claims_mod  # noqa: E402
import formula  # noqa: E402
import screening as screening_mod  # noqa: E402
from evidence import _jsonl, fetch_page, load_claims, load_evidence, sha256_text, TIERS, KINDS, STANCES  # noqa: E402
from verify_citations import match_score, normalise  # noqa: E402
from traps import (  # noqa: E402
    FORMAL_CALC_RE,
    SAMPLE_SIZE_RE,
    check_known_traps_in_text,
    check_source_tier_inflation,
    check_uncalibrated_probabilities,
    load_known_traps,
)

EID_RE = re.compile(r"\bE\d{3}\b")
CID_RE = re.compile(r"\bC\d{3}\b")
INFERENCE_LABEL_RE = re.compile(r"\b(Inference|Извод)\s*:", re.I)
INLINE_INF_TAG_RE = re.compile(r"\[(?:I|EST|Инференция|Оценка)(?:\s*[:\-–]\s*[^\]]*)?\]", re.I)
ASSUMPTION_LABEL_RE = re.compile(r"(?:^|\|)\s*(?:[-*]\s*)?\*{0,2}(?:Assumption|Hypothetical|Допускане|Проект)\s*:", re.I)
ESTIMATE_LABEL_RE = re.compile(r"\b(Estimate|Оценка)\b", re.I)
CALC_OPERATOR_RE = re.compile(
    r"(=|≈|≤|≥|<=|>=|[×÷]|\d\s*[+\-*/x]\s*[$€£¥]?\d)",
    re.I,
)
KILL_SECTION_RE = re.compile(r"(kill|red[- ]team|disconfirm|falsif|опроверга|убиващ)", re.I)
CONFLICT_SECTION_RE = re.compile(r"(conflict|contradict|противореч|конфликт)", re.I)
UNRESOLVED_RE = re.compile(r"(unresolved|unexplained|неразрешен|необяснен)", re.I)
VERDICT_RE = re.compile(r"(confirm|verified|refuted|disproved|потвърд|опроверг|проверено|присъда|verdict)",
                        re.I)
SOURCE_REF_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?\[(?:S|E)?\d{1,3}\]")
# Statements about the pipeline itself ("18 records verified against snapshots", "verified
# against gates E1-E8") are process claims, not findings about the subject.
PROCESS_RE = re.compile(r"\b(gates?|[ER]\d{1,2}|records?|snapshots?|sha-?256|checksums?|AST|"
                        r"calculations?|searches|epistemic|scorecard|audit)\b", re.I)
SELF_SCORE_RE = re.compile(r"\b\d{1,2}(?:\.\d)?\s*/\s*10\b|self[- ]score|оценка\s*\d+\s*/\s*10", re.I)

# Platforms for consumer/user reviews and marketplaces whose feedback represents empirical Voice-of-Customer
REVIEW_DOMAINS = (
    "g2.com", "capterra.com", "trustpilot.com", "apps.shopify.com",
    "marketplace.atlassian.com", "chromewebstore.google.com", "chrome.google.com",
    "wordpress.org", "reddit.com", "news.ycombinator.com", "getapp.com",
    "softwareadvice.com", "play.google.com", "apps.apple.com", "etsy.com",
    "gumroad.com", "upwork.com", "fiverr.com",
)

# Structural and prompt template tokens that must NOT trigger R3 number binding
STRUCTURAL_PATTERNS = (
    re.compile(r"^\s*\|\s*#?\d{1,3}\s*(?=\|)"),  # Leading table row index in Markdown: | 1 | ... | 35 |
    re.compile(r"\b(?:SQ|K|E|C|S|R|P|T)\d{1,3}[a-z]?\b", re.I),  # Structural identifiers SQ1, K5, T1, R14
    re.compile(r"\b\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\s*(?:★|⭐|stars?|звезди|точки|pts?)\b", re.I),  # 1-5★, 1-3★
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:★|⭐)\b"),  # 4.2★
    re.compile(r"\b\d+(?:\.\d+)?\s*/\s*(?:5|10|100)\b"),  # 4.8/5, 85/100
    re.compile(r"(?:≤|<=|≥|>=|<|>|~)?\s*\b(?:2\s*[-–]\s*3|3)\s+(?:weeks?|седмици)\b", re.I),  # ≤ 3 weeks
    re.compile(r"\b14[-–\s]+(?:day|дни|дневен)\b", re.I),  # 14-day demand test
    re.compile(r"\b(?:month|месец)\s+12\b|\b12[-–\s]+(?:month|месеца|месечен)\b", re.I),  # month 12
    re.compile(r"\b(?:first|първите)\s+100\s+(?:customers?|buyers?|клиенти|потребители)\b", re.I),  # first 100 customers
    re.compile(r"\b(?:top|топ)\s+\d{1,2}\b", re.I),  # Top 5 deep dives
    re.compile(r"\b(?:section|секция|глава|част)\s+\d+(?:\.\d+)*\b", re.I),  # Section 3, Секция 7.4
    re.compile(r"\b24\s*/\s*7\b"),  # 24/7
    re.compile(r"\b1\s*[-–]\s*10\s+(?:people|employees|души|служители|заети)\b", re.I),  # 1-10 people
)


def is_review_pain_evidence(rec: dict, index_rec: dict | None = None) -> bool:
  """True if the evidence record is a customer complaint/review from a software marketplace or forum."""
  if rec.get("kind") == "review_pain":
    return True
  if rec.get("kind") == "de_facto":
    url = (rec.get("url") or (index_rec or {}).get("url") or "").lower()
    if any(dom in url for dom in REVIEW_DOMAINS):
      return True
  return False


def strip_structural_tokens(text: str) -> str:
  """Removes table index columns, prompt template horizons, and rating scale labels before R3 number extraction."""
  cleaned = text
  for pat in STRUCTURAL_PATTERNS:
    cleaned = pat.sub(" ", cleaned)
  return cleaned
UNIT_SUFFIXES = {
    "%", "‰", "bps", "bp", "bips", "pt", "pts", "point", "points", "точка", "точки",
    "pip", "pips", "пип", "пипа", "пипсове",
    "percent", "pct", "процент", "процента", "проценти",
    "min", "mins", "minute", "minutes", "мин", "мин.", "минута", "минути",
    "sec", "secs", "second", "seconds", "сек", "сек.", "секунда", "секунди",
    "hours", "hour", "hrs", "hr", "ч", "ч.", "час", "часа", "часове",
    "days", "day", "d", "дни", "ден", "дена",
    "weeks", "week", "w", "седмица", "седмици",
    "months", "month", "месец", "месеца", "месеци",
    "years", "year", "yr", "yrs", "г", "г.", "год", "год.", "година", "години",
    "usd", "eur", "gbp", "bgn", "chf", "jpy",
    "dollar", "dollars", "долар", "долара", "долари",
    "euro", "euros", "евро",
    "lev", "leva", "лв", "лв.", "лев", "лева",
    "$", "€", "£", "¥",
}

NUM_RE = re.compile(
    r"(?<![\w.])([$€£¥])?\s*"
    r"(\d[\d,]*(?:\.\d+)?)"
    r"(?:[\s-]*"
    r"([$€£¥]|%|‰|bps\b|bp\b|bips\b|pts?\b|points?\b|точки?\b|"
    r"pips?\b|пип(?:а|ове)?\b|"
    r"percent\b|pct\b|процент[иа]?\b|"
    r"mins?\b|minutes?\b|мин(?:ут[иа])?\.?|"
    r"sec(?:ond)?s?\b|сек(?:унд[иа])?\.?|"
    r"hours?\b|hrs?\b|час(?:а|ове)?\b|"
    r"days?\b|дни\b|ден(?:а)?\b|"
    r"weeks?\b|седмиц[иа]\b|"
    r"months?\b|месец(?:а|и)?\b|"
    r"years?\b|yrs?\b|г(?:од)?\.?\b|годин[иа]\b|"
    r"usd\b|eur\b|gbp\b|bgn\b|chf\b|jpy\b|"
    r"dollars?\b|долар[аи]?\b|"
    r"euros?\b|евро\b|"
    r"lev(?:a)?\b|лв\.?|лев[а]?\b|"
    r"k\b|m\b|mn\b|bn\b|million\b|billion\b|хил\.|млн\.?|млрд\.?|милиард[аи]?\b)"
    r")?",
    re.I,
)
WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "нула": 0, "един": 1, "една": 1, "едно": 1, "два": 2, "две": 2,
    "три": 3, "четири": 4, "пет": 5, "шест": 6, "седем": 7, "осем": 8,
    "девет": 9, "десет": 10,
}

WORD_NUM_RE = re.compile(
    r"\b(" + "|".join(WORD_NUMS.keys()) + r")\s*"
    r"([$€£¥]|%|‰|bps\b|bp\b|bips\b|pts?\b|points?\b|точки?\b|"
    r"pips?\b|пип(?:а|ове)?\b|"
    r"percent\b|pct\b|процент[иа]?\b|"
    r"mins?\b|minutes?\b|мин(?:ут[иа])?\.?|"
    r"sec(?:ond)?s?\b|сек(?:унд[иа])?\.?|"
    r"hours?\b|hrs?\b|час(?:а|ове)?\b|"
    r"days?\b|дни\b|ден(?:а)?\b|"
    r"weeks?\b|седмиц[иа]\b|"
    r"months?\b|месец(?:а|и)?\b|"
    r"years?\b|yrs?\b|г(?:од)?\.?\b|годин[иа]\b|"
    r"usd\b|eur\b|gbp\b|bgn\b|chf\b|jpy\b|"
    r"dollars?\b|долар[аи]?\b|"
    r"euros?\b|евро\b|"
    r"lev(?:a)?\b|лв\.?|лев[а]?\b)",
    re.I,
)
VERDICTS = ("confirmed", "refuted", "unresolved")


class Num(float):
  has_unit: bool = False

  def __new__(cls, val: float, has_unit: bool = False):
    obj = super().__new__(cls, val)
    obj.has_unit = has_unit
    return obj


def numbers(text: str, strip_structural: bool = False) -> set:
  """Numeric values in text; '400,000', '$400K' and '400000' all map to 400000.0."""
  if strip_structural:
    text = strip_structural_tokens(text)
  text = EID_RE.sub(" ", text)
  text = CID_RE.sub(" ", text)
  text = re.sub(r"https?://\S+", " ", text)
  out_dates = set()
  for m in re.finditer(r"\b((?:19|20)\d{2}-\d{2}-\d{2})\b", text):
    out_dates.add(m.group(1))
  text = re.sub(r"\b((?:19|20)\d{2})-\d{2}-\d{2}\b", r"\1", text)  # ISO date: also bind the year
  text = re.sub(r"\[\^?[\w-]+\]", " ", text)
  out_dict: dict[float, Num] = {}
  for m in WORD_NUM_RE.finditer(text):
    w = m.group(1).lower()
    val = float(WORD_NUMS[w])
    out_dict[val] = Num(val, has_unit=True)
  for m in NUM_RE.finditer(text):
    prefix = m.group(1) or ""
    raw = m.group(2).rstrip(",.")
    suffix = (m.group(3) or "").lower()
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", raw):
      raw = raw.replace(",", "")
    else:
      raw = raw.replace(",", ".")
    try:
      v = float(raw)
    except ValueError:
      continue
    mult = {"k": 1e3, "хил.": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "млн": 1e6,
            "млн.": 1e6, "bn": 1e9, "billion": 1e9, "млрд": 1e9, "млрд.": 1e9,
            "милиард": 1e9, "милиарда": 1e9}.get(suffix, 1)
    val = round(v * mult, 6)
    has_unit = bool(prefix) or (suffix in UNIT_SUFFIXES)
    if val in out_dict:
      if has_unit and not out_dict[val].has_unit:
        out_dict[val] = Num(val, has_unit=True)
    else:
      out_dict[val] = Num(val, has_unit=has_unit)
  return set(out_dict.values()) | out_dates


def material(nums: set) -> set:
  """Numbers that must be bound: drop bare single digits (list counts, '2-Step')."""
  out = set()
  for n in nums:
    if isinstance(n, str):
      out.add(n)
    elif getattr(n, "has_unit", False):
      out.add(n)
    elif not (n.is_integer() and 0 <= n < 10):
      out.add(n)
  return out


E4_STRICT_FROM = "2026-11-04"  # studies dated from here on (or with study.json protocol >= 4.1)
STUDY_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def has_results(s: dict) -> bool:
  """A search counts as verified when it recorded what it returned: opened pages or result
  locators, or a tool-logged search (corpus.py / discover.py) with an explicit, possibly empty,
  result count."""
  if s.get("opened") or s.get("results"):
    return True
  return bool(s.get("tool") or s.get("channel")) and ("results" in s or "hits" in s)


def study_is_strict(d: Path) -> bool:
  marker = d / "study.json"
  if marker.exists():
    try:
      proto = json.loads(marker.read_text(encoding="utf-8")).get("protocol", "0")
      if tuple(int(x) for x in str(proto).split(".")[:2]) >= (4, 1):
        return True
    except (ValueError, json.JSONDecodeError):
      pass
  m = STUDY_DATE_RE.match(d.name)
  return bool(m and m.group(1) >= E4_STRICT_FROM)


PLACEHOLDER_ROW_RE = re.compile(r"^\|\s*(?:SQ|K)\d+\s*\|\s*(?:…|\.\.\.|<[^|]*>)\s*\|")


FORMULA_LINE_RE = re.compile(r"^\s*-\s*\*\*(Epistemic Index \(EI\)|Mechanical Confidence Ceiling|Source Tier "
                             r"Distribution|Verified Calculations \(`\[C###\]`\)|Limiting Factors):\*\*")


def placeholder_rows(plan: str) -> list[str]:
  """Rows still holding the template text ('| SQ1 | … |', '| K1 | <a T&C clause ...> |')."""
  return [m.group(0).split("|")[1].strip() for line in plan.splitlines()
          if (m := PLACEHOLDER_ROW_RE.match(line.strip()))]


def parse_plan(plan: str) -> tuple[list[str], dict[str, dict]]:
  sqs, kills = [], {}
  for line in plan.splitlines():
    s = line.strip()
    m = re.match(r"^\|\s*(SQ\d+)\s*\|", s)
    if m:
      sqs.append(m.group(1))
    m = re.match(r"^\|\s*(K\d+)\s*\|", s)
    if m:
      low = s.lower()
      verdict = next((v for v in VERDICTS if re.search(rf"\b{v}\b", low)), "pending")
      kills[m.group(1)] = {"verdict": verdict, "evidence": EID_RE.findall(s), "row": s}
  return sqs, kills


class Gate:
  def __init__(self, d: Path):
    self.d = d
    self.fail: list[str] = []
    self.warn: list[str] = []
    self.calculations: dict[str, dict] = {}
    self.scorecard: dict | None = None
    self.audit: dict | None = None

  def F(self, code: str, msg: str) -> None:
    self.fail.append(f"{code}  {msg}")

  def W(self, code: str, msg: str) -> None:
    self.warn.append(f"{code}  {msg}")

  # ------------------------------------------------------------ evidence
  def evidence_stage(
      self,
      min_searches: int,
      kill_share: float,
      min_primary_share: float = 0.50,
      strict_kill_results: bool | None = None,
  ) -> None:
    d = self.d
    index = {r["id"]: r for r in _jsonl(d / "sources" / "index.jsonl")}
    self.index = index
    self.evidence = {r["id"]: r for r in load_evidence(d)}
    self.calculations = calc.load_calculations(d)
    searches = _jsonl(d / "searches.jsonl")
    snaps: dict[str, str] = {}
    for sid, r in index.items():
      p = d / "sources" / f"{sid}.txt"
      if not p.exists():
        self.F("E1", f"snapshot {p.name} missing")
        continue
      snaps[sid] = p.read_text(encoding="utf-8")
      if r.get("via") == "manual":
        self.W("E1", f"{sid} is a manual capture ({r['url']}) - claims resting only on it: Medium confidence max")
      if sha256_text(snaps[sid]) != r["sha256"]:
        self.F("E1", f"snapshot {p.name} edited after fetch (sha256 mismatch) - re-fetch with --refresh")
    if not self.evidence:
      self.F("E2", "evidence.jsonl is empty - log evidence with evidence.py add")

    seen_source_quotes: dict[tuple[str, str], list[dict]] = {}
    for eid, r in self.evidence.items():
      sid = r.get("source")
      if sid not in snaps:
        self.F("E2", f"{eid}: source {sid!r} was never fetched - snippet or memory, not evidence")
        continue
      if r.get("snapshot_sha256") != index[sid]["sha256"]:
        self.F("E2", f"{eid}: snapshot changed since the quote was logged")
      if match_score(r.get("quote", ""), snaps[sid]) < 1.0:
        self.F("E2", f"{eid}: quote is not verbatim in {sid}.txt")
      for field, allowed in (("tier", TIERS), ("kind", KINDS), ("stance", STANCES)):
        if r.get(field) not in allowed:
          self.F("E2", f"{eid}: {field}={r.get(field)!r} not in {allowed}")
      # E6: Check against Source Tier Inflation (community -> T5, tertiary encyclopedias -> T4)
      src_url = r.get("url") or index[sid].get("url", "")
      src_pub = r.get("publisher", "") or index[sid].get("publisher", "")
      inf_err = check_source_tier_inflation(src_url, r.get("tier", ""), publisher=src_pub)
      if inf_err:
        self.F("E6", f"{eid}: {inf_err}")

      # E7a: Anti-stance-flipping and duplicate padding check
      q_key = (sid, normalise(r.get("quote", "")))
      for prev in seen_source_quotes.get(q_key, []):
        stances = {prev.get("stance"), r.get("stance")}
        if "supports" in stances and "contradicts" in stances:
          self.F("E7", f"{eid}: identical quote on {sid} logged with opposite stance to {prev['id']} "
                       f"({prev.get('stance')} vs {r.get('stance')})")
        elif prev.get("sq") == r.get("sq") and prev.get("stance") == r.get("stance"):
          self.F("E7", f"{eid}: exact duplicate evidence record of {prev['id']} ({sid}, {r.get('sq')})")
      seen_source_quotes.setdefault(q_key, []).append(r)

    # E7b: Primary / Peer-Reviewed Depth Floor (excluding review_pain / VoC marketplace reviews from denominator)
    core_ev = [
        r for r in self.evidence.values()
        if not is_review_pain_evidence(r, index.get(r.get("source", "")))
    ]
    if len(core_ev) >= 4 and min_primary_share > 0:
      t123 = sum(1 for r in core_ev if r.get("tier") in ("T1", "T2", "T3"))
      t123_share = t123 / len(core_ev)
      if t123_share < min_primary_share:
        self.F("E7", f"insufficient primary/peer-reviewed depth in core evidence: {t123}/{len(core_ev)} "
                     f"({t123_share:.0%}) non-review items are T1-T3; need >= {min_primary_share:.0%} "
                     f"(replace T4 encyclopedias/T5 blogs with primary or official sources)")

    # E8: Deterministic Calculations Integrity (calculations.jsonl)
    for calc_err in calc.verify_calculations(d, known_evidence_ids=set(self.evidence.keys())):
      self.F("E8", calc_err)

    plan_path = d / "plan.md"
    if not plan_path.exists():
      self.F("E3", "plan.md missing")
      self.sqs, self.kills = [], {}
      return
    self.sqs, self.kills = parse_plan(plan_path.read_text(encoding="utf-8"))
    if len(self.kills) < 3:
      self.F("E3", f"plan.md has {len(self.kills)} kill hypotheses (rows '| K1 | ...'); need >= 3")
    holders = placeholder_rows(plan_path.read_text(encoding="utf-8"))
    if holders:
      self.F("E3", f"plan.md still has template placeholder rows: {', '.join(holders)} - replace them "
                   f"with real sub-questions / kill hypotheses or delete them")
    per_purpose: dict[str, int] = {}
    for s in searches:
      per_purpose[s.get("purpose", "")] = per_purpose.get(s.get("purpose", ""), 0) + 1
    for k in self.kills:
      if per_purpose.get(k, 0) < 3:
        self.F("E3", f"{k}: {per_purpose.get(k, 0)} logged searches; need >= 3 (evidence.py log-search --purpose {k})")
    n_kill = sum(v for p, v in per_purpose.items() if p.startswith("K"))
    if len(searches) < min_searches:
      self.F("E4", f"{len(searches)} searches logged; need >= {min_searches}")
    elif n_kill / len(searches) < kill_share:
      self.F("E4", f"kill-hypothesis searches are {n_kill}/{len(searches)} = "
                   f"{n_kill / len(searches):.0%} of the budget; need >= {kill_share:.0%}")
    # A self-reported query with no recorded result set cannot be told apart from padding.
    # Studies on protocol >= 4.1 (study.json, or dated after the rule) count only kill searches
    # that recorded what they returned; archived studies keep the warning.
    verified = [s for s in searches if str(s.get("purpose", "")).startswith("K") and has_results(s)]
    strict = study_is_strict(d) if strict_kill_results is None else strict_kill_results
    if strict and searches:
      if len(verified) / len(searches) < kill_share:
        self.F("E4", f"kill searches with a recorded result set are {len(verified)}/{len(searches)} = "
                     f"{len(verified) / len(searches):.0%} of the budget; need >= {kill_share:.0%} - "
                     f"a search logged without what it returned does not count (corpus.py query --log, "
                     f"discover.py --dir, evidence.py log-search --opened <top results>)")
      per_k: dict[str, int] = {}
      for s in verified:
        per_k[s["purpose"]] = per_k.get(s["purpose"], 0) + 1
      for k in self.kills:
        if per_k.get(k, 0) < 3:
          self.F("E4", f"{k}: {per_k.get(k, 0)} kill searches with a recorded result set; need >= 3")
    elif n_kill and len(verified) / n_kill < 0.5:
      self.W("E4", f"only {len(verified)}/{n_kill} kill searches recorded what they found - "
                   f"the kill budget is unverifiable; log searches with corpus.py --log, "
                   f"discover.py --dir, or evidence.py log-search --opened")
    self._discovery_check(d, strict)
    by_sq: dict[str, list[str]] = {}
    for eid, r in self.evidence.items():
      by_sq.setdefault(r.get("sq", ""), []).append(eid)
    for sq in self.sqs:
      if sq not in by_sq:
        self.F("E5", f"{sq} has no evidence (answer it, or mark it unresolved in the report's Limitations)")
    for k, info in self.kills.items():
      if k not in by_sq and info["verdict"] in ("confirmed", "refuted"):
        self.F("E5", f"{k} is '{info['verdict']}' but has no evidence records with --sq {k}")
    if not any(r.get("stance") == "contradicts" for r in self.evidence.values()):
      self.W("E5", "no 'contradicts' evidence at all - was the red-team pass real?")

  # -------------------------------------------------------------- report
  def report_stage(
      self,
      report: Path,
      min_coverage: float,
      min_urls: int = 5,
      max_inline_calc_share: float = 0.40,
      require_audit: bool = False,
      max_error: float = 0.15,
  ) -> None:
    if not report.exists():
      self.F("R1", f"{report} missing")
      return
    res = cr.check(report, min_coverage=min_coverage, min_urls=min_urls)
    for f in res.failures:
      self.F("R1", f)
    for w in res.warnings:
      self.W("R1", w)
    text = report.read_text(encoding="utf-8")
    lines = text.splitlines()
    units = cr._units(cr._strip_non_prose(lines))
    section = ""
    quotes = {eid: r.get("quote", "") for eid, r in self.evidence.items()}
    calc_bound_nums = {
        cid: calc.bound_numbers_for_record(crec)
        for cid, crec in self.calculations.items()
    }
    traps = load_known_traps()
    body_cited: set[str] = set()  # cited outside Sources / Verification
    claim_count = 0
    inline_unverified_calc_count = 0

    exempt = False
    for u in units:
      if u.kind == "heading":
        section = u.text
        exempt = cr.heading_exempt(u.text, exempt)
        continue
      if exempt:
        self._exempt_claim_check(u)
        continue
      raw_eids = EID_RE.findall(u.text)
      raw_cids = CID_RE.findall(u.text)
      body_cited |= set(raw_eids)
      for cid in raw_cids:
        if cid in self.calculations:
          body_cited |= set(self.calculations[cid].get("cited_eids") or [])

      # R8: Check against known killed edges and traps
      trap_violations = check_known_traps_in_text(u.text, traps)
      for t in trap_violations:
        self.F("R8", f"L{u.line}: asserts known killed edge / trap '{t['name']}' without acknowledging lab refutation")

      if not cr._is_claim(u.text):
        continue
      if cr.SOURCE_LINE_RE.match(u.text):
        continue
      claim_count += 1

      known_eids = [e for e in raw_eids if e in self.evidence]
      for e in set(raw_eids) - set(known_eids):
        self.F("R2", f"L{u.line}: cites {e}, which is not in evidence.jsonl")

      known_cids = [c for c in raw_cids if c in self.calculations]
      for c in set(raw_cids) - set(known_cids):
        self.F("R2", f"L{u.line}: cites {c}, which is not in calculations.jsonl")

      effective_eids = list(known_eids)
      for c in known_cids:
        for ce in self.calculations[c].get("cited_eids") or []:
          if ce in self.evidence and ce not in effective_eids:
            effective_eids.append(ce)

      explicit_assumption = bool(known_cids and ASSUMPTION_LABEL_RE.search(cr.LEADING_ENUM_RE.sub("", u.text)))
      if not effective_eids and not explicit_assumption:
        self.F("R2", f"L{u.line}: claim has no valid evidence ID [E###]: {u.text[:110]}")
        continue

      # R7: Check against uncalibrated subjective probabilities
      combined_quotes = " ".join(quotes.get(e, "") for e in effective_eids)
      uncal_err = check_uncalibrated_probabilities(u.text, quote=combined_quotes)
      if uncal_err:
        self.F("R7", f"L{u.line}: {uncal_err}")

      # R3: Strict Quote + [C###] Number Binding (with row-scope union for table_row and structural whitelist)
      bound: set = set()
      for e in effective_eids:
        bound |= numbers(quotes[e], strip_structural=False)
      for c in known_cids:
        bound |= calc_bound_nums[c]

      unit_nums = material(numbers(u.text, strip_structural=True))
      missing = sorted(
          unit_nums - bound,
          key=lambda x: (0, float(x)) if isinstance(x, (int, float)) else (1, str(x)),
      )
      if not missing:
        continue

      has_inf_marker = bool(INLINE_INF_TAG_RE.search(u.text))
      is_formal_calc = bool(FORMAL_CALC_RE.search(u.text) and CALC_OPERATOR_RE.search(u.text))
      is_calibrated_sample = bool(
          (ESTIMATE_LABEL_RE.search(u.text) or has_inf_marker) and SAMPLE_SIZE_RE.search(u.text)
      )
      # Allow [I] / [EST] heuristic scores and projections in table rows, paragraphs, and bullets,
      # when the unit has valid [E###] or [C###] and is explicitly tagged with [I] or [EST].
      is_tagged_inference = has_inf_marker and bool(effective_eids or known_cids)

      if is_formal_calc or is_calibrated_sample or is_tagged_inference:
        if (is_formal_calc or is_tagged_inference) and not known_cids and u.kind != "table_row":
          inline_unverified_calc_count += 1
        continue

      shown = ", ".join(f"{m:g}" if isinstance(m, (int, float)) else str(m) for m in missing[:5])
      if INFERENCE_LABEL_RE.search(u.text) and not has_inf_marker:
        self.F("R3", f"L{u.line}: number(s) {shown} not in {', '.join(effective_eids)} - "
                     f"'Inference:'/'Извод:' cannot introduce unbound numbers without [I]/[EST] + [C###]; "
                     f"register math with calc.py [C###] or fetch primary evidence")
      elif FORMAL_CALC_RE.search(u.text):
        self.F("R3", f"L{u.line}: 'Calculation:' unit introduces number(s) {shown} without an explicit "
                     f"formula/equation (=, +, -, *, /) or verified calc.py [C###] record")
      else:
        refs_shown = ", ".join(effective_eids + known_cids)
        self.F("R3", f"L{u.line} ({u.kind}): number(s) {shown} not in the union of quotes/calculations "
                     f"of [{refs_shown}] - cite the evidence on this row/sentence or register calc.py [C###]")

    # R9: Anti-Bypass Ceiling on unverified inline 'Calculation:' prose
    if claim_count >= 5 and (inline_unverified_calc_count / claim_count) > max_inline_calc_share:
      self.F("R9", f"unverified inline 'Calculation:' units are {inline_unverified_calc_count}/{claim_count} "
                   f"({inline_unverified_calc_count / claim_count:.0%}) > {max_inline_calc_share:.0%} ceiling - "
                   f"register deterministic formulas in calculations.jsonl via calc.py [C###]")

    for eid, r in self.evidence.items():
      if r.get("stance") == "contradicts" and eid not in body_cited:
        self.F("R4", f"{eid} contradicts the thesis ({r.get('claim', '')[:80]}) but the report never addresses it")
    headings = [l for l in lines if l.lstrip().startswith("#")]
    for h in headings:
      for t in check_known_traps_in_text(h, traps):
        self.F("R8", f"Heading asserts known killed edge / trap '{t['name']}': {h}")
    if not any(KILL_SECTION_RE.search(h) for h in headings):
      self.F("R5", "report has no 'Kill hypotheses' / 'Red team' section")
    for k, info in self.kills.items():
      if info["verdict"] == "pending":
        self.F("R5", f"{k}: verdict still pending in plan.md (confirmed / refuted / unresolved)")
    for n, line in enumerate(lines, 1):
      if SELF_SCORE_RE.search(line):
        self.F("R6", f"L{n}: self-assigned score - remove it; the gates are the assessment")

    self._conflicts_check(units)
    self._audit_check(text, require_audit, max_error)
    self._completeness_check(text, units)

    # R10: Mechanical Confidence Cap Enforcement via formula.py
    self.scorecard = formula.compute_epistemic_score(self.d, report_path=report)
    if self.scorecard["confidence_overclaimed"]:
      lim = "; ".join(self.scorecard["limiting_factors"][:3])
      self.F("R10", f"L{self.scorecard['declared_confidence_line']}: declared overall confidence "
                    f"'{self.scorecard['declared_confidence']}' exceeds mechanical ceiling "
                    f"'{self.scorecard['max_confidence']}' (EI={self.scorecard['epistemic_index']}/100; {lim})")

  # E9: discovery completeness - the screening audit and the coverage / saturation estimate
  def _discovery_check(self, d: Path, strict: bool) -> None:
    sdata = screening_mod.load(d)
    if sdata:
      s = screening_mod.summary(d, sdata)
      if s["pending"]:
        self.F("E9", f"screening audit has {len(s['pending'])} unjudged item(s): "
                     f"{', '.join(s['pending'][:8])} (screening.py record)")
      for i in s["relevant_not_fetched"]:
        self.F("E9", f"screening item {i} was judged relevant but is not in sources/ - fetch it "
                     f"(evidence.py fetch) and record it with --source S###")
      if not s["pending"] and s["cp_upper"] > screening_mod.MAX_LOSS:
        self.W("E9", f"screening loss bound {s['cp_upper']:.0%} > 20%: up to ~{s['max_lost']:.0f} "
                     f"relevant source(s) may have been discarded unread - fetch more of the leads")
    elif strict:
      self.W("E9", "no screening audit: the share of relevant leads discarded unread is unmeasured "
                   "(screening.py sample --dir <dir>)")
    cov_path = d / "coverage.json"
    if cov_path.exists():
      try:
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
      except json.JSONDecodeError:
        cov = {}
      n_now = len(_jsonl(d / "sources" / "index.jsonl"))
      if cov.get("sources") != n_now:
        self.W("E9", f"coverage.json was computed on {cov.get('sources')} sources, the corpus has "
                     f"{n_now}: re-run corpus.py stats --dir <dir> --save")
      elif cov.get("verdict") != "SATURATED":
        self.W("E9", f"corpus.py stats verdict {cov.get('verdict')}: "
                     + "; ".join(cov.get("reasons", [])[:2]))
    elif strict:
      self.W("E9", "coverage and saturation not measured (corpus.py stats --dir <dir> --save)")

  # R13: no findings hidden in the exempt Sources / Verification sections
  def _exempt_claim_check(self, u) -> None:
    if u.kind == "heading" or EID_RE.search(u.text) or CID_RE.search(u.text):
      return
    if cr.SOURCE_LINE_RE.match(u.text) or SOURCE_REF_LINE_RE.match(u.text):
      return
    if FORMULA_LINE_RE.match(u.text):  # pasted formula.py scorecard: tool output, recomputed by gate
      return
    if VERDICT_RE.search(u.text) and PROCESS_RE.search(u.text):
      self.W("R13", f"L{u.line}: self-reported verification status (records, gates, searches) - "
                    f"paste the tool output instead of describing it: {u.text[:90]}")
    elif VERDICT_RE.search(u.text):
      self.F("R13", f"L{u.line}: finding stated in the Sources/Verification section without "
                    f"evidence - those sections are not audited; move it into the body with "
                    f"[E###] or delete it: {u.text[:90]}")
    elif cr._is_claim(re.sub(r"`[^`]*`", "", u.text)):  # paths and commands are not claims
      self.W("R13", f"L{u.line}: uncited claim in the Sources/Verification section "
                    f"(not audited): {u.text[:90]}")

  # R11: every conflict found in claims.jsonl is confronted in the Conflicts section
  def _conflicts_check(self, units: list) -> None:
    claims = load_claims(self.d)
    if not claims:
      return
    conflicts = claims_mod.find_conflicts(claims, self.evidence)
    section, conflict_units = "", []
    for u in units:
      if u.kind == "heading":
        section = u.text
      elif CONFLICT_SECTION_RE.search(section):
        conflict_units.append(u.text)
    for c in conflicts:
      rows = [t for t in conflict_units
              if set(EID_RE.findall(t)) & set(c["a_eids"]) and set(EID_RE.findall(t)) & set(c["b_eids"])]
      label = f"{c['a']} vs {c['b']} [{c['key']}] (axes: {', '.join(c['axes'])})"
      if not rows:
        self.F("R11", f"conflict {label} is not in the Conflicts section with evidence from both sides")
      elif c["axes"] == ["UNEXPLAINED"] and not any(UNRESOLVED_RE.search(t) for t in rows):
        self.F("R11", f"conflict {label} has no explaining axis - investigate it or mark it unresolved")

  # R12: sampled claim audit (audit.py) with a one-sided 95% error bound
  def _audit_check(self, report_text: str, require: bool, max_error: float) -> None:
    data = audit_mod.load(self.d)
    if not data:
      if require:
        self.F("R12", "no claim audit - run audit.py sample, have a fresh verifier judge "
                      "audit/brief.md, record the verdicts")
      return
    s = audit_mod.summary(data)
    self.audit = s
    if s["pending"]:
      self.F("R12", f"audit has {len(s['pending'])} unjudged item(s): {', '.join(s['pending'][:8])}")
    for p in audit_mod.check_against_report(data, report_text):
      self.F("R12", f"audit - {p}")
    if not s["pending"] and s["upper_bound"] > max_error:
      self.F("R12", f"unsupported-claim rate upper bound {s['upper_bound']:.1%} > {max_error:.0%} "
                    f"({s['errors']} error(s) in {s['n']}); fix them and re-audit a fresh sample")

  # R14: Anti-Goodhart Completeness Gate (validates mandatory volume and structural quotas from quotas.json)
  def _completeness_check(self, report_text: str, units: list) -> None:
    q_path = self.d / "quotas.json"
    if not q_path.exists():
      return
    try:
      quotas = json.loads(q_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
      self.F("R14", f"quotas.json is not valid JSON: {e}")
      return

    # 1. Минимален общ брой думи в доклада
    min_words = int(quotas.get("min_words", 0))
    if min_words > 0:
      word_count = len(re.findall(r"\S+", report_text))
      if word_count < min_words:
        self.F("R14", f"report has {word_count} words; quotas.json requires >= {min_words} words "
                      f"(anti-truncation gate: expand analysis, tables, and deep dives)")

    # 2. Минимален брой доказателства [E###] и изчисления [C###]
    min_ev = int(quotas.get("min_evidence", 0))
    if min_ev > 0 and len(self.evidence) < min_ev:
      self.F("R14", f"study has {len(self.evidence)} evidence records; quotas.json requires >= {min_ev}")

    min_calcs = int(quotas.get("min_calculations", 0))
    if min_calcs > 0 and len(self.calculations) < min_calcs:
      self.F("R14", f"study has {len(self.calculations)} [C###] calculations; quotas.json requires >= {min_calcs}")

    # 3. Минимален брой уникални цитирани [E###] от тип review_pain / потребителски цитати в тялото
    min_review_cites = int(quotas.get("min_review_quotes_cited", 0))
    if min_review_cites > 0:
      cited_eids = set(EID_RE.findall(report_text))
      review_cites = sum(
          1 for eid in cited_eids
          if eid in self.evidence and is_review_pain_evidence(
              self.evidence[eid], self.index.get(self.evidence[eid].get("source", ""))
          )
      )
      if review_cites < min_review_cites:
        self.F("R14", f"report cites {review_cites} review/complaint evidence items; "
                      f"quotas.json requires >= {min_review_cites}")

    # 4. Минимален брой редове в таблици по секции (напр. {"SQ1": 30, "Long list": 20, "Scoring": 20})
    section_table_quotas: dict[str, int] = quotas.get("min_table_rows_by_section", {})
    if section_table_quotas:
      sec_rows: dict[str, int] = {k: 0 for k in section_table_quotas}
      current_headings: list[str] = []
      for u in units:
        if u.kind == "heading":
          lvl = len(u.text) - len(u.text.lstrip("#"))
          current_headings = [h for h in current_headings if (len(h) - len(h.lstrip("#"))) < lvl]
          current_headings.append(u.text)
        elif u.kind == "table_row":
          joined_h = " ".join(current_headings)
          for sec_pat, _ in section_table_quotas.items():
            if re.search(sec_pat, joined_h, re.I):
              sec_rows[sec_pat] += 1
      for sec_pat, req_rows in section_table_quotas.items():
        if sec_rows[sec_pat] < req_rows:
          self.F("R14", f"section matching {sec_pat!r} has {sec_rows[sec_pat]} table data rows; "
                        f"quotas.json requires >= {req_rows} rows")

    # 5. Минимален брой Deep Dive профили и минимална дължина на всеки
    min_deep_dives = int(quotas.get("min_deep_dives", 0))
    min_dd_words = int(quotas.get("min_deep_dive_words", 400))
    dd_heading_pat = quotas.get("deep_dive_heading_pattern", r"(?:Deep\s*Dive|Дълбок\s*анализ|Концепция|Candidate|Идея)\s*#?\d+")
    if min_deep_dives > 0:
      dd_re = re.compile(dd_heading_pat, re.I)
      dd_sections: list[tuple[str, list[str]]] = []
      cur_dd_title: str | None = None
      cur_dd_lines: list[str] = []
      cur_dd_level = 0
      for line in report_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
          lvl = len(s) - len(s.lstrip("#"))
          if dd_re.search(s):
            if cur_dd_title is not None:
              dd_sections.append((cur_dd_title, cur_dd_lines))
            cur_dd_title = s
            cur_dd_lines = []
            cur_dd_level = lvl
            continue
          elif cur_dd_title is not None and lvl <= cur_dd_level:
            dd_sections.append((cur_dd_title, cur_dd_lines))
            cur_dd_title = None
            cur_dd_lines = []
        if cur_dd_title is not None:
          cur_dd_lines.append(line)
      if cur_dd_title is not None:
        dd_sections.append((cur_dd_title, cur_dd_lines))

      if len(dd_sections) < min_deep_dives:
        self.F("R14", f"found {len(dd_sections)} deep-dive section(s) matching {dd_heading_pat!r}; "
                      f"quotas.json requires >= {min_deep_dives}")
      for title, dlines in dd_sections:
        w_cnt = len(re.findall(r"\S+", "\n".join(dlines)))
        if w_cnt < min_dd_words:
          self.F("R14", f"deep-dive {title!r} has only {w_cnt} words; "
                        f"quotas.json requires >= {min_dd_words} words per deep dive")

  # ---------------------------------------------------------------- live
  def live_sample(self, n: int) -> None:
    by_source: dict[str, list[dict]] = {}
    for r in self.evidence.values():
      by_source.setdefault(r["source"], []).append(r)
    valid_sids = [
        sid for sid in sorted(by_source)
        if self.index.get(sid, {}).get("url", "").startswith(("http://", "https://"))
        and self.index.get(sid, {}).get("via") != "manual"
    ]
    for sid in random.sample(valid_sids, min(n, len(valid_sids))):
      url = self.index[sid]["url"]
      # r.jina.ai is a third-party service: re-fetch through it only with the user's opt-in
      use_jina = self.index[sid].get("via") == "jina" and os.environ.get("DR_ALLOW_JINA") == "1"
      page = fetch_page(url, jina_fallback=use_jina)
      if not page["ok"] and self.index[sid].get("via") == "jina" and not use_jina:
        self.W("L1", f"{sid} was captured via r.jina.ai and cannot be re-fetched directly "
                     f"({page['error']}); set DR_ALLOW_JINA=1 only if the user allows that service")
        continue
      if not page["ok"]:
        self.F("L1", f"{sid} live re-fetch failed ({page['error']}): {url}")
        continue
      for r in by_source[sid]:
        if match_score(r["quote"], page["text"]) < 1.0:
          self.F("L1", f"{r['id']}: quote no longer (or never) on the live page {url}")


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("dir", type=Path)
  ap.add_argument("--stage", choices=("evidence", "report"), default="report")
  ap.add_argument("--report", type=Path, help="default: <dir>/report.md")
  ap.add_argument("--min-searches", type=int, default=12)
  ap.add_argument("--kill-share", type=float, default=0.30)
  ap.add_argument("--strict-kill-results", action=argparse.BooleanOptionalAction, default=None,
                  help="count only kill searches with a recorded result set (default: on for "
                       "studies with study.json protocol >= 4.1 or dated >= " + E4_STRICT_FROM + ")")
  ap.add_argument("--min-primary-share", type=float, default=0.50)
  ap.add_argument("--min-coverage", type=float, default=0.9)
  ap.add_argument("--min-urls", type=int, default=5)
  ap.add_argument("--max-inline-calc-share", type=float, default=0.40)
  ap.add_argument("--live", type=int, default=0, metavar="N")
  ap.add_argument("--scorecard", action="store_true", help="print full Markdown Epistemic Scorecard")
  ap.add_argument("--require-audit", action="store_true",
                  help="fail without a judged audit.py sample (R12)")
  ap.add_argument("--max-error", type=float, default=0.15,
                  help="max 95%% upper bound on the unsupported-claim rate (R12)")
  args = ap.parse_args(argv)

  g = Gate(args.dir)
  g.evidence_stage(args.min_searches, args.kill_share, args.min_primary_share,
                   args.strict_kill_results)
  if args.stage == "report":
    g.report_stage(
        args.report or args.dir / "report.md",
        args.min_coverage,
        args.min_urls,
        args.max_inline_calc_share,
        args.require_audit,
        args.max_error,
    )
  else:
    g.scorecard = formula.compute_epistemic_score(args.dir, report_path=args.report)
  if args.live:
    g.live_sample(args.live)

  status = "PASS" if not g.fail else "FAIL"
  sc_hint = ""
  if g.scorecard:
    sc_hint = f" EI={g.scorecard['epistemic_index']:.1f}/100 max_conf={g.scorecard['max_confidence']}"
  if g.audit and not g.audit["pending"]:
    sc_hint += (f" audit={g.audit['errors']}/{g.audit['n']} err, "
                f"<= {g.audit['upper_bound']:.1%} @95%")
  print(f"[{status}] {args.dir}  stage={args.stage}  "
        f"sources={len(getattr(g, 'index', {}))} evidence={len(g.evidence)} "
        f"calcs={len(g.calculations)}{sc_hint}")
  for i, f in enumerate(g.fail, 1):
    print(f"  {i:>3}. FAIL {f}")
  for w in g.warn:
    print(f"       WARN {w}")
  if args.scorecard and g.scorecard:
    print("")
    print(formula.format_scorecard_markdown(g.scorecard))
  return 1 if g.fail else 0


if __name__ == "__main__":
  sys.exit(main())
