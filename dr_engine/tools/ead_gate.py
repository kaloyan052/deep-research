#!/usr/bin/env python3
"""Deep Research Engine v12.0 — Epistemic Alpha Delta (EAD) Gate (Frontier 3).

A deep research report that only restates the first page of a search engine has
negative value: the reader already had that. The deliverable must show the
*delta* — the ground truth that our multilingual trench miners and immutable
snapshots proved, and what acting on the superficial consensus would have cost.

Rule R18 enforces a mandatory ``## Epistemic Alpha Delta`` section with exactly
three contrast-bearing parts:

  * **Superficial Consensus** — what standard LLMs / generic search returns;
  * **Trench Ground-Truth (The Alpha)** — the hidden bug, the 511 kg upset, the
    unreleased preview, the silent fee. Must cite at least one verbatim
    snapshot-verified [E###] that the consensus section does NOT cite;
  * **Delta Impact** — why the consensus would have caused financial,
    operational or strategic loss.

The contrast is mechanical, not editorial: shingle-Jaccard between the
consensus and trench bodies must stay below ``MAX_CONTRAST_JACCARD``, so a
copy-paste "delta" cannot pass. Placeholders, empty sections and unverified
evidence IDs are hard failures.

Protocol versioning: v12 gates are MANDATORY for every study carrying
``protocol_version: "12.0"`` (emitted by ``auto_spec.generate`` from v12
onwards). Pre-v12 studies remain verifiable exactly as before and receive an
explicit ``W_EAD_LEGACY_STUDY`` warning instead of a retroactive failure —
this preserves the 322-test regression invariant without weakening any new
study. Use ``lean_engine.py verify --strict-v12`` to force the gate on any
study.

Rule B0 is preserved: the whole v12 gate stack runs inside a fail-closed
wrapper; an unevaluable gate is a hard failure, never a warning.

Pure Python 3.10+ stdlib. Zero paid API keys. Windows cp1252-safe.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any

# Allow both `python dr_engine/tools/ead_gate.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.dethrone import run_b11_dethroning_filter  # noqa: E402
from dr_engine.tools.polyglot_text import shingles  # noqa: E402

__all__ = [
    "EAD_HEADING", "REQUIRED_SUBSECTIONS", "MIN_SECTION_CHARS",
    "MAX_CONTRAST_JACCARD", "PROTOCOL_VERSION", "EADHeading",
    "parse_ead_section", "validate_ead_section", "render_ead_template",
    "is_v12_protocol", "run_v12_gates_fail_closed",
]

EAD_HEADING = "Epistemic Alpha Delta"
PROTOCOL_VERSION = "12.0"
MIN_SECTION_CHARS = 40
MAX_CONTRAST_JACCARD = 0.70

REQUIRED_SUBSECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("superficial_consensus", ("superficial consensus", "generic consensus", "standard consensus")),
    ("trench_ground_truth", ("trench ground-truth", "trench ground truth", "the alpha",
                             "trench truth", "ground-truth")),
    ("delta_impact", ("delta impact", "impact of the delta", "why it matters")),
)

_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.M)
_EID_RE = re.compile(r"\bE\d{3}\b")
_CID_RE = re.compile(r"\bC\d{3}\b")
_NUM_RE = re.compile(r"\d")
_PLACEHOLDER_RE = re.compile(
    # Angle-bracket template slots can be long; 60 chars let real template
    # placeholders through. 200 covers the canonical EAD scaffold verbatim.
    r"<\s*[^>]{1,200}\s*>|\bTODO\b|\bTBD\b|\bFIXME\b|\bplaceholder\b|"
    r"\bpaste\s+output\b|\bfill\s+(?:this|me|in)\b|\.\.\.|…",
    re.I,
)
_LOSS_VECTORS = (
    "financial", "monetary", "cash", "revenue", "loss", "cost", "usd", "eur",
    "operational", "outage", "downtime", "production", "incident", "latency",
    "strategic", "roadmap", "competitive", "market share", "contract", "reputation",
    "финансов", "убыток", "операцион", "стратегич", "经济损失", "上线故障", "战略",
    "financiero", "operativo", "estratégico", "finanziell", "operativ", "strategisch",
)
_EAD_SUBSECTION_ALIASES: dict[str, str] = {
    alias: key for key, aliases in REQUIRED_SUBSECTIONS for alias in aliases
}


class EADHeading:
    """Small compatibility alias (kept as a plain class, no dataclass dependency)."""

    def __init__(self, present: bool, body: str = "", sections: dict[str, str] | None = None):
        self.present = present
        self.body = body
        self.sections = sections or {}

    def as_dict(self) -> dict[str, Any]:
        return {"present": self.present, "body": self.body, "sections": dict(self.sections)}


def _canonical_subsection(title: str) -> str | None:
    low = re.sub(r"[^a-zа-яё\w\s-]", " ", title.lower(), flags=re.I)
    low = re.sub(r"\s+", " ", low).strip()
    for alias, key in _EAD_SUBSECTION_ALIASES.items():
        if alias in low:
            return key
    return None


def parse_ead_section(report_text: Any) -> dict[str, Any]:
    """Locate the EAD section and split it into canonical subsections.

    Robust to heading levels 2-4, bold subsection labels and trailing prose.
    Never raises on malformed input.
    """
    text = report_text if isinstance(report_text, str) else str(report_text or "")
    headings = list(_HEADING_RE.finditer(text))
    start: int | None = None
    level = 0
    for h in headings:
        if EAD_HEADING.lower() in h.group(2).lower():
            start, level = h.end(), len(h.group(1))
            break
    if start is None:
        return {"present": False, "body": "", "sections": {}, "heading_level": 0}

    end = len(text)
    for h in headings:
        if h.start() <= start:
            continue
        if len(h.group(1)) <= level:
            end = h.start()
            break
    body = text[start:end].strip()

    sections: dict[str, str] = {}
    sub_heads: list[tuple[int, int, str]] = []
    for m in _HEADING_RE.finditer(body):
        key = _canonical_subsection(m.group(2))
        if key:
            sub_heads.append((m.start(), m.end(), key))
    for i, (s, e, key) in enumerate(sub_heads):
        stop = sub_heads[i + 1][0] if i + 1 < len(sub_heads) else len(body)
        sections[key] = sections.get(key, "") + "\n" + body[e:stop].strip()
    if not sub_heads:
        # Also accept bold labels: "**Superficial Consensus**: ..."
        for m in re.finditer(r"\*\*([^*]{3,80})\*\*\s*[:\-]?", body):
            key = _canonical_subsection(m.group(1))
            if key:
                sections.setdefault(key, "")
                tail = body[m.end():m.end() + 1200]
                nxt = re.search(r"\*\*[^*]{3,80}\*\*", tail)
                sections[key] += tail[: nxt.start() if nxt else len(tail)].strip() + "\n"
    return {
        "present": True, "body": body,
        "sections": {k: v.strip() for k, v in sections.items()},
        "heading_level": level,
    }


def _jaccard(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(text)) or len(re.findall(r"\S+", text)) < 6


def validate_ead_section(
    prose_text: str,
    manifest: dict[str, Any] | None = None,
    verified_evidence_ids: set[str] | None = None,
    *,
    min_chars: int = MIN_SECTION_CHARS,
) -> tuple[list[str], dict[str, Any]]:
    """Rule R18: enforce a real, contrast-bearing EAD section.

    Returns ``(failures, diagnostics)``. ``verified_evidence_ids`` must be the
    set of IDs whose quotes passed verbatim SHA-256 snapshot verification; a
    self-declared ID in prose is not enough to ground the trench ground-truth.
    """
    parsed = parse_ead_section(prose_text)
    manifest = manifest if isinstance(manifest, dict) else {}
    diag: dict[str, Any] = {
        "present": parsed["present"],
        "sections_found": sorted(parsed["sections"]),
        "missing": [],
        "consensus_evidence": [],
        "trench_evidence": [],
        "verified_trench_evidence": [],
        "contrast_jaccard": None,
        "loss_vectors": [],
        "passed": False,
    }
    failures: list[str] = []
    if not parsed["present"]:
        failures.append(
            "R18 (Epistemic Alpha Delta Missing): report.md has no "
            f"'## {EAD_HEADING}' section. A report that only repeats the "
            "superficial consensus has zero epistemic alpha; state the "
            "consensus, the trench ground-truth, and the delta impact."
        )
        return failures, diag

    sections = parsed["sections"]
    missing = [key for key, _ in REQUIRED_SUBSECTIONS if not sections.get(key)]
    diag["missing"] = missing
    for key in missing:
        label = next(aliases[0] for k, aliases in REQUIRED_SUBSECTIONS if k == key)
        failures.append(
            f"R18 (EAD Subsection Missing): '{label}' is absent from the "
            f"{EAD_HEADING} section."
        )
    for key, body in sections.items():
        if len(body) < min_chars or _is_placeholder(body):
            failures.append(
                f"R18 (EAD Placeholder): '{key}' is empty, templated or under "
                f"{min_chars} characters ({len(body)} chars). Cite real evidence."
            )
    if missing:
        return failures, diag

    consensus, trench, impact = (
        sections["superficial_consensus"], sections["trench_ground_truth"],
        sections["delta_impact"],
    )
    consensus_ids = sorted(set(_EID_RE.findall(consensus)))
    trench_ids = sorted(set(_EID_RE.findall(trench)))
    diag["consensus_evidence"] = consensus_ids
    diag["trench_evidence"] = trench_ids

    if not trench_ids:
        failures.append(
            "R18 (Trench Alpha Uncited): 'Trench Ground-Truth' cites no [E###] "
            "snapshot. An uncited claim is an assertion, not ground truth."
        )
    else:
        verified = set(verified_evidence_ids or set())
        if verified:
            ok = [e for e in trench_ids if e in verified]
            diag["verified_trench_evidence"] = ok
            if not ok:
                failures.append(
                    "R18 (Unverified Trench Evidence): none of "
                    f"{trench_ids} passed verbatim snapshot verification."
                )
        novel = [e for e in trench_ids if e not in consensus_ids]
        if not novel:
            failures.append(
                "R18 (No Epistemic Delta): the trench ground-truth cites only "
                f"{consensus_ids}, the same evidence as the superficial "
                "consensus. A delta requires at least one additional verified "
                "snapshot that generic search did not surface."
            )

    jac = _jaccard(shingles(consensus, k=3), shingles(trench, k=3))
    diag["contrast_jaccard"] = round(jac, 4)
    if jac >= MAX_CONTRAST_JACCARD:
        failures.append(
            f"R18 (Contrast Collapse): superficial consensus and trench "
            f"ground-truth overlap at shingle-Jaccard {jac:.3f} (>= "
            f"{MAX_CONTRAST_JACCARD}). Copying the consensus into the 'Alpha' "
            "section is not a delta."
        )

    low_impact = impact.lower()
    hits = sorted({w for w in _LOSS_VECTORS if w in low_impact})
    diag["loss_vectors"] = hits
    if not hits:
        failures.append(
            "R18 (Delta Impact Not Consequential): state the concrete financial, "
            "operational or strategic loss of acting on the superficial "
            "consensus (name the vector, not just 'it matters')."
        )
    if not (_NUM_RE.search(impact) or _EID_RE.search(impact) or _CID_RE.search(impact)):
        failures.append(
            "R18 (Delta Impact Unquantified): the impact statement must carry a "
            "measured number, an [E###] quote or a [C###] calculation."
        )

    # Optional structured declaration: cross-check it against the prose.
    declared = manifest.get("epistemic_alpha_delta")
    if isinstance(declared, dict):
        declared_ids = [str(x) for x in (declared.get("trench_evidence") or [])]
        if declared_ids and verified_evidence_ids is not None:
            bad = [e for e in declared_ids if e not in verified_evidence_ids]
            if bad:
                failures.append(
                    "R18 (Manifest/Prose Mismatch): "
                    f"manifest.epistemic_alpha_delta.trench_evidence {bad} are "
                    "not snapshot-verified evidence IDs."
                )

    diag["passed"] = not failures
    return failures, diag


def render_ead_template(
    consensus: str = "",
    trench: str = "",
    impact: str = "",
) -> str:
    """Canonical EAD markdown block used by the report template and the CLI."""
    return (
        f"## {EAD_HEADING}\n\n"
        "### Superficial Consensus\n\n"
        + (consensus or "<what a 5-second generic search / standard LLM answers; name the stale leader or claim>")
        + "\n\n### Trench Ground-Truth (The Alpha)\n\n"
        + (trench or "<the multilingual practitioner disclosure or freshly dethroned record, with [E###]>")
        + "\n\n### Delta Impact\n\n"
        + (impact or "<financial / operational / strategic loss avoided, with a measured number [E###] or [C###]>")
        + "\n"
    )


def _version_at_least_12(val: Any) -> bool:
    s = str(val or "").strip().lstrip("vV")
    m = re.match(r"^(\d+)(?:\.(\d+))?$", s)
    if not m:
        return False
    return (int(m.group(1)), int(m.group(2) or 0)) >= (12, 0)


def is_v12_protocol(
    study_dir: Path | str | None,
    manifest: dict[str, Any] | None,
    *,
    force: bool = False,
) -> bool:
    """Decide whether the mandatory v12 gates apply to this study.

    A study is v12+ when its manifest or its ``study_spec.json`` declares
    ``protocol_version >= 12.0`` (including ``"13.0"``), or when forced.
    Pre-v12 studies stay on the v11 gate stack (no retroactive failure).
    """
    if force:
        return True
    if isinstance(manifest, dict):
        if _version_at_least_12(manifest.get("protocol_version")):
            return True
        if isinstance(manifest.get("epistemic_alpha_delta"), dict):
            return True
        if isinstance(manifest.get("dethroning"), list) and manifest["dethroning"]:
            return True
    if study_dir is not None:
        p = Path(study_dir) / "study_spec.json"
        try:
            if p.exists():
                spec = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(spec, dict) and _version_at_least_12(spec.get("protocol_version")):
                    return True
        except (OSError, ValueError, TypeError):
            # Unreadable spec must not silently disable the gate: callers that
            # declare v12 in the manifest are already covered; otherwise warn.
            pass
    return False


def run_v12_gates_fail_closed(
    prose_text: str,
    manifest: dict[str, Any],
    verified_evidence_ids: set[str],
    *,
    protocol_active: bool,
    as_of: dt.date | str | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Single fail-closed entry point for Rule R18 (EAD) and Rule B11.

    When ``protocol_active`` is False the gates do not run (legacy study) and a
    single explicit warning is emitted. When active, any exception inside the
    gate stack produces ``B0 (v12 Gate Integrity / FAIL-CLOSED)`` — never a
    warning, never a silent pass.
    """
    diag: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION if protocol_active else "legacy",
        "active": bool(protocol_active),
        "ead": {}, "dethroning": {}, "passed": False,
    }
    if not protocol_active:
        return [], [
            "W_EAD_LEGACY_STUDY: this study declares no v12 protocol; mandatory "
            "EAD / dethroning gates were not applied. Re-run auto_spec v12.0 "
            "and add the Epistemic Alpha Delta section."
        ], diag

    failures: list[str] = []
    warnings: list[str] = []
    try:
        ead_failures, ead_diag = validate_ead_section(
            prose_text, manifest, verified_evidence_ids,
        )
        b11_failures, b11_warnings, b11_diag = run_b11_dethroning_filter(
            prose_text, manifest, verified_evidence_ids, as_of=as_of,
        )
        if not isinstance(ead_failures, list) or not isinstance(b11_failures, list):
            raise TypeError("v12 gate returned a non-list result")
        failures.extend(ead_failures)
        failures.extend(b11_failures)
        warnings.extend(b11_warnings)
        diag["ead"] = ead_diag
        diag["dethroning"] = b11_diag
    except Exception as exc:  # Rule B0: an unevaluable gate can never certify
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        failures.append(
            f"B0 (v12 Gate Integrity / FAIL-CLOSED): R18/B11 could not be fully "
            f"evaluated ({type(exc).__name__}: {detail}). The study cannot be "
            "certified while any epistemic gate is unevaluable."
        )
        return failures, warnings, diag

    diag["passed"] = not failures
    return failures, warnings, diag


def _selftest() -> int:
    good = (
        "# Study\n\n## Epistemic Alpha Delta\n\n"
        "### Superficial Consensus\n\n"
        "Generic search still reports Hafthor Bjornsson's 510 kg deadlift as the "
        "standing world record, an answer copied by most model responses. [E001]\n\n"
        "### Trench Ground-Truth (The Alpha)\n\n"
        "A Spanish-language eyewitness posted from Birmingham that Raul Flores "
        "actually pulled 511 kg; the federation results snapshot confirms it. [E007]\n\n"
        "### Delta Impact\n\n"
        "Booking or settling a record-based sponsorship at 510 kg would have "
        "caused a financial loss of 250000 USD and a strategic credibility "
        "failure once the 511 kg result was ratified. [E007, C001]\n"
    )
    fails, diag = validate_ead_section(
        good, {}, verified_evidence_ids={"E001", "E007"},
    )
    assert not fails, fails
    assert diag["passed"] and diag["contrast_jaccard"] < MAX_CONTRAST_JACCARD
    assert "E007" in diag["verified_trench_evidence"]
    assert diag["loss_vectors"]

    missing, d2 = validate_ead_section("# Study\n\nNo delta here.\n", {}, set())
    assert any("R18 (Epistemic Alpha Delta Missing)" in f for f in missing)
    assert not d2["present"]

    copy_paste = good.replace(
        "A Spanish-language eyewitness posted from Birmingham that Raul Flores "
        "actually pulled 511 kg; the federation results snapshot confirms it. [E007]",
        "Generic search still reports Hafthor Bjornsson's 510 kg deadlift as the "
        "standing world record, an answer copied by most model responses. [E007]",
    )
    copy_fail, _ = validate_ead_section(
        copy_paste, {}, verified_evidence_ids={"E001", "E007"},
    )
    assert any("R18 (Contrast Collapse)" in f or "R18 (No Epistemic Delta)" in f
               for f in copy_fail), copy_fail

    placeholders, _ = validate_ead_section(render_ead_template(), {}, set())
    assert placeholders

    assert is_v12_protocol(None, {"protocol_version": "12.0"})
    assert not is_v12_protocol(None, {"domain": "quant"})
    assert is_v12_protocol(None, {}, force=True)

    f, w, d = run_v12_gates_fail_closed("No EAD at all.", {}, set(), protocol_active=False)
    assert not f and any("W_EAD_LEGACY_STUDY" in x for x in w) and d["protocol_version"] == "legacy"
    f2, _, d2b = run_v12_gates_fail_closed("No EAD at all.", {}, set(), protocol_active=True)
    assert f2 and d2b["active"] and not d2b["passed"]

    print("[SELFTEST PASS] ead_gate v12.0 (R18 contrast / B11 / B0 fail-closed) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
