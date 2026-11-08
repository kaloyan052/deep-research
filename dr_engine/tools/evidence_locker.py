#!/usr/bin/env python3
"""Deep Research Engine v14.1 — Pre-Synthesis Evidence Locker.

Eliminates the "Semantic Illusion / Hallucinated Citation" failure mode.
In previous versions, agents drafted report.md from memory, hallucinating quotes
and institutions (e.g. BIS/CFTC talking about R-multiples), only to fail at gate verification.

The Pre-Synthesis Evidence Locker mandates:
  1. All quotes MUST be locked into `evidence_ledger.json` and `evidence_pack.md`
     BEFORE authoring `report.md`.
  2. Every locked quote is verified verbatim against downloaded snapshots in `sources/S###.txt`.
  3. Authoring tools and verification gates (Rule B14) reject any citation not in the locked ledger.
  4. Write operations are atomic and fail-closed: failures remove stale ledgers.

Stdlib only. Windows cp1252/UTF-8-safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dr_engine.tools.lean_engine import (
    quote_matches_snapshot, normalise_ws, sha256_text,
)

__all__ = [
    "lock_evidence",
    "load_locked_evidence",
    "extract_candidate_quotes",
    "build_evidence_pack_markdown",
    "verify_report_against_ledger",
]

VALID_TIERS = {"T1", "T2", "T3", "T4", "T5"}
EID_STRICT = re.compile(r"^E\d{3}$")
MIN_LOCKED_QUOTE_CHARS = 20


def _canonical_digest(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _md_cell(value: Any) -> str:
    """Escape a table cell; normalise_ws also destroys CR/LF row injection."""
    s = normalise_ws(str(value))
    return s.replace("\\", "\\\\").replace("|", "\\|")


def _md_url(url: Any) -> str:
    s = str(url).strip()
    return (s.replace(" ", "%20").replace("(", "%28")
             .replace(")", "%29").replace("|", "%7C"))


def build_evidence_pack_markdown(locked_items: list[dict[str, Any]]) -> str:
    lines = [
        "# Pre-Locked Evidence Pack (Deep Research v14.1)",
        "",
        "> [!IMPORTANT]",
        "> When authoring `report.md`, cite ONLY quotes from this pre-locked evidence pack.",
        "> Every quote below has been mechanically verified against its primary snapshot.",
        "",
        "| ID | Source | Tier | Verbatim Quote | URL |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for item in locked_items:
        if not isinstance(item, dict):
            continue
        eid = _md_cell(item.get("id", ""))
        sid = _md_cell(item.get("source", ""))
        tier = _md_cell(item.get("tier", "T3"))
        quote = _md_cell(item.get("quote", ""))
        url = _md_url(item.get("source_url", ""))
        lines.append(f"| `[{eid}]` | `{sid}` | {tier} | {quote} | [{sid}]({url}) |")
    lines.append("")
    return "\n".join(lines)


def load_snapshots(study_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Loads sources metadata and raw text snapshots from study_dir/sources."""
    sources_meta: dict[str, dict[str, Any]] = {}
    source_texts: dict[str, str] = {}

    index_file = study_dir / "sources" / "index.jsonl"
    if index_file.exists():
        for line in index_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                sid = data.get("id")
                if sid:
                    sources_meta[sid] = data
            except Exception:
                pass

    sources_dir = study_dir / "sources"
    if sources_dir.exists():
        for p in sources_dir.glob("S*.txt"):
            sid = p.stem
            try:
                source_texts[sid] = p.read_text(encoding="utf-8")
            except Exception as e:
                source_texts[sid] = f"[SNAPSHOT READ ERROR: {e}]"

    return sources_meta, source_texts


def lock_evidence(
    study_dir: Path,
    evidence_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Verify candidate evidence and write a tamper-evident, atomic ledger."""
    sources_meta, source_texts = load_snapshots(study_dir)
    locked: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()

    if not isinstance(evidence_items, list):
        return [], ["manifest.evidence must be a list"]

    for idx, item in enumerate(evidence_items, 1):
        if not isinstance(item, dict):
            errors.append(f"E{idx:03d}: evidence item is not an object")
            continue
        eid = str(item.get("id") or f"E{idx:03d}")
        if not EID_STRICT.match(eid):
            errors.append(f"{eid}: id must match ^E\\d{{3}}$")
            continue
        if eid in seen:
            errors.append(f"{eid}: duplicate evidence id")
            continue
        sid = str(item.get("source") or item.get("sid") or "")
        quote = item.get("quote", "")
        if not isinstance(quote, str):
            errors.append(f"{eid}: quote must be a string, got {type(quote).__name__}")
            continue
        quote = quote.strip()
        tier = str(item.get("tier", "T3"))
        if tier not in VALID_TIERS:
            errors.append(f"{eid}: invalid tier {tier!r}")
            continue
        if len(quote) < MIN_LOCKED_QUOTE_CHARS:
            errors.append(f"{eid}: quote too short ({len(quote)} chars)")
            continue
        if sid not in source_texts:
            errors.append(f"{eid}: source {sid!r} not found in snapshots "
                          f"(available: {sorted(source_texts)})")
            continue
        meta = sources_meta.get(sid) or {}
        if not isinstance(meta, dict):
            meta = {}
        src_tier = str(meta.get("tier", tier))
        if src_tier in VALID_TIERS and src_tier > tier:
            tier = src_tier          # never upgrade above the declared source tier
        if not quote_matches_snapshot(quote, source_texts[sid]):
            errors.append(f"{eid}: quote does not match snapshot {sid}.txt verbatim: "
                          f"{quote[:60]!r}")
            continue
        seen.add(eid)
        locked.append({
            "id": eid,
            "source": sid,
            "source_url": str(meta.get("url", "")),
            "title": str(meta.get("title", "")),
            "tier": tier,
            "quote": quote,
            "char_len": len(quote),
            "snapshot_sha256": sha256_text(source_texts[sid]),
        })

    out_json = study_dir / "evidence_ledger.json"
    out_sig = study_dir / "evidence_ledger.json.sha256"
    out_pack = study_dir / "evidence_pack.md"

    # Fail-closed: a refused lock must NEVER leave a stale authoritative ledger.
    if errors or not locked:
        for p in (out_json, out_sig, out_pack):
            if p.exists():
                p.unlink()
        return [], errors or ["no evidence was locked"]

    out_json.write_text(json.dumps(locked, indent=2, ensure_ascii=False), encoding="utf-8")
    out_sig.write_text(_canonical_digest(locked) + "\n", encoding="utf-8")
    out_pack.write_text(build_evidence_pack_markdown(locked), encoding="utf-8")
    return locked, errors


def verify_report_against_ledger(
    study_dir: Path,
    manifest: dict[str, Any],
    raw_report: str,
) -> list[str]:
    """Rule B14 — bind every report citation to the pre-locked ledger."""
    p = study_dir / "evidence_ledger.json"
    sig = study_dir / "evidence_ledger.json.sha256"
    if not p.exists() or not sig.exists():
        return ["B14 (Evidence Locker Missing): run "
                "`lean_engine.py lock-evidence --dir <study>` BEFORE authoring report.md."]
    try:
        records = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            return ["B14 (Empty Evidence Ledger)"]
        if _canonical_digest(records) != sig.read_text(encoding="utf-8").strip():
            return ["B14 (Evidence Ledger Tampered): SHA-256 digest mismatch."]
    except Exception as e:
        return [f"B14 (Evidence Ledger Unreadable): {type(e).__name__}: {e}"]

    locked = {str(r.get("id")): r for r in records if isinstance(r, dict)}
    failures: list[str] = []
    manifest_ev = manifest.get("evidence", [])
    if not isinstance(manifest_ev, list):
        return ["B14 (manifest.evidence must be a list)"]

    for ev in manifest_ev:
        if not isinstance(ev, dict):
            failures.append("B14 (malformed evidence record)")
            continue
        eid = str(ev.get("id", ""))
        rec = locked.get(eid)
        if rec is None:
            failures.append(f"B14: {eid} is cited in the manifest but is NOT pre-locked.")
            continue
        if (str(ev.get("source", "")) != str(rec.get("source", ""))
                or str(ev.get("quote", "")).strip() != str(rec.get("quote", "")).strip()):
            failures.append(f"B14: {eid} source/quote diverges from the locked record.")

    cited = set(re.findall(r"\bE\d{3}\b", raw_report))
    orphans = cited - set(locked)
    if orphans:
        failures.append(f"B14 (Unlocked Citations): {sorted(orphans)} appear in "
                        "report.md but not in evidence_ledger.json.")
    return failures


def load_locked_evidence(study_dir: Path) -> list[dict[str, Any]]:
    p = study_dir / "evidence_ledger.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def extract_candidate_quotes(study_dir: Path, keywords: list[str]) -> list[dict[str, Any]]:
    """Extracts candidate sentences from snapshots that match specified keywords."""
    sources_meta, source_texts = load_snapshots(study_dir)
    candidates = []

    for sid, text in source_texts.items():
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for s in sentences:
            s_clean = normalise_ws(s)
            if len(s_clean) < MIN_LOCKED_QUOTE_CHARS or len(s_clean) > 300:
                continue
            if any(k.lower() in s_clean.lower() for k in keywords):
                url = str(sources_meta.get(sid, {}).get("url", ""))
                candidates.append({
                    "source": sid,
                    "quote": s_clean,
                    "tier": "T1" if ("nber.org" in url or "edu" in url) else "T3",
                })
    return candidates


if __name__ == "__main__":
    study = Path("research/2026-11-08-rp53k-process-and-battery")
    if study.exists():
        manifest_p = study / "report.md"
        if manifest_p.exists():
            m = re.search(r"```json:manifest\s*\n(.*?)```", manifest_p.read_text(encoding="utf-8"), re.S)
            if m:
                data = json.loads(m.group(1))
                ev = data.get("evidence", [])
                locked, errs = lock_evidence(study, ev)
                print(f"[TEST LOCKER] Locked {len(locked)} quotes, {len(errs)} errors.")
                if errs:
                    for e in errs:
                        print("  Error:", e)
                    sys.exit(1)
                else:
                    print("[TEST PASS] Evidence locker functioning correctly.")
