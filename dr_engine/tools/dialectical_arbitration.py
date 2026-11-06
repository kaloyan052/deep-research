#!/usr/bin/env python3
"""Deep Research Engine v11.0 — De Jure vs. De Facto Dialectical Arbitration.

The hardest failure mode in institutional research is not a fabricated quote;
it is a **true but scoped** Tier-1 statement (a statute, a patent, a paper's
theoretical result) contradicted by a Tier-3 practitioner postmortem proving
the edge dies in production. v10.0 had no representation for this, so an LLM
could simply average the two into a comfortable "moderate confidence" number.

This module formalises **Rule B10 / the Dialectical Reconciliation Matrix**:

  1. Detect a de_jure / de_facto contradiction keyed on the same ``subject``.
  2. **Forbid simple averaging** across authority tiers (hard failure).
  3. Mechanically classify the delta into one of three axes:
       ``implementation_drag``                    (engineering / latency / ops)
       ``undisclosed_microstructure_friction``   (spread / fees / queue / fill)
       ``regulatory_enforcement_asymmetry``      (enforcement / discretion)
  4. Cap overall confidence at **Medium** until an explicit verification record
     exists; an unclassified or unreconciled delta is a hard failure.

NOTE: this is deliberately a *different* module from the pre-existing
``dialectics.py`` (v5.0 claim-ledger CLI + DerSimonian-Laird I²). B10 operates
on the v9/v10 ``json:manifest`` evidence records and complements, rather than
replaces, the older claims.jsonl regime-partitioning workflow.

Pure Python 3.10+ stdlib. Deterministic. Windows cp1252-safe.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "ALLOWED_DELTA_AXES", "AXIS_MARKERS", "AVERAGING_RE",
    "epistemic_mode", "detect_dejure_defacto_conflicts", "classify_delta",
    "reconciliation_matrix", "run_b10_dialectical_arbitration",
]

ALLOWED_DELTA_AXES = (
    "implementation_drag",
    "undisclosed_microstructure_friction",
    "regulatory_enforcement_asymmetry",
)

DE_JURE_KINDS = frozenset({
    "de_jure", "statute", "regulation", "patent", "academic", "paper",
    "peer_reviewed", "theoretical", "whitepaper", "official", "normative",
})
DE_JURE_PROVES = frozenset({
    "theoretical_validity", "legal_authority", "de_jure_rule",
    "normative_validity", "mechanism_hypothesis",
})
DE_FACTO_KINDS = frozenset({
    "de_facto", "practitioner_postmortem", "practitioner_trench", "review_pain",
    "github_issue", "forum_post", "production_report", "incident_report",
    "empirical_field", "operational_reality",
})
DE_FACTO_PROVES = frozenset({
    "operational_reality", "incumbent_weakness", "production_failure",
    "operational_failure", "implementation_drag", "postmortem",
})
DISCONFIRMING_STANCES = frozenset({"contradicts", "refutes", "disconfirms", "kills"})

# Averaging across authority tiers is epistemically invalid: the two claims are
# not samples from one population, so no pooled estimator is defined.
AVERAGING_RE = re.compile(
    r"\b(?:averag(?:e|ed|ing)|pool(?:ed|ing)|mean estimate|weighted mean|"
    r"combined estimate|meta[- ]analytic|random[- ]effects|on balance|"
    r"split the difference|somewhere between)\b",
    re.I,
)

AXIS_MARKERS: dict[str, re.Pattern[str]] = {
    "implementation_drag": re.compile(
        r"\b(?:implementation|engineering|latency|throughput|deployment|"
        r"integration|bug|crash|timeout|rollout|scalability|ops|runtime|"
        r"memory|concurrency|retries?|off[- ]by[- ]one)\w*\b", re.I),
    "undisclosed_microstructure_friction": re.compile(
        r"\b(?:spread|slippage|fee|commission|friction|queue|fill|adverse selection|"
        r"market impact|basis|liquidity|capacity|hidden cost|haircut|"
        r"bid[- ]ask|tick size)\w*\b", re.I),
    "regulatory_enforcement_asymmetry": re.compile(
        r"\b(?:enforcement|regulator|court|guidance|discretion|exemption|"
        r"licen[cs]e|sanction|interpretation|not enforced|in practice|"
        r"supervisory|grandfather|carve[- ]out|waiver)\w*\b", re.I),
}

_PROSE_STRIP_RE = re.compile(r"```.*?```", re.S)


def _norm_subject(value: Any) -> str:
    s = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", s)[:120]


def epistemic_mode(ev: dict[str, Any]) -> str | None:
    """Classify one evidence record as ``de_jure`` / ``de_facto`` / unknown.

    An explicit ``epistemic_mode`` field always wins. Otherwise the decision
    uses authority tier PLUS kind/proves semantics, so a T1 source is never
    assumed de_jure merely because it is authoritative.
    """
    if not isinstance(ev, dict):
        return None
    explicit = str(ev.get("epistemic_mode", "")).strip().lower()
    if explicit in ("de_jure", "de_facto"):
        return explicit
    tier = str(ev.get("tier", "")).strip().upper()
    kind = str(ev.get("kind", "")).strip().lower()
    proves = str(ev.get("proves", "")).strip().lower()
    if tier in ("T1", "T2") and (kind in DE_JURE_KINDS or proves in DE_JURE_PROVES
                                 or ev.get("authority_tier")):
        return "de_jure"
    if tier in ("T3", "T4", "T5") and (kind in DE_FACTO_KINDS or proves in DE_FACTO_PROVES):
        return "de_facto"
    return None


def detect_dejure_defacto_conflicts(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one conflict record per subject with a de_jure/de_facto contradiction.

    A conflict requires:
      * at least one de_jure record with a supporting stance;
      * at least one de_facto record with a disconfirming stance OR an explicit
        failure ``proves`` value;
      * matching subjects (or both unscoped). Differently-scoped subjects are
        NOT conflated -- that would recreate the scope-distortion error the
        blind claim audit exists to catch.
    """
    if not isinstance(evidence, list):
        return []
    de_jure: dict[str, list[dict[str, Any]]] = {}
    de_facto: dict[str, list[dict[str, Any]]] = {}
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        mode = epistemic_mode(ev)
        if mode is None:
            continue
        subject = _norm_subject(ev.get("subject") or ev.get("claim_key") or "")
        stance = str(ev.get("stance", "")).strip().lower()
        proves = str(ev.get("proves", "")).strip().lower()
        if mode == "de_jure" and stance in ("supports", "confirms", ""):
            de_jure.setdefault(subject, []).append(ev)
        elif mode == "de_facto" and (
            stance in DISCONFIRMING_STANCES or proves in DE_FACTO_PROVES
        ):
            de_facto.setdefault(subject, []).append(ev)

    conflicts: list[dict[str, Any]] = []
    for subject, dj in de_jure.items():
        candidates: list[dict[str, Any]] = []
        if subject:
            candidates.extend(de_facto.get(subject, []))
            candidates.extend(de_facto.get("", []))
        else:
            for group in de_facto.values():
                candidates.extend(group)
        if not candidates:
            continue
        seen: set[str] = set()
        unique_df = []
        for ev in candidates:
            key = str(ev.get("id") or id(ev))
            if key not in seen:
                seen.add(key)
                unique_df.append(ev)
        conflicts.append({
            "subject": subject or "(unscoped)",
            "de_jure_ids": [str(e.get("id", "")) for e in dj],
            "de_facto_ids": [str(e.get("id", "")) for e in unique_df],
            "de_jure_quotes": [str(e.get("quote", "")) for e in dj],
            "de_facto_quotes": [str(e.get("quote", "")) for e in unique_df],
        })
    return conflicts


def classify_delta(conflict: dict[str, Any], report_text: str) -> dict[str, Any]:
    """Mechanically classify the delta into one allowed axis.

    Scoring is lexical and fully reproducible: de_facto quotes carry 3x weight
    (they describe the observed failure), de_jure quotes 1x, and report prose
    near the subject 1x. Ties and zero-signal cases return ``unclassified``,
    which is a HARD FAILURE -- the engine never guesses an axis.
    """
    prose = _PROSE_STRIP_RE.sub(" ", report_text)
    subject = conflict.get("subject", "")
    context = prose
    if subject and subject != "(unscoped)":
        pos = prose.lower().find(subject.lower())
        if pos >= 0:
            context = prose[max(0, pos - 400): pos + 600]
    scores: dict[str, int] = {axis: 0 for axis in ALLOWED_DELTA_AXES}
    for quote in conflict.get("de_facto_quotes", []):
        for axis, pattern in AXIS_MARKERS.items():
            scores[axis] += 3 * len(pattern.findall(str(quote)))
    for quote in conflict.get("de_jure_quotes", []):
        for axis, pattern in AXIS_MARKERS.items():
            scores[axis] += len(pattern.findall(str(quote)))
    for axis, pattern in AXIS_MARKERS.items():
        scores[axis] += len(pattern.findall(context))
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best, best_score = ranked[0]
    if best_score <= 0 or (len(ranked) > 1 and ranked[1][1] == best_score):
        return {"axis": "unclassified", "scores": scores, "evidence": "no unique dominant axis"}
    return {"axis": best, "scores": scores, "evidence": f"dominant marker count {best_score}"}


def _reconciliation_lookup(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = manifest.get("dialectics") or []
    if not isinstance(entries, list):
        return {}
    return {
        _norm_subject(e.get("subject")): e
        for e in entries if isinstance(e, dict)
    }


def reconciliation_matrix(
    conflicts: list[dict[str, Any]],
    report_text: str,
    manifest: dict[str, Any],
    pooled_subjects: list[str] | None = None,
) -> dict[str, Any]:
    """Build the full Dialectical Reconciliation Matrix (B10)."""
    lookup = _reconciliation_lookup(manifest)
    prose = _PROSE_STRIP_RE.sub(" ", report_text)
    pooled = {_norm_subject(s) for s in (pooled_subjects or [])}
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []
    axis_counts: dict[str, int] = {axis: 0 for axis in ALLOWED_DELTA_AXES}
    axis_counts["unclassified"] = 0

    for conflict in conflicts:
        subject = conflict["subject"]
        classified = classify_delta(conflict, prose)
        entry = lookup.get(subject if subject != "(unscoped)" else "", {})
        declared_axis = str(entry.get("axis", "")).strip().lower()
        if declared_axis in ALLOWED_DELTA_AXES:
            axis = declared_axis
            axis_source = "manifest.dialectics (structured)"
        else:
            axis = classified["axis"]
            axis_source = "mechanical lexical classification"
        axis_counts[axis] = axis_counts.get(axis, 0) + 1

        # 1. Forbid averaging across authority tiers.
        averaging_hits = list(AVERAGING_RE.finditer(prose))
        # Conservative default: any averaging language in a report that has a
        # de_jure/de_facto contradiction is forbidden. When the subject is
        # explicitly present, refine to a 500-character local window.
        local_averaging = bool(averaging_hits)
        if subject and subject != "(unscoped)":
            pos = prose.lower().find(subject.lower())
            if pos >= 0:
                local_averaging = any(abs(m.start() - pos) <= 500 for m in averaging_hits)
        pooled_this_subject = subject in pooled
        if local_averaging or pooled_this_subject:
            failures.append(
                f"B10 (Forbidden Averaging): de_jure/de_facto contradiction on "
                f"{subject!r} must NOT be averaged or pooled "
                f"({'pooled estimator detected' if pooled_this_subject else 'averaging language detected'}); "
                f"the two claims are not samples from one population"
            )

        # 2. Classification and reconciliation are mandatory.
        if axis == "unclassified":
            failures.append(
                f"B10 (Unclassified Dialectical Delta): contradiction on {subject!r} "
                f"could not be classified into {list(ALLOWED_DELTA_AXES)}. "
                f"Declare `manifest.dialectics[].axis` with supporting evidence."
            )
        if not entry:
            failures.append(
                f"B10 (Unreconciled De Jure/De Facto Conflict): {subject!r} has "
                f"de_jure {conflict['de_jure_ids']} vs de_facto {conflict['de_facto_ids']} "
                f"but no `manifest.dialectics` reconciliation entry"
            )

        verification = entry.get("verification") or {}
        verified = str(verification.get("status", "")).strip().lower() == "verified"
        rows.append({
            "subject": subject,
            "de_jure_ids": conflict["de_jure_ids"],
            "de_facto_ids": conflict["de_facto_ids"],
            "axis": axis,
            "axis_source": axis_source,
            "axis_scores": classified["scores"],
            "averaging_forbidden": bool(local_averaging or pooled_this_subject),
            "reconciled": bool(entry),
            "resolution": str(entry.get("resolution", "")),
            "verification_required": not verified,
            "verified": verified,
            "confidence_cap": None if verified else "Medium",
        })
        if entry and not verified:
            warnings.append(
                f"W_B10: de_jure/de_facto delta on {subject!r} classified as {axis}; "
                "overall confidence capped at Medium until verification is recorded"
            )

    caps = {r["confidence_cap"] for r in rows if r["confidence_cap"]}
    return {
        "conflicts_detected": len(conflicts),
        "rows": rows,
        "axis_counts": axis_counts,
        "confidence_cap": "Medium" if caps else None,
        "verification_required": any(r["verification_required"] for r in rows),
        "averaging_forbidden": any(r["averaging_forbidden"] for r in rows),
        "failures": failures,
        "warnings": warnings,
    }


def run_b10_dialectical_arbitration(
    report_text: str,
    manifest: dict[str, Any],
    model_env: dict[str, Any] | None = None,
    verified_evidence_ids: set[str] | None = None,
    pooled_subjects: list[str] | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Public B10 entry point: ``(failures, warnings, arbitration_matrix)``.

    When ``verified_evidence_ids`` is supplied, only evidence whose quotes were
    already validated against immutable snapshots participates -- so a
    self-declared manifest cannot manufacture a dialectical conflict (or erase
    a real one).
    """
    if not isinstance(manifest, dict):
        return [], [], {"conflicts_detected": 0, "rows": []}
    raw_evidence = manifest.get("evidence") or []
    if not isinstance(raw_evidence, list):
        raw_evidence = []
    evidence = [
        ev for ev in raw_evidence
        if isinstance(ev, dict)
        and (verified_evidence_ids is None or str(ev.get("id", "")) in verified_evidence_ids)
    ]
    conflicts = detect_dejure_defacto_conflicts(evidence)
    if not conflicts:
        matrix = {
            "conflicts_detected": 0, "rows": [], "axis_counts": {},
            "confidence_cap": None, "verification_required": False,
            "averaging_forbidden": False, "failures": [], "warnings": [],
        }
        return [], [], matrix
    matrix = reconciliation_matrix(conflicts, report_text, manifest, pooled_subjects)
    return list(matrix["failures"]), list(matrix["warnings"]), matrix


def _selftest() -> int:
    manifest = {
        "domain": "quant",
        "evidence": [
            {"id": "E001", "tier": "T1", "kind": "academic", "stance": "supports",
             "subject": "0dte_gamma_edge", "epistemic_mode": "de_jure",
             "quote": "Theoretical model predicts positive expectancy under frictionless execution."},
            {"id": "E002", "tier": "T5", "kind": "practitioner_postmortem",
             "stance": "contradicts", "subject": "0dte_gamma_edge",
             "epistemic_mode": "de_facto",
             "quote": "In production the spread widened and slippage ate the edge; the fill rate collapsed."},
        ],
        "dialectics": [{
            "subject": "0dte_gamma_edge",
            "axis": "undisclosed_microstructure_friction",
            "resolution": "Re-run with measured round-turn friction and queue priority.",
            "verification": {"status": "pending"},
        }],
    }
    clean = "We reject the frictionless theoretical result [E001] given measured execution [E002]."
    fails, warns, matrix = run_b10_dialectical_arbitration(clean, manifest)
    assert not fails, f"unexpected failures: {fails}"
    assert matrix["conflicts_detected"] == 1
    assert matrix["rows"][0]["axis"] == "undisclosed_microstructure_friction"
    assert matrix["confidence_cap"] == "Medium"
    assert warns and matrix["verification_required"]

    averaged = "On average the edge is mildly positive, pooling [E001] and [E002]."
    f_avg, _, _ = run_b10_dialectical_arbitration(averaged, manifest)
    assert any("B10 (Forbidden Averaging)" in f for f in f_avg)

    no_entry = dict(manifest)
    no_entry.pop("dialectics")
    f_none, _, _ = run_b10_dialectical_arbitration(clean, no_entry)
    assert any("B10 (Unreconciled" in f for f in f_none)

    verified = dict(manifest)
    verified["dialectics"] = [dict(manifest["dialectics"][0],
                                   verification={"status": "verified", "method": "live A/B"})]
    f_v, _, m_v = run_b10_dialectical_arbitration(clean, verified)
    assert not f_v and m_v["confidence_cap"] is None

    scoped = dict(manifest)
    scoped["evidence"] = [manifest["evidence"][0],
                          dict(manifest["evidence"][1], subject="unrelated_topic")]
    assert detect_dejure_defacto_conflicts(scoped["evidence"]) == []

    _, _, m_filtered = run_b10_dialectical_arbitration(
        clean, manifest, verified_evidence_ids={"E001"})
    assert m_filtered["conflicts_detected"] == 0

    # A pooled DerSimonian-Laird estimator on the conflicting subject fails.
    f_pool, _, _ = run_b10_dialectical_arbitration(
        clean, manifest, pooled_subjects=["0dte_gamma_edge"])
    assert any("B10 (Forbidden Averaging)" in f for f in f_pool)

    print("[SELFTEST PASS] dialectical_arbitration v11.0 (B10 matrix / no averaging / Medium cap) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
