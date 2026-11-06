#!/usr/bin/env python3
"""Deep Research Engine v10.0 — Fail-Closed Epistemic Guard.

Audit finding A1/A2 (v9.0):

  * ``lean_engine.verify_study`` wrapped the entire B1-B9 filter call in
    ``except Exception: res.warnings.append(...)``. Because ``res.passed`` is
    ``len(failures) == 0``, **any** exception (a malformed ``sample_end_year``,
    a ``NaN`` in ``model_env``, an unexpected manifest type) silently disabled
    all nine filters while the study still passed with ``High`` confidence.
  * Every mitigating keyword was tested against the *whole report*: one
    ``"avoid"``, ``"refuted"``, ``"decayed"``, ``"treaty"``, ``"scope"`` or
    ``"n=30"`` in an unrelated appendix disarmed B2, B3, B7, R8, R11 and B1.
  * ``float('nan') > 0.95`` is False and ``nan <= 0.0`` is False, so a NaN
    thermodynamic headroom passed B8.

This module supplies three things:

  1. :func:`is_mitigated_locally` / :func:`unmitigated_spans` -- a disclaimer
     only counts when it is attached to the triggering claim (bounded character
     window AND at most one intervening sentence boundary).
  2. :func:`validate_inputs` -- finite-only numeric coercion and structured
     pre-flight rejection of malformed manifest fields, so filters never see a
     value that can raise.
  3. :func:`run_filters_fail_closed` -- the only sanctioned entry point for the
     verification stage. An unevaluable filter is a **hard failure** (rule B0),
     never a warning.

Pure Python 3.10+ standard library. Windows cp1252-safe.
"""

from __future__ import annotations

import math
import re
import traceback
from typing import Any, Callable

__all__ = [
    "normalize_verdict",
    "POSITIVE_VERDICTS",
    "NEGATIVE_VERDICTS",
    "safe_int",
    "safe_number",
    "is_finite_number",
    "is_mitigated_locally",
    "unmitigated_spans",
    "validate_inputs",
    "run_filters_fail_closed",
]

POSITIVE_VERDICTS = frozenset({"GO", "DEPLOY", "CONDITIONAL_GO", "CONDITIONAL"})
NEGATIVE_VERDICTS = frozenset({"NO_GO", "KILL", "REJECT", "NO", "HOLD"})

_SENTENCE_BOUNDARY_RE = re.compile(r"(?:[.!?;]\s)|(?:\n+)")


def normalize_verdict(value: Any) -> str:
    """Canonicalise verdict spelling (``'conditional go'`` -> ``CONDITIONAL_GO``).

    v9.0 compared verdict strings against inconsistent tuples: B2 accepted
    ``CONDITIONAL GO`` and ``CONDITIONAL_GO`` but B3 accepted only ``GO`` and
    ``DEPLOY`` -- so a ``CONDITIONAL_GO`` report with 5% friction/1R passed the
    Jacobian friction gate. One canonical form removes that bypass.
    """
    v = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    while "__" in v:
        v = v.replace("__", "_")
    return v.strip("_")


def is_finite_number(value: Any) -> bool:
    """True only for a real, finite int/float (excludes bool, NaN, Inf, strings)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError, OverflowError):
        return False


def safe_number(value: Any, default: float | None = None) -> float | None:
    """Coerce to a finite float; return ``default`` for NaN/Inf/bad types.

    Deliberately does **not** coerce numeric strings from manifests: a
    ``"2026-Q3"`` sample period must be reported as malformed, not silently
    truncated to ``2026``.
    """
    return float(value) if is_finite_number(value) else default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Coerce an exact integer; reject floats with fractions and bad strings."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)
    return default


def _boundary_count(text: str, lo: int, hi: int) -> int:
    """Count sentence boundaries strictly between two character positions."""
    return sum(1 for m in _SENTENCE_BOUNDARY_RE.finditer(text) if lo < m.start() < hi)


def is_mitigated_locally(
    text: str,
    trigger_pos: int,
    *,
    terms: tuple[str, ...] | list[str] = (),
    mitigation_re: re.Pattern[str] | None = None,
    validator: Callable[[re.Match[str]], bool] | None = None,
    window: int = 180,
    max_sentence_gaps: int = 1,
) -> bool:
    """Return True iff a genuine qualifier is attached to this specific claim.

    A term must be both within ``window`` characters of the trigger **and**
    separated from it by at most ``max_sentence_gaps`` sentence boundaries.
    This defeats the "bury a disclaiming word in an unrelated appendix" bypass
    while still allowing a qualifier in an adjacent sentence.
    """
    lo = max(0, trigger_pos - window)
    hi = min(len(text), trigger_pos + window)
    low_region = text[lo:hi].lower()

    for term in terms:
        needle = term.lower()
        start = 0
        while True:
            idx = low_region.find(needle, start)
            if idx < 0:
                break
            abs_pos = lo + idx
            a, b = min(abs_pos, trigger_pos), max(abs_pos, trigger_pos)
            if _boundary_count(text, a, b) <= max_sentence_gaps:
                return True
            start = idx + 1

    if mitigation_re is not None:
        for m in mitigation_re.finditer(text, lo, hi):
            if validator is not None and not validator(m):
                continue
            abs_pos = m.start()
            a, b = min(abs_pos, trigger_pos), max(abs_pos, trigger_pos)
            if _boundary_count(text, a, b) <= max_sentence_gaps:
                return True
    return False


def unmitigated_spans(
    text: str,
    trigger_re: re.Pattern[str],
    *,
    terms: tuple[str, ...] | list[str] = (),
    mitigation_re: re.Pattern[str] | None = None,
    validator: Callable[[re.Match[str]], bool] | None = None,
    window: int = 180,
) -> list[tuple[int, str]]:
    """Return ``(position, matched_text)`` for triggers with no local qualifier."""
    out: list[tuple[int, str]] = []
    for m in trigger_re.finditer(text):
        if not is_mitigated_locally(
            text, m.start(), terms=terms, mitigation_re=mitigation_re,
            validator=validator, window=window,
        ):
            out.append((m.start(), m.group(0)))
    return out


def validate_inputs(manifest: dict[str, Any], model_env: dict[str, Any]) -> list[str]:
    """Pre-flight checks that make the filters total (incapable of raising).

    Every finding here is a **failure**, not a warning: a non-finite variable
    or an unparseable sample period means the study cannot be certified.
    """
    failures: list[str] = []

    if not isinstance(manifest, dict):
        return ["B0 (Manifest Integrity): manifest is not a JSON object"]
    if not isinstance(model_env, dict):
        return ["B0 (Model Integrity): python:model environment is not a mapping"]

    for name, value in model_env.items():
        if not is_finite_number(value):
            failures.append(
                f"B0 (Non-Finite Model Variable): `{name}` = {value!r} is not a finite number; "
                f"NaN/Inf/bool/string values cannot be certified"
            )

    cp = manifest.get("counterparty_physics") or {}
    if isinstance(cp, dict) and "sample_end_year" in cp:
        if safe_int(cp["sample_end_year"]) is None:
            failures.append(
                f"B0 (Malformed Sample Period): `counterparty_physics.sample_end_year` = "
                f"{cp['sample_end_year']!r} is not an integer year; recency cannot be certified"
            )
        else:
            year = safe_int(cp["sample_end_year"])
            if year is not None and not (1900 <= year <= 2100):
                failures.append(
                    f"B0 (Implausible Sample Period): sample_end_year={year} is outside [1900, 2100]"
                )

    cphys = manifest.get("clinical_physics") or {}
    if isinstance(cphys, dict) and "trial_phase" in cphys:
        if safe_int(cphys["trial_phase"]) is None:
            failures.append(
                f"B0 (Malformed Trial Phase): `clinical_physics.trial_phase` = "
                f"{cphys['trial_phase']!r} is not an integer"
            )

    evidence = manifest.get("evidence", [])
    if not isinstance(evidence, list):
        failures.append("B0 (Manifest Integrity): `evidence` must be a list")

    return failures


def run_filters_fail_closed(
    report_text: str,
    manifest: dict[str, Any],
    model_env: dict[str, Any],
    verified_evidence_ids: set[str] | None = None,
    arbitration_out: dict[str, Any] | None = None,
    pooled_subjects: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Evaluate B0-B10 with a fail-closed posture.

    Args:
        report_text: Full ``report.md`` text (including fenced blocks).
        manifest: Parsed ``json:manifest`` (or ``manifest.json``).
        model_env: Executed ``python:model`` variable environment.
        verified_evidence_ids: Evidence IDs whose quotes were *already*
            validated verbatim against an immutable SHA-256 snapshot. When
            supplied, neither B9 benchmark grounding nor B10 conflict
            detection can be satisfied by a self-declared manifest quote.
        arbitration_out: Optional mutable dict filled with the v11.0 B10
            Dialectical Reconciliation Matrix (used to cap confidence).
        pooled_subjects: Subjects that DerSimonian-Laird pooling has combined;
            B10 forbids pooling across a de_jure/de_facto contradiction.

    Returns:
        ``(failures, warnings)``. Any exception inside the filter stack yields
        a ``B0`` hard failure rather than a warning.
    """
    failures: list[str] = []
    warnings: list[str] = []

    failures.extend(validate_inputs(manifest, model_env))

    try:
        from dr_engine.tools.v9_bullshit_filters import (
            run_b10_dialectical_filter, run_v9_bullshit_filters,
        )

        f, w = run_v9_bullshit_filters(
            report_text, manifest, model_env,
            verified_evidence_ids=verified_evidence_ids,
        )
        if not isinstance(f, list) or not isinstance(w, list):
            raise TypeError("filter stack returned a non-list result")
        f10, w10 = run_b10_dialectical_filter(
            report_text, manifest,
            arbitration_out=arbitration_out,
            verified_evidence_ids=verified_evidence_ids,
            pooled_subjects=pooled_subjects,
        )
        if not isinstance(f10, list) or not isinstance(w10, list):
            raise TypeError("B10 arbitration returned a non-list result")
        f, w = f + f10, w + w10
    except Exception as exc:  # fail-closed: never degrade epistemic gates to warnings
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        failures.append(
            f"B0 (Filter Integrity / FAIL-CLOSED): B1-B10 could not be fully evaluated "
            f"({type(exc).__name__}: {detail}). The study cannot be certified while any "
            f"epistemic filter is unevaluable. Fix the malformed manifest/model input "
            f"and re-run verification."
        )
        return failures, warnings

    failures.extend(str(x) for x in f)
    warnings.extend(str(x) for x in w)
    return failures, warnings


def _selftest() -> int:
    assert normalize_verdict("conditional go") == "CONDITIONAL_GO"
    assert normalize_verdict("NO-GO") == "NO_GO"
    assert normalize_verdict("CONDITIONAL_GO") in POSITIVE_VERDICTS
    assert safe_number(float("nan")) is None
    assert safe_number(float("inf")) is None
    assert safe_number(True) is None
    assert safe_number("8.4") is None
    assert safe_number(8.4) == 8.4
    assert safe_int("2026") == 2026
    assert safe_int("2026-Q3") is None
    assert safe_int(2026.0) == 2026
    assert safe_int(2026.5) is None

    trigger = re.compile(r"two-way real-time sync", re.I)
    # A distant "avoid" in an unrelated appendix must NOT disarm the rule.
    distant = (
        "We will deploy a two-way real-time sync across channels. "
        + "Unrelated filler sentence. " * 30
        + " avoid"
    )
    assert unmitigated_spans(distant, trigger, terms=("avoid", "rejected"))
    # A local qualifier does disarm it.
    near = "We avoid a two-way real-time sync; instead we use read-only diffs."
    assert not unmitigated_spans(near, trigger, terms=("avoid", "rejected"))

    # Regex mitigation with a numeric validator (B1 n >= 30).
    ev_trigger = re.compile(r"Base\s+\d+%", re.I)
    n_re = re.compile(r"\bn\s*=\s*(\d+)\b", re.I)
    at_least_30 = lambda m: int(m.group(1)) >= 30
    weak = "Base 50% / Bear 35% / Stress 15%." + " filler. " * 40 + "n=30"
    assert unmitigated_spans(weak, ev_trigger, mitigation_re=n_re, validator=at_least_30)
    strong = "Base 50% with n=45 observed sessions."
    assert not unmitigated_spans(strong, ev_trigger, mitigation_re=n_re, validator=at_least_30)

    assert validate_inputs({}, {"x": float("nan")})
    assert validate_inputs({"counterparty_physics": {"sample_end_year": "2026-Q3"}}, {})
    assert not validate_inputs({"counterparty_physics": {"sample_end_year": 2026}}, {"x": 1.0})

    print("[SELFTEST PASS] epistemic_guard v10.0 (scoped mitigation + fail-closed B0) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
