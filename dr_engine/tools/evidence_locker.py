#!/usr/bin/env python3
"""Deep Research Engine v14.0 — Pre-Synthesis Evidence Locker.

Eliminates the "Semantic Illusion / Hallucinated Citation" failure mode.
In previous versions, agents drafted report.md from memory, hallucinating quotes
and institutions (e.g. BIS/CFTC talking about R-multiples), only to fail at gate verification.

The Pre-Synthesis Evidence Locker mandates:
  1. All quotes MUST be locked into `evidence_ledger.json` and `evidence_pack.md`
     BEFORE authoring `report.md`.
  2. Every locked quote is verified verbatim against downloaded snapshots in `sources/S###.txt`.
  3. Authoring tools and verification gates reject any citation not in the locked ledger.

Stdlib only. Windows cp1252-safe.
"""

from __future__ import annotations

import argparse
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

from dr_engine.tools.lean_engine import quote_matches_snapshot, normalise_ws

__all__ = [
    "lock_evidence",
    "load_locked_evidence",
    "extract_candidate_quotes",
    "build_evidence_pack_markdown",
]


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
            except Exception:
                pass

    return sources_meta, source_texts


def lock_evidence(
    study_dir: Path,
    evidence_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Verifies candidate evidence items against snapshots and locks them to evidence_ledger.json.
    
    Returns (locked_items, errors).
    """
    sources_meta, source_texts = load_snapshots(study_dir)
    locked: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, item in enumerate(evidence_items, 1):
        eid = item.get("id") or f"E{idx:03d}"
        sid = item.get("source") or item.get("sid", "")
        quote = item.get("quote", "").strip()
        tier = item.get("tier", "T1")

        if not quote:
            errors.append(f"{eid}: empty quote string")
            continue

        if sid not in source_texts:
            errors.append(f"{eid}: source {sid} not found in snapshots (available: {list(source_texts.keys())})")
            continue

        snap_text = source_texts[sid]
        if not quote_matches_snapshot(quote, snap_text):
            errors.append(f"{eid}: quote does not match snapshot {sid}.txt verbatim: {quote[:60]!r}")
            continue

        meta = sources_meta.get(sid, {})
        locked_record = {
            "id": eid,
            "source": sid,
            "source_url": meta.get("url", ""),
            "title": meta.get("title", ""),
            "tier": tier,
            "quote": quote,
            "char_len": len(quote),
        }
        locked.append(locked_record)

    if locked and not errors:
        # Write to evidence_ledger.json
        out_json = study_dir / "evidence_ledger.json"
        out_json.write_text(json.dumps(locked, indent=2, ensure_ascii=False), encoding="utf-8")

        # Write human-readable evidence_pack.md
        pack_md = build_evidence_pack_markdown(locked)
        out_pack = study_dir / "evidence_pack.md"
        out_pack.write_text(pack_md, encoding="utf-8")

    return locked, errors


def build_evidence_pack_markdown(locked_items: list[dict[str, Any]]) -> str:
    """Builds markdown ledger ready for direct inclusion or reference by report authors."""
    lines = [
        "# Pre-Locked Evidence Pack (Deep Research v14.0)",
        "",
        "> [!IMPORTANT]",
        "> When authoring `report.md`, cite ONLY quotes from this pre-locked evidence pack.",
        "> Every quote below has been mechanically verified against its primary snapshot.",
        "",
        "| ID | Source | Tier | Verbatim Quote | URL |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for item in locked_items:
        eid = item["id"]
        sid = item["source"]
        tier = item.get("tier", "T1")
        quote = item["quote"].replace("|", "\\|")
        url = item.get("source_url", "")
        lines.append(f"| `[{eid}]` | `{sid}` | {tier} | {quote} | [{sid}]({url}) |")

    lines.append("")
    return "\n".join(lines)


def load_locked_evidence(study_dir: Path) -> list[dict[str, Any]]:
    """Loads locked evidence ledger if present."""
    p = study_dir / "evidence_ledger.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
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
            if len(s_clean) < 30 or len(s_clean) > 300:
                continue
            if any(k.lower() in s_clean.lower() for k in keywords):
                candidates.append({
                    "source": sid,
                    "quote": s_clean,
                    "tier": "T1" if "nber" in sources_meta.get(sid, {}).get("url", "") or "edu" in sources_meta.get(sid, {}).get("url", "") else "T2",
                })
    return candidates


if __name__ == "__main__":
    study = Path("research/2026-11-08-rp53k-process-and-battery")
    if study.exists():
        # Test locking existing RP53K verified quotes
        manifest_p = study / "report.md"
        if manifest_p.exists():
            import re
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
