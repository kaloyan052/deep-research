#!/usr/bin/env python3
"""Deep Research Engine v13.0 — Anti-Truncation Depth, Claim-Link-Quote Ledger,
Anti-Hallucination Multiplier/Frequency & Deliverable Attestation Gates.

Closes the four structural failure modes exposed by the RP52A-H postmortem:
  * Rule R19 (Anti-Truncation & Deep-Digging Quotas): closes the R17 IDI
    denominator Goodhart loophole where a 20-line stub achieved high IDI by
    shrinking `word_count`. Enforces prose word floor, distinct snapshotted
    source floor, verified verbatim quote floor, table breadth, section count,
    and computed `python:model` variable depth.
  * Rule R20 (Mandatory `Claim -> URL -> Verbatim Quote` Ledger): requires an
    explicit human-auditable Markdown table in `report.md` mapping each core
    claim to a clickable primary URL and an exact verbatim quote verified
    against `sources/S###.txt` and `sources/index.jsonl`.
  * Rule B12 (Hyperbolic Verdict, Fake Multiplier & Frequency Guess Ban):
    bans marketing hype labels (`MAXIMUM CONVICTION GO`), requires standalone
    payoff/fee multipliers (`11.8x`) to match a finite `python:model` variable
    or verified `[E###]` quote, and requires event-frequency assertions
    (`100-150 occurrences/year`) to cite a verified `[E###]` or `[C###]`.
  * Rule R21 (Deliverable Receipt & `reports/` Anti-Bypass Guard): writes a
    tamper-evident `verification_receipt.json` on verification PASS, gates
    export into `reports/`, and audits `reports/*.md` against unverified writes.

Pure Python 3.10+ stdlib. Fail-closed under Rule B0. Windows cp1252-safe.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sys
import traceback
import urllib.parse
from pathlib import Path
from typing import Any, Callable

_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.deep_digger import registrable_domain  # noqa: E402
from dr_engine.tools.epistemic_guard import is_mitigated_locally  # noqa: E402

__all__ = [
    "PROTOCOL_VERSION_V13",
    "DEFAULT_V13_QUOTAS",
    "parse_protocol_version",
    "version_at_least",
    "is_v13_protocol",
    "validate_depth_quotas",
    "validate_claim_link_quote_ledger",
    "run_b12_anti_hallucination_filter",
    "run_v13_gates_fail_closed",
    "render_claim_ledger_scaffold",
    "write_verification_receipt",
    "export_verified_report",
    "audit_deliverables_directory",
]

PROTOCOL_VERSION_V13 = "13.0"

DEFAULT_V13_QUOTAS: dict[str, int] = {
    "min_words": 1000,
    "min_sources": 5,
    "min_evidence": 8,
    "min_tables": 2,
    "min_sections": 5,
    "min_model_vars": 4,
    "min_ledger_rows": 8,
}

HARD_FLOOR_QUOTAS: dict[str, int] = {
    "min_words": 350,
    "min_sources": 3,
    "min_evidence": 4,
    "min_tables": 1,
    "min_sections": 3,
    "min_model_vars": 2,
    "min_ledger_rows": 4,
}

ATTESTATION_MARKER_RE = re.compile(
    r"\n*---\n<!-- DR-ATTESTATION:\s*(\{.*?\})\s*-->.*?\Z",
    re.S,
)

HYPERBOLIC_VERDICT_RE = re.compile(
    r"\b(?:"
    r"MAXIMUM\s+CONVICTION(?:\s+GO)?|"
    r"MAX\s+CONVICTION(?:\s+GO)?|"
    r"100%\s+CONVICTION|"
    r"GUARANTEED\s+(?:EDGE|PROFIT|ALPHA|RETURN|WINNER)|"
    r"RISK[- ]FREE\s+(?:ALPHA|PROFIT|EDGE)|"
    r"ZERO[- ]RISK\s+(?:ALPHA|EDGE|PROFIT)|"
    r"CERTAIN\s+(?:WINNER|EDGE|PROFIT)|"
    r"БЕЗУСЛОВНО\s+GO|"
    r"ГАРАНТИРАН[АИО]?\s+(?:ПЕЧАЛБА|ДОХОДНОСТ|ЕДЖ)|"
    r"СИГУРНА\s+ПЕЧАЛБА"
    r")\b",
    re.I,
)

# Standalone numeric multiplier such as `11.8x`, `10.4×`, `8.2x`.
MULTIPLIER_RE = re.compile(
    r"(?<![A-Za-z0-9_/.:=\-])(\d{1,4}(?:\.\d+)?)\s*(?:x|×)(?![A-Za-z0-9_])"
)

# Benign technical contexts immediately before/after `Nx` (e.g. `1.5 × ATR`, `x3.0` BM25 prior).
BENIGN_MULTIPLIER_AFTER_RE = re.compile(
    r"^\s*(?:ATR|sigma|std|stdev|SD|vol|volatility|bars?|steps?|hops?|retries|"
    r"leverage|margin|BM25|prior|boost|speedup|faster|daily|per\s+day|per\s+week|"
    r"roll|etf|etp|short|long|\d+\b)",
    re.I,
)

FREQUENCY_CLAIM_RE = re.compile(
    r"(?:~\s*|≈\s*|\babout\s+|\bapprox(?:imately)?\.?\s+|\bоколо\s+|\bприблизително\s+)?"
    r"\b\d{1,4}(?:\s*[-–]\s*\d{1,4})?\s+"
    r"(?:occurrences|events|setups|triggers|signals|instances|случая|събития|сигнала|входа)\s*"
    r"(?:/|per\s+|a\s+|на\s+)(?:year|yr|annum|month|mo|week|година|месец|седмица)\b",
    re.I,
)

LOCAL_REFUTATION_TERMS = (
    "refuted", "false", "hallucinated", "unbacked", "unverified", "erroneous",
    "killed", "rejected", "wrong", "disproved", "0 times", "zero times",
    "грешен", "грешно", "убито", "невярно", "няма изчисление", "без изчисление",
    "опроверган", "отхвърлен", "0 пъти", "вместо обещаните",
)

EID_RE = re.compile(r"\b(E\d{3})\b")
CID_RE = re.compile(r"\b(C\d{3})\b")
URL_IN_CELL_RE = re.compile(r"https?://[^\s)>\]\"'|]+")
PLACEHOLDER_CELL_RE = re.compile(r"<\s*[^>]{1,160}\s*>|\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b", re.I)

CLAIM_HEADER_TOKENS = ("claim", "assertion", "finding", "fact", "rule", "твърдение", "факт", "правило", "констатация")
LINK_HEADER_TOKENS = ("url", "link", "source", "линк", "източник", "връзка", "адрес")
QUOTE_HEADER_TOKENS = ("quote", "verbatim", "excerpt", "цитат", "дословен", "извадка")


def parse_protocol_version(raw: Any) -> tuple[int, int]:
    """Parse `'13.0'` -> `(13, 0)`; never raises on malformed values."""
    if raw is None or isinstance(raw, bool):
        return (0, 0)
    s = str(raw).strip().lstrip("vV")
    m = re.match(r"^(\d+)(?:\.(\d+))?$", s)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))


def version_at_least(raw: Any, major: int, minor: int = 0) -> bool:
    return parse_protocol_version(raw) >= (major, minor)


def is_v13_protocol(
    study_dir: Path | str | None,
    manifest: dict[str, Any] | None,
    *,
    force: bool = False,
) -> bool:
    """True when v13 gates (R19, R20, B12) apply to this study."""
    if force:
        return True
    if isinstance(manifest, dict):
        if version_at_least(manifest.get("protocol_version"), 13, 0):
            return True
        if isinstance(manifest.get("depth_quotas"), dict):
            return True
        if manifest.get("claim_ledger_required") is True:
            return True
    if study_dir is not None:
        spec_p = Path(study_dir) / "study_spec.json"
        try:
            if spec_p.exists():
                spec = json.loads(spec_p.read_text(encoding="utf-8"))
                if isinstance(spec, dict) and version_at_least(spec.get("protocol_version"), 13, 0):
                    return True
        except (OSError, ValueError, TypeError):
            pass
    return False


def strip_non_prose_blocks(report_text: str) -> str:
    """Remove fenced code/manifest/model blocks and attestation footers."""
    txt = ATTESTATION_MARKER_RE.sub("", str(report_text or ""))
    txt = re.sub(r"```.*?```", "\n", txt, flags=re.S)
    return txt


def _extract_markdown_tables(prose_text: str) -> list[dict[str, Any]]:
    """Parse pipe-delimited Markdown tables into `{'headers': [...], 'rows': [[...], ...]}`."""
    tables: list[dict[str, Any]] = []
    lines = prose_text.splitlines()
    i = 0
    n = len(lines)
    sep_re = re.compile(r"^\s*\|?\s*:?-{2,}:?(?:\s*\|\s*:?-{2,}:?)+\s*\|?\s*$")

    def _split_row(ln: str) -> list[str]:
        s = ln.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        # Respect escaped `\|` inside quotes
        parts = re.split(r"(?<!\\)\|", s)
        return [p.replace(r"\|", "|").strip() for p in parts]

    while i < n - 1:
        if "|" in lines[i] and sep_re.match(lines[i + 1]):
            headers = _split_row(lines[i])
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                if not sep_re.match(lines[i]):
                    rows.append(_split_row(lines[i]))
                i += 1
            if len(headers) >= 2 and rows:
                tables.append({"headers": headers, "rows": rows})
            continue
        i += 1
    return tables


def _resolve_quotas(study_dir: Path | str | None, manifest: dict[str, Any] | None) -> tuple[dict[str, int], bool]:
    quotas = dict(DEFAULT_V13_QUOTAS)
    compact_fixture = False
    overrides: dict[str, Any] = {}

    if study_dir is not None:
        spec_p = Path(study_dir) / "study_spec.json"
        try:
            if spec_p.exists():
                spec = json.loads(spec_p.read_text(encoding="utf-8"))
                if isinstance(spec, dict) and isinstance(spec.get("depth_quotas"), dict):
                    overrides.update(spec["depth_quotas"])
        except (OSError, ValueError, TypeError):
            pass

    if isinstance(manifest, dict) and isinstance(manifest.get("depth_quotas"), dict):
        overrides.update(manifest["depth_quotas"])

    if overrides.get("allow_compact_fixture") is True:
        compact_fixture = True

    for key, default_val in DEFAULT_V13_QUOTAS.items():
        if key in overrides and isinstance(overrides[key], int) and not isinstance(overrides[key], bool):
            floor = 1 if compact_fixture else HARD_FLOOR_QUOTAS[key]
            quotas[key] = max(floor, int(overrides[key]))
        else:
            quotas[key] = default_val
    return quotas, compact_fixture


def validate_depth_quotas(
    report_text: str,
    *,
    study_dir: Path | str | None,
    manifest: dict[str, Any],
    n_sources: int,
    n_verified_evidence: int,
    model_env: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Enforce Rule R19: Anti-Truncation & Minimum Deep-Digging Floor."""
    quotas, compact = _resolve_quotas(study_dir, manifest)
    prose = strip_non_prose_blocks(report_text)
    words = re.findall(r"[\w\u0400-\u04FF]+", prose)
    word_count = len(words)
    tables = _extract_markdown_tables(prose)
    substantive_tables = [t for t in tables if len(t["rows"]) >= 2]
    sections = re.findall(r"^##\s+\S+", prose, flags=re.M)
    finite_vars = [
        k for k, v in (model_env or {}).items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
    ]

    failures: list[str] = []
    if word_count < quotas["min_words"]:
        failures.append(
            f"R19 (Shallow Prose / Truncation): report has only {word_count} prose words "
            f"(excluding code/manifest); v13 requires >= {quotas['min_words']} words of grounded analysis. "
            f"15-30 line summaries are banned."
        )
    if n_sources < quotas["min_sources"]:
        failures.append(
            f"R19 (Insufficient Source Digging): only {n_sources} distinct sources snapshotted in "
            f"`sources/index.jsonl`; v13 requires >= {quotas['min_sources']} (run `deep_digger.py dig` "
            f"or `lean_engine.py ingest --deep` to crawl T&Cs, FAQs, subpages & literature)."
        )
    if n_verified_evidence < quotas["min_evidence"]:
        failures.append(
            f"R19 (Insufficient Verified Quotes): only {n_verified_evidence} verbatim `[E###]` quotes "
            f"verified against snapshots; v13 requires >= {quotas['min_evidence']}."
        )
    if len(substantive_tables) < quotas["min_tables"]:
        failures.append(
            f"R19 (Missing Structured Tables): found {len(substantive_tables)} Markdown table(s) with >= 2 rows; "
            f"v13 requires >= {quotas['min_tables']} (Claim-Link-Quote Ledger + Comparative/Cost/Rejection Matrix)."
        )
    if len(sections) < quotas["min_sections"]:
        failures.append(
            f"R19 (Missing Analytical Breadth): found {len(sections)} `## ` sections; "
            f"v13 requires >= {quotas['min_sections']} distinct analytical sections."
        )
    if len(finite_vars) < quotas["min_model_vars"]:
        failures.append(
            f"R19 (Thin Quantitative Model): `python:model` computes {len(finite_vars)} finite variable(s); "
            f"v13 requires >= {quotas['min_model_vars']} deterministic variables."
        )

    diag = {
        "quotas": quotas,
        "compact_fixture": compact,
        "measured": {
            "prose_words": word_count,
            "n_sources": n_sources,
            "n_verified_evidence": n_verified_evidence,
            "n_tables": len(substantive_tables),
            "n_sections": len(sections),
            "n_model_vars": len(finite_vars),
        },
        "passed": not failures,
    }
    return failures, diag


def _normalize_quote_ws(s: str) -> str:
    trans = str.maketrans({
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u201e": '"', "\u00ab": '"', "\u00bb": '"',
        "\u2013": "-", "\u2014": "-", "\u00a0": " ",
    })
    return re.sub(r"\s+", " ", s.translate(trans)).strip()


def _quote_in_snapshot(quote_cell: str, snapshot_text: str) -> bool:
    q = str(quote_cell or "").strip()
    # Strip outer Markdown italics/quotes/backticks around the verbatim excerpt
    q = re.sub(r"^[\s*`\"'„“”«»]+|[\s*`\"'„“”«»]+$", "", q)
    # Also strip trailing `[E001]` if placed inside the quote cell
    q = re.sub(r"\s*\[?E\d{3}\]?\s*$", "", q).strip()
    q = re.sub(r"^[\s*`\"'„“”«»]+|[\s*`\"'„“”«»]+$", "", q)
    norm_q = _normalize_quote_ws(q)
    if len(norm_q) < 15:
        return False
    norm_snap = _normalize_quote_ws(snapshot_text)
    if norm_q in norm_snap:
        return True
    return norm_q.lower() in norm_snap.lower()


def _identify_ledger_columns(headers: list[str]) -> dict[str, int] | None:
    low_headers = [h.lower() for h in headers]
    claim_idx = next((i for i, h in enumerate(low_headers) if any(t in h for t in CLAIM_HEADER_TOKENS)), None)
    link_idx = next((i for i, h in enumerate(low_headers) if any(t in h for t in LINK_HEADER_TOKENS)), None)
    quote_idx = next((i for i, h in enumerate(low_headers) if any(t in h for t in QUOTE_HEADER_TOKENS)), None)
    if claim_idx is None or link_idx is None or quote_idx is None:
        return None
    if len({claim_idx, link_idx, quote_idx}) < 3:
        return None
    return {"claim": claim_idx, "link": link_idx, "quote": quote_idx}


def validate_claim_link_quote_ledger(
    report_text: str,
    *,
    manifest: dict[str, Any],
    sources_index: dict[str, dict[str, Any]],
    source_texts: dict[str, str],
    verified_evidence_ids: set[str],
    min_rows: int = 8,
) -> tuple[list[str], dict[str, Any]]:
    """Enforce Rule R20: Mandatory `Claim -> URL -> Verbatim Quote` Ledger Table."""
    prose = strip_non_prose_blocks(report_text)
    tables = _extract_markdown_tables(prose)

    ev_map: dict[str, dict[str, Any]] = {}
    for ev in (manifest.get("evidence") or []):
        if isinstance(ev, dict) and ev.get("id"):
            ev_map[str(ev["id"])] = ev

    matched_table: dict[str, Any] | None = None
    col_map: dict[str, int] | None = None
    for t in tables:
        cm = _identify_ledger_columns(t["headers"])
        if cm is not None:
            matched_table = t
            col_map = cm
            break

    if matched_table is None or col_map is None:
        return [
            "R20 (Claim-Link-Quote Ledger Missing): `report.md` must contain a Markdown table "
            "mapping `Claim | Source URL | Verbatim Quote | Evidence ID` (or BG `Твърдение | Линк | Дословен цитат | ID`) "
            "so every key fact can be audited inline without opening JSON."
        ], {"present": False, "valid_rows": 0, "total_rows": 0, "passed": False}

    rows = matched_table["rows"]
    failures: list[str] = []
    valid_rows = 0

    if len(rows) < min_rows:
        failures.append(
            f"R20 (Ledger Too Thin): Claim-Link-Quote table has {len(rows)} row(s); "
            f"need >= {min_rows} grounded rows."
        )

    for r_idx, row in enumerate(rows, 1):
        max_col = max(col_map.values())
        if len(row) <= max_col:
            failures.append(f"R20 (Malformed Ledger Row #{r_idx}): row has {len(row)} columns, expected >= {max_col + 1}.")
            continue

        claim_cell = row[col_map["claim"]].strip()
        link_cell = row[col_map["link"]].strip()
        quote_cell = row[col_map["quote"]].strip()
        joined_row = " | ".join(row)

        if len(claim_cell) < 10 or PLACEHOLDER_CELL_RE.search(claim_cell):
            failures.append(f"R20 (Empty/Placeholder Claim in Row #{r_idx}): {claim_cell[:60]!r}")
            continue

        urls = URL_IN_CELL_RE.findall(link_cell)
        if not urls:
            failures.append(
                f"R20 (Missing Source URL in Row #{r_idx}): link column {link_cell[:60]!r} "
                f"contains no clickable `http(s)://` URL."
            )
            continue
        row_url = urls[0].rstrip(".,;)")

        eids = EID_RE.findall(joined_row)
        if not eids:
            failures.append(
                f"R20 (Missing [E###] in Row #{r_idx}): ledger row must reference its snapshot-verified `[E###]` ID."
            )
            continue

        verified_row_eids = [e for e in eids if e in verified_evidence_ids and e in ev_map]
        if not verified_row_eids:
            failures.append(
                f"R20 (Unverified [E###] in Row #{r_idx}): {eids} did not pass verbatim snapshot verification."
            )
            continue

        eid = verified_row_eids[0]
        sid = str(ev_map[eid].get("source", ""))
        src_meta = sources_index.get(sid) or {}
        snap_url = str(src_meta.get("url", ""))
        snap_text = source_texts.get(sid, "")

        row_dom = registrable_domain(row_url)
        snap_dom = registrable_domain(snap_url)
        if snap_dom and row_dom != snap_dom:
            failures.append(
                f"R20 (URL/Snapshot Mismatch in Row #{r_idx}): row cites `{eid}` ({sid}: {snap_url}) "
                f"but links to domain `{row_dom}` ({row_url})."
            )
            continue

        if PLACEHOLDER_CELL_RE.search(quote_cell) or not _quote_in_snapshot(quote_cell, snap_text):
            failures.append(
                f"R20 (Non-Verbatim Ledger Quote in Row #{r_idx}): quote {quote_cell[:70]!r} "
                f"was not found verbatim in `{sid}.txt`."
            )
            continue

        valid_rows += 1

    diag = {
        "present": True,
        "total_rows": len(rows),
        "valid_rows": valid_rows,
        "min_rows": min_rows,
        "passed": not failures,
    }
    return failures, diag


def run_b12_anti_hallucination_filter(
    report_text: str,
    *,
    manifest: dict[str, Any],
    model_env: dict[str, Any],
    verified_evidence_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Enforce Rule B12: Ban Hyperbolic Verdicts, Uncalculated Multipliers & Frequency Guesses."""
    failures: list[str] = []
    warnings: list[str] = []
    prose = strip_non_prose_blocks(report_text)

    verified_quotes: dict[str, str] = {}
    for ev in (manifest.get("evidence") or []):
        if isinstance(ev, dict):
            eid = str(ev.get("id", ""))
            if eid in verified_evidence_ids:
                verified_quotes[eid] = str(ev.get("quote", ""))

    finite_vals = [
        float(v) for v in (model_env or {}).values()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
    ]

    # 1. Hyperbolic marketing verdict check
    for m in HYPERBOLIC_VERDICT_RE.finditer(prose):
        if not is_mitigated_locally(prose, m.start(), terms=LOCAL_REFUTATION_TERMS, window=180):
            failures.append(
                f"B12 (Hyperbolic Verdict Trap): uncalibrated hype label {m.group(0)!r} is forbidden. "
                f"Use calibrated verdicts (`GO`, `CONDITIONAL_GO`, `HOLD`, `NO_GO`, `KILL`) with empirical confidence."
            )

    # 2. Standalone numeric multiplier check (`11.8x`, `10.4x`)
    for m in MULTIPLIER_RE.finditer(prose):
        raw_num = m.group(1)
        try:
            val = float(raw_num)
        except ValueError:
            continue
        if val <= 0.0:
            continue

        after_slice = prose[m.end(): m.end() + 28]
        before_slice = prose[max(0, m.start() - 24): m.start()].lower()
        if BENIGN_MULTIPLIER_AFTER_RE.search(after_slice):
            continue
        if any(tok in before_slice for tok in ("prior=", "prior ", "bm25", "resolution ", "grid ")):
            continue
        # Small integer counts like `1x`, `2x`, `3x` in ordinary prose unless decimal (`11.8x`)
        if "." not in raw_num and val <= 4.0:
            continue
        if is_mitigated_locally(prose, m.start(), terms=LOCAL_REFUTATION_TERMS, window=200):
            continue

        # Check model_env match within rounding tolerance
        tol = max(0.15, 0.02 * abs(val))
        in_model = any(abs(mv - val) <= tol for mv in finite_vals)

        # Or check local verified [E###] quote containing the number
        lo = max(0, m.start() - 240)
        hi = min(len(prose), m.end() + 240)
        local_eids = EID_RE.findall(prose[lo:hi])
        in_quote = any(raw_num in verified_quotes.get(eid, "") for eid in local_eids)

        if not in_model and not in_quote:
            failures.append(
                f"B12 (Uncalculated Multiplier Hallucination): standalone multiplier `{m.group(0)}` "
                f"neither matches any variable in `python:model` (`[C###]`) nor appears in a locally "
                f"cited verified `[E###]` snapshot quote."
            )

    # 3. Empirical event-frequency claim check (`~100-150 occurrences/year`)
    for m in FREQUENCY_CLAIM_RE.finditer(prose):
        if is_mitigated_locally(prose, m.start(), terms=LOCAL_REFUTATION_TERMS, window=220):
            continue
        # Bound region to current paragraph/block so citations in adjacent paragraphs cannot launder guesses
        para_start = prose.rfind("\n\n", 0, m.start())
        para_start = 0 if para_start < 0 else para_start + 2
        para_end = prose.find("\n\n", m.end())
        para_end = len(prose) if para_end < 0 else para_end
        lo = max(para_start, m.start() - 220)
        hi = min(para_end, m.end() + 220)
        region = prose[lo:hi]
        freq_nums = re.findall(r"\d+(?:\.\d+)?", m.group(0))
        local_eids = [e for e in EID_RE.findall(region) if e in verified_evidence_ids]
        local_cids = CID_RE.findall(region)

        backed_by_quote = any(
            any(fn in verified_quotes.get(eid, "") for fn in freq_nums)
            for eid in local_eids
        )
        backed_by_model = bool(local_cids) and any(
            any(abs(mv - float(fn)) <= max(0.5, 0.02 * float(fn)) for mv in finite_vals)
            for fn in freq_nums
        )
        if not backed_by_quote and not backed_by_model:
            failures.append(
                f"B12 (Unbacked Frequency Guess): empirical rate claim {m.group(0)!r} has no locally "
                f"attached snapshot-verified `[E###]` quote or `[C###]` dataset count variable."
            )

    return failures, warnings


def run_v13_gates_fail_closed(
    report_text: str,
    *,
    study_dir: Path | str | None,
    manifest: dict[str, Any],
    sources_index: dict[str, dict[str, Any]],
    source_texts: dict[str, str],
    verified_evidence_ids: set[str],
    model_env: dict[str, Any],
    protocol_active: bool,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Fail-closed wrapper for v13 gates R19, R20, and B12."""
    diag: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION_V13 if protocol_active else "legacy",
        "active": bool(protocol_active),
        "depth": {},
        "ledger": {},
        "passed": False,
    }
    if not protocol_active:
        return [], [
            "W_V13_LEGACY_STUDY: study declares pre-v13 protocol; v13 deep-digging quotas (R19), "
            "Claim-Link-Quote Ledger (R20) and B12 multiplier gates were not enforced. "
            "Pass `--strict-v13` or regenerate spec with `auto_spec.py` v13.0."
        ], diag

    failures: list[str] = []
    warnings: list[str] = []
    try:
        quotas, _ = _resolve_quotas(study_dir, manifest)
        r19_fails, depth_diag = validate_depth_quotas(
            report_text,
            study_dir=study_dir,
            manifest=manifest,
            n_sources=len(sources_index),
            n_verified_evidence=len(verified_evidence_ids),
            model_env=model_env,
        )
        r20_fails, ledger_diag = validate_claim_link_quote_ledger(
            report_text,
            manifest=manifest,
            sources_index=sources_index,
            source_texts=source_texts,
            verified_evidence_ids=verified_evidence_ids,
            min_rows=quotas["min_ledger_rows"],
        )
        b12_fails, b12_warns = run_b12_anti_hallucination_filter(
            report_text,
            manifest=manifest,
            model_env=model_env,
            verified_evidence_ids=verified_evidence_ids,
        )
        failures.extend(r19_fails)
        failures.extend(r20_fails)
        failures.extend(b12_fails)
        warnings.extend(b12_warns)
        diag["depth"] = depth_diag
        diag["ledger"] = ledger_diag
        diag["passed"] = not failures
        if not failures:
            warnings.append(
                f"W_V13_PASS: R19/R20/B12 verified (words={depth_diag['measured']['prose_words']}, "
                f"sources={len(sources_index)}, ledger_rows={ledger_diag['valid_rows']})."
            )
    except Exception as exc:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        failures.append(
            f"B0 (v13 Gate Integrity / FAIL-CLOSED): R19/R20/B12 raised an unexpected "
            f"{type(exc).__name__} ({detail}). Certification refused."
        )
    return failures, warnings, diag


def render_claim_ledger_scaffold() -> str:
    """Canonical Markdown scaffold for Rule R20."""
    return (
        "## Claim-Link-Quote Evidence Ledger\n\n"
        "| Твърдение (Claim) | Източник / Линк (Primary URL) | Дословен цитат от снапшота (Verbatim Quote) | ID |\n"
        "| :-- | :-- | :-- | :-- |\n"
        "| <конкретен проверим факт / число / клауза> | https://example.com/terms | \"<точен дословен цитат от S001.txt>\" | [E001] |\n"
    )


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def write_verification_receipt(
    study_dir: Path | str,
    report_text: str,
    summary: dict[str, Any],
) -> Path:
    """Write `verification_receipt.json` inside `study_dir` when verification passes."""
    sdir = Path(study_dir)
    clean_body = ATTESTATION_MARKER_RE.sub("", report_text).rstrip() + "\n"
    payload = {
        "study_dir": sdir.name,
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "passed": bool(summary.get("passed", False)),
        "protocol_version": str(summary.get("protocol_version", PROTOCOL_VERSION_V13)),
        "body_sha256": _sha256_str(clean_body),
        "ei_score": summary.get("ei_score", 0.0),
        "idi_score": summary.get("idi_score", 0.0),
        "max_confidence": summary.get("max_confidence", "Unverified"),
        "n_sources": summary.get("n_sources", 0),
        "n_evidence": summary.get("n_evidence", 0),
        "neff": summary.get("neff", 0.0),
    }
    receipt_path = sdir / "verification_receipt.json"
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_path


def export_verified_report(
    study_dir: Path | str,
    out_path: Path | str,
    verify_fn: Callable[[Path], Any],
) -> tuple[bool, list[str], Path | None]:
    """Rule R21: Refuse export to `reports/` unless `verify_fn(study_dir)` passes."""
    sdir = Path(study_dir).resolve()
    rep = verify_fn(sdir)
    if not getattr(rep, "passed", False):
        return False, list(getattr(rep, "failures", ["verification failed"])), None

    report_path = sdir / "report.md"
    raw_report = report_path.read_text(encoding="utf-8")
    clean_body = ATTESTATION_MARKER_RE.sub("", raw_report).rstrip() + "\n"
    body_sha = _sha256_str(clean_body)

    att_data = {
        "study_dir": sdir.name,
        "protocol_version": "14.1" if getattr(rep, "v14_protocol_active", False) else (
            PROTOCOL_VERSION_V13 if getattr(rep, "v13_protocol_active", False) else (
                "12.0" if getattr(rep, "v12_protocol_active", False) else "legacy"
            )
        ),
        "body_sha256": body_sha,
        "ei_score": getattr(rep, "epistemic_index", getattr(rep, "ei_score", 0.0)),
        "idi_score": getattr(rep, "information_density_index", getattr(rep, "idi_score", 0.0)),
        "n_sources": getattr(rep, "n_sources", 0),
        "n_evidence": getattr(rep, "n_evidence", 0),
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    write_verification_receipt(
        sdir,
        clean_body,
        {
            **att_data,
            "passed": True,
            "max_confidence": getattr(rep, "max_confidence", ""),
            "neff": getattr(rep, "n_eff_clusters", getattr(rep, "neff", 0.0)),
        },
    )

    footer = (
        "\n\n---\n"
        f"<!-- DR-ATTESTATION: {json.dumps(att_data, ensure_ascii=False)} -->\n"
        f"*Verified by Deep Research Engine ({att_data['protocol_version']}) · "
        f"Study: `{sdir.name}` · Sources: {att_data['n_sources']} · "
        f"Verified Quotes: {att_data['n_evidence']} · EI: {att_data['ei_score']}/100 · "
        f"IDI: {att_data['idi_score']} · SHA-256: `{body_sha[:16]}`*\n"
    )
    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(clean_body + footer, encoding="utf-8")
    return True, [], dest


def audit_deliverables_directory(
    reports_dir: Path | str,
    research_root: Path | str,
    *,
    since_date: str = "2026-11-07",
    check_all: bool = False,
) -> dict[str, Any]:
    """Rule R21 scanner: detect unverified standalone `.md` stubs written into `reports/`."""
    rdir = Path(reports_dir)
    res_root = Path(research_root)
    cutoff = dt.date.fromisoformat(since_date) if since_date and not check_all else None

    checked: list[str] = []
    skipped_legacy: list[str] = []
    violations: list[dict[str, str]] = []
    verified_ok: list[str] = []

    if not rdir.exists():
        return {"passed": True, "checked": 0, "verified": [], "violations": [], "skipped_legacy": []}

    for md_file in sorted(rdir.glob("*.md")):
        name = md_file.name
        if name.startswith(("ENGINE_AUDIT_", "V14_ADVERSARIAL_AUDIT_")):
            continue
        if cutoff is not None:
            mtime_date = dt.date.fromtimestamp(md_file.stat().st_mtime)
            if mtime_date < cutoff:
                skipped_legacy.append(name)
                continue

        checked.append(name)
        txt = md_file.read_text(encoding="utf-8", errors="replace")
        m = ATTESTATION_MARKER_RE.search(txt)
        if not m:
            violations.append({
                "file": name,
                "reason": "R21 (Unverified Deliverable Bypass): missing `DR-ATTESTATION` footer; file was written directly to `reports/` bypassing `lean_engine.py export`.",
            })
            continue

        try:
            att = json.loads(m.group(1))
        except ValueError:
            violations.append({"file": name, "reason": "R21 (Corrupt Attestation JSON)"})
            continue

        clean_body = ATTESTATION_MARKER_RE.sub("", txt).rstrip() + "\n"
        actual_sha = _sha256_str(clean_body)
        if actual_sha != att.get("body_sha256"):
            violations.append({
                "file": name,
                "reason": f"R21 (Post-Verification Tampering): body SHA-256 `{actual_sha[:12]}` != attested `{str(att.get('body_sha256'))[:12]}`.",
            })
            continue

        study_slug = str(att.get("study_dir", ""))
        receipt_p = res_root / study_slug / "verification_receipt.json"
        if not study_slug or not receipt_p.exists():
            violations.append({
                "file": name,
                "reason": f"R21 (Missing Study Receipt): `research/{study_slug}/verification_receipt.json` not found.",
            })
            continue

        try:
            receipt = json.loads(receipt_p.read_text(encoding="utf-8"))
        except ValueError:
            violations.append({"file": name, "reason": "R21 (Unreadable Study Receipt)"})
            continue

        if not receipt.get("passed") or receipt.get("body_sha256") != actual_sha:
            violations.append({
                "file": name,
                "reason": "R21 (Receipt Mismatch): study receipt either did not pass or hashes diverged.",
            })
            continue

        verified_ok.append(name)

    return {
        "passed": len(violations) == 0,
        "checked": len(checked),
        "verified": verified_ok,
        "violations": violations,
        "skipped_legacy": skipped_legacy,
    }


def _selftest() -> int:
    # 1. Version parsing
    assert version_at_least("13.0", 13, 0)
    assert version_at_least("13.0", 12, 0)
    assert not version_at_least("12.0", 13, 0)
    assert parse_protocol_version(None) == (0, 0)

    # 2. Catch RP52H / RP52E style hallucinations with B12
    rp52_stub = (
        "# RP52H Stub\nStatus: MAXIMUM CONVICTION GO\n"
        "| Firm | Cash/Fee |\n| :-- | :-- |\n| Fintokei | 11.8x |\n"
        "Event frequency: ~100-150 occurrences/year.\n"
    )
    b12_f, _ = run_b12_anti_hallucination_filter(
        rp52_stub, manifest={"evidence": []}, model_env={"fee_usd": 549.0}, verified_evidence_ids=set()
    )
    assert any("Hyperbolic Verdict" in x for x in b12_f), b12_f
    assert any("Uncalculated Multiplier" in x for x in b12_f), b12_f
    assert any("Unbacked Frequency" in x for x in b12_f), b12_f

    # 3. Verify calibrated multiplier + ATR technical text passes B12
    clean_prose = (
        "Stop is 1.5 × ATR and target is 2.5x ATR. "
        "Computed expected cash-to-fee ratio is 11.8x [C001]. "
        "Historical count is 108 occurrences/year [E001]."
    )
    b12_ok, _ = run_b12_anti_hallucination_filter(
        clean_prose,
        manifest={"evidence": [{"id": "E001", "quote": "108 occurrences/year observed"}]},
        model_env={"cash_to_fee_mult": 11.82},
        verified_evidence_ids={"E001"},
    )
    assert not b12_ok, b12_ok

    # 4. Verify R20 Claim-Link-Quote Ledger validation
    ledger_md = (
        "## Claim-Link-Quote Ledger\n\n"
        "| Твърдение | Линк | Дословен цитат | ID |\n"
        "| :-- | :-- | :-- | :-- |\n"
        "| Fintokei 100K струва $549 | https://www.fintokei.com/protrader | \"USD 100,000 ProTrader fee is $549\" | [E001] |\n"
    )
    f_r20, d_r20 = validate_claim_link_quote_ledger(
        ledger_md,
        manifest={"evidence": [{"id": "E001", "source": "S001", "quote": "USD 100,000 ProTrader fee is $549"}]},
        sources_index={"S001": {"id": "S001", "url": "https://www.fintokei.com/protrader/"}},
        source_texts={"S001": "Pricing table: USD 100,000 ProTrader fee is $549 one-time."},
        verified_evidence_ids={"E001"},
        min_rows=1,
    )
    assert not f_r20 and d_r20["valid_rows"] == 1, f_r20

    print("[SELFTEST PASS] depth_and_ledger_gate v13.0 (R19 + R20 + R21 + B12) verified.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
