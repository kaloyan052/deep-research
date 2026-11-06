#!/usr/bin/env python3
"""Deep Research Engine v11.0 — R17 Anti-Fluff Information Density Gate.

A report can pass every citation, arithmetic and filter gate and still be
useless: pages of confident, generic academic prose with almost no verified
empirical content. v10.0 computed the Information Density Index (IDI) but never
*enforced* it, and had no defence against boilerplate LLM phrasing.

R17 is a purely mechanical gate with three independent checks:

  1. ``IDI >= 100``  -- weighted verified-entity density per 1000 words.
  2. ``D >= 3.0``    -- verified empirical entities per 100 words
                        (evidence quotes + executed model values + bound number
                        units), which punishes padding with words.
  3. Boilerplate detection on prose only (fenced code stripped):
       * any single HARD phrase ("paves the way", "a multifaceted approach",
         "delve into", ...) -> reject;
       * two or more distinct SOFT phrases ("in conclusion",
         "it is important to remember", ...) -> reject.

There is no LLM judgement, no semantic scoring and no tunable subjective
weight. Every threshold is a module constant and every rejection names the
exact offending phrases and the measured numbers.

Pure Python 3.10+ stdlib. Windows cp1252-safe.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "IDI_MIN", "DENSITY_MIN_PER_100", "BOILERPLATE_SOFT", "BOILERPLATE_HARD",
    "strip_fenced_code", "detect_boilerplate", "empirical_density",
    "evaluate_r17_gate",
]

IDI_MIN = 100.0
DENSITY_MIN_PER_100 = 3.0
SOFT_PHRASE_LIMIT = 1   # >= 2 distinct soft phrases fails
HARD_PHRASE_LIMIT = 0   # any hard phrase fails

# Hard phrases are near-certain signals of generated filler. One is enough.
BOILERPLATE_HARD: tuple[str, ...] = (
    "paves the way", "a multifaceted approach", "delve into", "delving into",
    "testament to", "unlock the full potential", "unlocking the potential",
    "game-changer", "game changer", "in today's fast-paced world",
    "a paradigm shift", "navigate the complexities", "the ever-evolving landscape",
    "it is worth noting that", "a nuanced understanding",
)

# Soft phrases are common but acceptable in isolation; a cluster is fluff.
BOILERPLATE_SOFT: tuple[str, ...] = (
    "it is important to remember", "it is important to note", "in conclusion",
    "further research is needed", "more research is needed", "at the end of the day",
    "in summary", "to summarize", "overall", "broadly speaking",
    "it goes without saying", "needless to say", "as we have seen",
    "a wide range of", "a variety of factors", "plays a crucial role",
    "plays a key role", "it should be noted", "in the realm of",
)

_FENCE_RE = re.compile(r"```.*?```", re.S)
_MATH_RE = re.compile(r"\$\$.*?\$\$", re.S)
_WORD_RE = re.compile(r"\S+")


def strip_fenced_code(text: str) -> str:
    """Remove fenced code and display math before measuring prose density."""
    return _MATH_RE.sub(" ", _FENCE_RE.sub(" ", str(text or "")))


def detect_boilerplate(prose: str) -> dict[str, Any]:
    """Return distinct matched phrases, split into hard and soft buckets.

    Defensively strips fenced code itself: boilerplate text inside a code
    sample or a quotation of bad prose is not the author's own filler.
    """
    low = strip_fenced_code(prose).lower()
    hard = sorted({p for p in BOILERPLATE_HARD if p in low})
    soft = sorted({p for p in BOILERPLATE_SOFT if p in low})
    return {
        "hard": hard,
        "soft": soft,
        "distinct": sorted(set(hard) | set(soft)),
        "hard_count": len(hard),
        "soft_count": len(soft),
    }


def empirical_density(
    word_count: int,
    n_evidence: int,
    n_models: int,
    bound_units: int,
    weights: tuple[float, float, float] = (2.0, 5.0, 1.0),
) -> float:
    """Verified empirical entities per 100 words.

    ``entities = 2*E + 5*M + 1*U`` where E = verbatim-verified evidence quotes,
    M = executed ``python:model`` blocks and U = bound quantitative claim units.
    Verbatim quotes and executable models dominate: they are the expensive,
    falsifiable artefacts that fluff cannot manufacture.
    """
    w = max(1, int(word_count))
    entities = weights[0] * max(0, n_evidence) + weights[1] * max(0, n_models) + weights[2] * max(0, bound_units)
    return round(100.0 * entities / w, 2)


def evaluate_r17_gate(
    prose_text: str,
    *,
    idi: float,
    n_evidence: int,
    n_models: int,
    bound_units: int,
    word_count: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Evaluate R17. Returns ``(failures, diagnostics)``.

    ``prose_text`` must already have fenced code stripped by the caller (or
    :func:`strip_fenced_code` is applied here as a safety net).
    """
    prose = strip_fenced_code(prose_text)
    words = max(1, int(word_count if word_count is not None else len(_WORD_RE.findall(prose))))
    density = empirical_density(words, n_evidence, n_models, bound_units)
    boiler = detect_boilerplate(prose)

    diagnostics: dict[str, Any] = {
        "idi": round(float(idi), 1),
        "idi_min": IDI_MIN,
        "empirical_density_per_100w": density,
        "density_min": DENSITY_MIN_PER_100,
        "word_count": words,
        "n_evidence": n_evidence,
        "n_models": n_models,
        "bound_units": bound_units,
        "boilerplate": boiler,
        "passed": False,
    }

    failures: list[str] = []
    if float(idi) < IDI_MIN:
        failures.append(
            f"R17 (Information Density Gate): IDI={float(idi):.1f} < {IDI_MIN:.0f}. "
            f"The report is too dilute: {n_evidence} verified quotes and {n_models} "
            f"executable models across {words} words. Add verbatim empirical entities "
            f"or remove generic prose -- never pad to pass a gate."
        )
    if density < DENSITY_MIN_PER_100:
        failures.append(
            f"R17 (Empirical Entity Density): {density:.2f} verified entities per "
            f"100 words < {DENSITY_MIN_PER_100:.1f}. {words} words carry only "
            f"{n_evidence} quotes, {n_models} models and {bound_units} bound units."
        )
    if boiler["hard_count"] > HARD_PHRASE_LIMIT:
        failures.append(
            f"R17 (Anti-Fluff / Hard Boilerplate): {boiler['hard']} are generic AI "
            "phrases with zero empirical content. Remove them and replace with "
            "cited, quantitative findings."
        )
    if boiler["soft_count"] > SOFT_PHRASE_LIMIT:
        failures.append(
            f"R17 (Anti-Fluff / Boilerplate Cluster): {len(boiler['soft'])} distinct "
            f"filler phrases detected: {boiler['soft']}. A study must read as an "
            "intelligence briefing, not an academic literature review."
        )

    diagnostics["passed"] = not failures
    return failures, diagnostics


def _selftest() -> int:
    good = (
        "# Execution Friction\n\n"
        "Effective spread is 1.2 bps across 500 sessions [E001]. Net alpha is "
        "5.4 bps [E001, C001]. Round-turn friction totals 3.0 bps [E002]."
    )
    fails, diag = evaluate_r17_gate(
        good, idi=140.0, n_evidence=3, n_models=1, bound_units=6)
    assert not fails, f"unexpected R17 failures on dense prose: {fails}"
    assert diag["passed"] and diag["empirical_density_per_100w"] >= DENSITY_MIN_PER_100

    fluffy = (
        "# A Broad Overview\n\n"
        "It is important to remember that this is a multifaceted approach. "
        "In conclusion, it is worth noting that the landscape is complex. "
        "Overall, a wide range of factors plays a crucial role. " * 20
    )
    f_fluff, d_fluff = evaluate_r17_gate(
        fluffy, idi=12.0, n_evidence=1, n_models=0, bound_units=0)
    assert any("R17 (Information Density Gate)" in f for f in f_fluff)
    assert any("R17 (Empirical Entity Density)" in f for f in f_fluff)
    assert any("Hard Boilerplate" in f for f in f_fluff)
    assert any("Boilerplate Cluster" in f for f in f_fluff)
    assert not d_fluff["passed"]

    # Code blocks never count as prose (and cannot smuggle boilerplate).
    coded = strip_fenced_code("Intro prose.\n```python\nx = 1\n```\nMore prose.")
    assert "```" not in coded and "x = 1" not in coded
    assert detect_boilerplate("```python\nIn conclusion: paves the way\n```")["hard"] == []

    assert empirical_density(100, 3, 1, 6) == round(100.0 * (6 + 5 + 6) / 100, 2)
    print("[SELFTEST PASS] density_gate v11.0 (R17 IDI / density / boilerplate) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
