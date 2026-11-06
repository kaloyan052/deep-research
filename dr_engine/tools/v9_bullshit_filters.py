#!/usr/bin/env python3
"""Deep Research v10.0 Anti-Goodhart & Operational Bullshit Filters (B1-B9).

Enforces:
  B1: No Fake EV Math (bans uncalibrated subjective scenario probabilities;
      mandates deterministic unit breakeven & churn replacement math).
  B2: Zero-Liability Solo Operational Physics (rejects 2-way real-time mutating
      syncs in favor of Read-Only / Preflight / BYOD architectures).
  B3: Modern Microstructure & Jacobian Friction Tipping Point (rejects pre-2023
      decayed anomalies, enforces Friction/1R <= 3.0%, verifies runnable code).
  B4: The "ChatGPT Wrapper" Falsification Test.
  B5: WTP vs. Complaint Separation & Pre-Committed 14-Day Falsifiable Demand Test.
  B6: Biotech & Clinical Physics (Phase 2->3 shrinkage, tolerability dropout <= 25%).
  B7: Legal & Tax Normative Hierarchy (Statute vs Guidance, no unmapped US/BG mix).
  B8: Hardware & Thermodynamic Limits (headroom <= 0.95, BOM economics, yield).
  B9: Temporal Recency & SOTA Benchmark Grounding (bans deprecated models as
      current leaders; mandates verified Tier 2 measured benchmarks).

v10.0 hardening (see ``epistemic_guard.py`` for the rationale):
  * disclaimers are checked **locally** to the triggering claim, not anywhere
    in the document (closes the global-keyword disarm bypass);
  * numeric inputs are finite-only and verdicts are canonicalised (closes the
    NaN / ``CONDITIONAL_GO`` friction bypasses);
  * B9 is **claim-triggered**, so it fires on a SOTA claim in any domain --
    v9.0 gated it on domains the classifier could never emit;
  * B9 benchmark grounding can be restricted to evidence IDs already verified
    verbatim against an immutable snapshot (``verified_evidence_ids``).

Pure Python stdlib. Windows cp1252-safe.
"""

from __future__ import annotations

import ast
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# Allow both `python dr_engine/tools/v9_bullshit_filters.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.epistemic_guard import (  # noqa: E402
    NEGATIVE_VERDICTS,
    POSITIVE_VERDICTS,
    is_mitigated_locally,
    normalize_verdict,
    safe_int,
    safe_number,
    unmitigated_spans,
)

# B1: Detects fake subjective EV tables ("Win Prob 15%", "Base 50% / Bear 35% / Stress 15%")
FAKE_EV_PROB_RE = re.compile(
    r"\b(?:win\s+prob(?:ability)?|p\s*\(\s*success\s*\)|scenario\s+weight|субективна\s+вероятност)\b"
    r"|\|\s*\*{0,2}(?:Base|Bear|Stress|Базов|Песимистичен)\*{0,2}\s*\|\s*\d{1,2}(?:\.\d+)?%\s*\|"
    r"|\b(?:Base|Bear|Stress|Базов)\s+\d{1,2}(?:\.\d+)?%",
    re.I,
)
EMPIRICAL_SAMPLE_RE = re.compile(r"\b(?:n|N|sample\s+size|извадка)\s*=\s*\d{2,}\b")
# v10.0: the sample size must be >= 30 AND attached to the EV table it calibrates.
EMPIRICAL_N_RE = re.compile(
    r"\b(?:n|N|sample\s+size|извадка)\s*[=:]\s*(\d{2,})\b", re.I
)


def _n_at_least_30(match: re.Match[str]) -> bool:
    """B1 validator: a subjective scenario weight needs n >= 30 behind it."""
    try:
        return int(match.group(1)) >= 30
    except (ValueError, TypeError, IndexError):
        return False

# B2: Dangerous high-liability mutating SaaS architectures for a solo founder
MUTATING_LIABILITY_RE = re.compile(
    r"\b(two[- ]way\s+(?:real[- ]time\s+)?sync|bi[- ]directional\s+(?:inventory\s+)?sync|"
    r"real[- ]time\s+inventory\s+overwrite|auto[- ]cancel\s+orders|live\s+order\s+routing|"
    r"custodial\s+wallet|automated\s+tax\s+filing\s+submission)\b",
    re.I,
)
ALLOWED_SOLO_ARCHITECTURES = {
    "read_only_diff",
    "preflight_validator",
    "in_browser_byod_parser",
    "offline_quota_sentry",
    "deterministic_audit_report",
}

# B3: Refuted / decayed pre-2022 textbook anomalies
REFUTED_TEXTBOOK_ANOMALIES = {
    "overnight drift": "Boyarchenko et al. (2026): US equity overnight drift decayed post-2021.",
    "london 4pm fix": "Lab P31/FXFIX01 (t = -11.09): Fix window widening killed reversal edge.",
    "naive turn of the month": "Front-run by T-5 to T-1 pension rebalance flows; classical T+1..T+3 decayed.",
    "unfiltered moving average crossover": "Negative net expectancy after spread and slippage.",
}

# B4: Structural mechanisms that pass the ChatGPT Falsification Test
STRUCTURAL_MOAT_MECHANISMS = {
    "multi_file_deterministic_parser",
    "in_browser_wasm_large_file",
    "statutory_xsd_ast_validator",
    "cross_system_read_only_reconciliation",
    "proprietary_microstructure_dataset",
    "cryptographic_audit_trail",
}


def extract_fenced_python_code(report_text: str) -> list[str]:
    """Extracts all runnable ` ```python ` code blocks (excluding `python:model` blocks)."""
    blocks: list[str] = []
    for m in re.finditer(r"```python(?!\s*:model)\s*\n(.*?)```", report_text, re.S):
        blocks.append(m.group(1).strip())
    return blocks


def verify_runnable_code_blocks(code_blocks: list[str], min_loc: int = 35) -> list[str]:
    """Verifies that extracted Python code blocks parse cleanly, contain no TODO/pass stubs,
    and meet the minimum lines-of-code threshold for actionable engineering."""
    errors: list[str] = []
    if not code_blocks:
        return ["B3 (Code Gate): report contains 0 runnable ```python``` code blocks"]

    total_loc = 0
    for idx, code in enumerate(code_blocks, 1):
        lines = [ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        total_loc += len(lines)
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            errors.append(f"B3 (Code Gate): syntax error in python block #{idx} (line {e.lineno}): {e.msg}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    errors.append(f"B3 (Code Gate): empty `pass` stub in `{node.name}` (block #{idx}); write full implementation")
                elif (
                    len(node.body) == 1
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and node.body[0].value.value is Ellipsis
                ):
                    errors.append(f"B3 (Code Gate): ellipsis `...` stub in `{node.name}` (block #{idx}); write full implementation")

        if re.search(r"\b(?:TODO|FIXME|PLACEHOLDER|INSERT_CODE_HERE)\b", code, re.I):
            errors.append(f"B3 (Code Gate): placeholder marker found in python block #{idx}")

    if total_loc < min_loc:
        errors.append(f"B3 (Code Gate): runnable Python code has {total_loc} non-comment lines; need >= {min_loc} LOC")
    return errors



# B6: Biotech / Clinical Endpoint & Preclinical Extrapolation Patterns
PRECLINICAL_ONLY_RE = re.compile(
    r"\b(?:murine\s+model|mouse\s+model|mice\s+cohort|in[- ]vitro\s+assay|cell\s+culture\s+only|rat\s+model)\b",
    re.I,
)
SUBGROUP_PHACK_RE = re.compile(
    r"\b(?:post[- ]hoc\s+subgroup|exploratory\s+subgroup|unadjusted\s+p[- ]value)\b",
    re.I,
)
ALLOWED_CLINICAL_ENDPOINTS = {"hard_clinical", "fda_validated_surrogate"}

# B7: Legal / Tax Normative Hierarchy & Jurisdiction Mixing Patterns
US_TAX_MARKERS_RE = re.compile(r"\b(?:IRC\s*§?\s*\d+|Section\s+1256|Section\s+174|Subchapter\s+S|IRS\s+Notice)\b", re.I)
BG_TAX_MARKERS_RE = re.compile(r"\b(?:ЗДДФЛ|ЗКПО|НАП|ЕООД|ДОПК|осигурителен\s+доход)\b", re.I)
ALLOWED_AUTHORITY_TIERS = {"binding_statute", "appellate_precedent", "administrative_guidance"}

# B8: Hardware / Deep Tech Physical Limit Tiers
ALLOWED_PHYSICAL_LIMITS = {
    "carnot_efficiency",
    "shockley_queisser_pv",
    "shannon_hartley_capacity",
    "gravimetric_energy_density_wh_kg",
    "landauer_erasure_bound",
    "betz_wind_limit",
}


def run_b6_to_b8_domain_filters(
    report_text: str,
    manifest: dict[str, Any],
    model_env: dict[str, float],
) -> tuple[list[str], list[str]]:
    """Enforces Rules B6 (Biotech/Clinical), B7 (Legal/Tax), and B8 (Hardware/DeepTech)."""
    failures: list[str] = []
    warnings: list[str] = []
    domain = str(manifest.get("domain", "general")).lower().strip()
    verdict = normalize_verdict(manifest.get("verdict", ""))
    low_text = report_text.lower()

    # -------------------------------------------------------------------------
    # RULE B6: Biotech / Pharma / Clinical / Longevity Physics
    # -------------------------------------------------------------------------
    if domain in ("biotech", "pharma", "medicine", "clinical", "longevity"):
        cphys = manifest.get("clinical_physics", {}) or {}
        if not isinstance(cphys, dict):
            cphys = {}
        ep_type = str(cphys.get("endpoint_type", "")).lower().strip()
        trial_phase = safe_int(cphys.get("trial_phase", 0), default=0)
        if trial_phase is None:
            failures.append(
                f"B6 (Malformed Trial Phase): `clinical_physics.trial_phase` = "
                f"{cphys.get('trial_phase')!r} must be an integer"
            )
            trial_phase = 0

        if ep_type not in ALLOWED_CLINICAL_ENDPOINTS:
            failures.append(
                f"B6 (Endpoint Rigor): `clinical_physics.endpoint_type`={ep_type!r} must be in "
                f"{sorted(ALLOWED_CLINICAL_ENDPOINTS)} (no unvalidated surrogate conflation)"
            )
        if PRECLINICAL_ONLY_RE.search(report_text) and trial_phase < 1 and verdict in POSITIVE_VERDICTS:
            failures.append(
                "B6 (Preclinical Translation Trap): report extrapolates murine/in-vitro preclinical data "
                "to a positive clinical verdict (`trial_phase < 1`)"
            )
        req_bio_vars = ("shrunk_effect_size", "discontinuation_rate_pct")
        missing_bio = [v for v in req_bio_vars if v not in model_env]
        if missing_bio:
            failures.append(
                f"B6 (Clinical Power & Attrition): `python:model` is missing mandatory clinical variables: "
                f"{', '.join(missing_bio)}"
            )
        elif (safe_number(model_env.get("discontinuation_rate_pct"), 0.0) or 0.0) > 25.0 and verdict == "GO":
            failures.append(
                f"B6 (Tolerability Gate): `discontinuation_rate_pct` is "
                f"{model_env['discontinuation_rate_pct']:.1f}% (> 25.0% threshold) with a GO verdict"
            )
        if SUBGROUP_PHACK_RE.search(report_text) and "bonferroni_alpha" not in model_env and "adjusted_p_value" not in model_env:
            failures.append(
                "B6 (Multiplicity / p-Hacking Gate): post-hoc/exploratory subgroup claim requires "
                "`bonferroni_alpha` or `adjusted_p_value` in `python:model`"
            )

    # -------------------------------------------------------------------------
    # RULE B7: Legal / Tax / Regulatory Normative Hierarchy & Jurisdiction Gate
    # -------------------------------------------------------------------------
    if domain in ("law", "legal", "tax", "regulatory", "compliance"):
        nphys = manifest.get("normative_physics", {}) or {}
        if not isinstance(nphys, dict):
            nphys = {}
        auth_tier = str(nphys.get("authority_tier", "")).lower().strip()
        jurisdiction = str(nphys.get("jurisdiction", "")).strip()
        statute = str(nphys.get("primary_statute", "")).strip()

        if not jurisdiction or not statute or auth_tier not in ALLOWED_AUTHORITY_TIERS:
            failures.append(
                f"B7 (Normative Hierarchy): `normative_physics` must declare `jurisdiction`, "
                f"`primary_statute`, and `authority_tier` in {sorted(ALLOWED_AUTHORITY_TIERS)}"
            )
        if auth_tier == "administrative_guidance" and verdict == "GO" and "revocation_risk_haircut" not in model_env:
            failures.append(
                "B7 (Sub-Statutory Guidance Trap): relying on non-binding `administrative_guidance` for a GO "
                "verdict requires `revocation_risk_haircut` in `python:model`"
            )
        if US_TAX_MARKERS_RE.search(report_text) and BG_TAX_MARKERS_RE.search(report_text):
            # v10.0: a free-text "treaty" keyword anywhere is not a legal basis.
            # Require an explicit, structured treaty article in the manifest.
            treaty_article = str((manifest.get("normative_physics") or {}).get("treaty_article", "")).strip()
            if not treaty_article:
                failures.append(
                    "B7 (Jurisdiction Conflation): mixes US IRC tax rules and Bulgarian ЗДДФЛ/ЗКПО "
                    "statutes without declaring `normative_physics.treaty_article` "
                    "(an explicit Double Tax Treaty / СИДДО article). A passing mention of the "
                    "word 'treaty' in prose is not a mapped legal basis"
                )
        req_tax_vars = ("effective_tax_rate_pct", "net_after_tax_savings")
        missing_tax = [v for v in req_tax_vars if v not in model_env]
        if missing_tax:
            failures.append(
                f"B7 (Tax Friction Math): `python:model` is missing mandatory tax-economics variables: "
                f"{', '.join(missing_tax)}"
            )

    # -------------------------------------------------------------------------
    # RULE B8: Hardware / Deep Tech / Energy Thermodynamic & BOM Scaling Physics
    # -------------------------------------------------------------------------
    if domain in ("hardware", "deeptech", "energy", "semiconductors", "robotics"):
        plim = manifest.get("physical_limits", {}) or {}
        if not isinstance(plim, dict):
            plim = {}
        lim_name = str(plim.get("limit_name", "")).lower().strip()
        if lim_name not in ALLOWED_PHYSICAL_LIMITS:
            failures.append(
                f"B8 (First-Principles Physics): `physical_limits.limit_name`={lim_name!r} must be in "
                f"{sorted(ALLOWED_PHYSICAL_LIMITS)}"
            )
        req_hw_vars = ("thermodynamic_headroom_ratio", "bom_unit_cost_usd", "first_pass_yield_pct")
        missing_hw = [v for v in req_hw_vars if v not in model_env]
        if missing_hw:
            failures.append(
                f"B8 (Hardware & BOM Physics): `python:model` is missing mandatory deep-tech variables: "
                f"{', '.join(missing_hw)}"
            )
        else:
            # v10.0: NaN/Inf must be rejected explicitly. `nan > 0.95` and
            # `nan <= 0.0` are both False, so v9.0 let NaN pass this gate.
            ratio = safe_number(model_env["thermodynamic_headroom_ratio"])
            if ratio is None or not (0.0 < ratio <= 0.95):
                failures.append(
                    f"B8 (Thermodynamic Violation): `thermodynamic_headroom_ratio` is "
                    f"{model_env['thermodynamic_headroom_ratio']!r} "
                    f"(must be a finite value in (0.0, 0.95] of theoretical physical limit)"
                )
    return failures, warnings



# ---------------------------------------------------------------------------
# RULE B9: Temporal Recency & SOTA Benchmark Grounding
# ---------------------------------------------------------------------------
DEPRECATED_TECHNOLOGY_MODELS = {
    "bloomberggpt": "BloombergGPT (2023) is a deprecated domain model, surpassed by frontier generalist models.",
    "fingpt": "FinGPT (2023) is an obsolete 7B model, surpassed by current frontier reasoning architectures.",
    "gpt-3.5": "GPT-3.5 is deprecated legacy infrastructure.",
    "gpt-4-0613": "GPT-4-0613 is obsolete 2023 infrastructure.",
}

FRONTIER_SUPERIORITY_KEYWORDS = re.compile(r"(?:най[- ]доб(?:ър|р\w*)|best\s+(?:ai\s+)?model|sota|state-of-the-art|#1\s+model|номер\s+едно|водещ\w*\s+модел)", re.I)

# Independent Tier-2 benchmark publishers. A vendor's own blog is not Tier 2.
BENCHMARK_SOURCE_HOSTS = (
    "artificialanalysis.ai", "lmarena.ai", "chat.lmsys.org", "lmsys.org", "swebench.com",
)
BENCHMARK_QUOTE_MARKERS = (
    "artificial analysis", "lmsys", "lm arena", "swe-bench", "leaderboard",
    "rank 1", "rank 2", "score:",
)
SURPASSED_MARKERS = (
    "obsolete", "deprecated", "surpassed", "остарял", "изместен", "неконкурентен",
    "динозавър", "legacy", "от 2023", "от 2024", "предишно поколение",
)


def run_b9_temporal_and_benchmark_filter(
    report_text: str,
    manifest: dict[str, Any],
    model_env: dict[str, float],
    verified_evidence_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Enforce Rule B9: temporal recency & measured-benchmark grounding.

    v10.0 is **claim-triggered**: B9 fires whenever the report makes a SOTA /
    best-model claim or names a deprecated model, *independent of the manifest
    domain*. v9.0 gated it on ``tech/software/ai/hardware/finance`` while
    ``auto_spec.classify_prompt_domain`` could only emit quant/saas/biotech/
    legal/deeptech -- so B9 was effectively unreachable in the real pipeline.
    """
    failures: list[str] = []
    warnings: list[str] = []
    raw_evidence = manifest.get("evidence", []) or []
    evidence_list = [e for e in raw_evidence if isinstance(e, dict)] if isinstance(raw_evidence, list) else []

    sota_claims = list(FRONTIER_SUPERIORITY_KEYWORDS.finditer(report_text))
    deprecated_mentions: list[tuple[str, re.Match[str]]] = []
    for dep_model in DEPRECATED_TECHNOLOGY_MODELS:
        deprecated_mentions.extend(
            (dep_model, m) for m in re.finditer(re.escape(dep_model), report_text, re.I)
        )

    if not sota_claims and not deprecated_mentions:
        return failures, warnings

    # 1. Deprecated models must carry a LOCAL obsolescence disclaimer.
    for dep_model, match in deprecated_mentions:
        if not is_mitigated_locally(
            report_text, match.start(), terms=SURPASSED_MARKERS, window=200
        ):
            failures.append(
                f"B9 (Deprecated Dinosaur SOTA Trap): cites {dep_model!r} without locally "
                f"marking it obsolete/surpassed. {DEPRECATED_TECHNOLOGY_MODELS[dep_model]}"
            )

    # 2. SOTA / comparative claims require a VERIFIED Tier-2 measured benchmark.
    if sota_claims:
        grounded_ids: list[str] = []
        for ev in evidence_list:
            eid = str(ev.get("id", ""))
            if verified_evidence_ids is not None and eid not in verified_evidence_ids:
                # A self-declared quote in the manifest is not evidence.
                continue
            quote = str(ev.get("quote", "")).lower()
            locator = (str(ev.get("source", "")) + " " + str(ev.get("source_url", ""))).lower()
            if any(mk in quote for mk in BENCHMARK_QUOTE_MARKERS) or any(
                host in locator for host in BENCHMARK_SOURCE_HOSTS
            ):
                grounded_ids.append(eid or "<unnamed>")

        if not grounded_ids:
            suffix = (
                " No manifest evidence quote has been verified verbatim against an immutable "
                "SHA-256 snapshot." if verified_evidence_ids is not None else ""
            )
            failures.append(
                "B9 (Uncalibrated SOTA Claim): declares 'best model / SOTA leader' without a "
                "verified independent Tier 2 measured benchmark (Artificial Analysis Index, "
                "LMSYS/LM Arena, SWE-bench). Marketing claims and pre-2025 academic papers "
                f"do not ground a comparative superiority claim.{suffix}"
            )
    return failures, warnings

def run_b10_dialectical_filter(
    report_text: str,
    manifest: dict[str, Any],
    arbitration_out: dict[str, Any] | None = None,
    verified_evidence_ids: set[str] | None = None,
    pooled_subjects: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """v11.0 Rule B10: de_jure vs de_facto Dialectical Reconciliation Matrix.

    Implemented in :mod:`dialectical_arbitration` (kept separate from the
    pre-existing v5.0 ``dialectics.py`` claim-ledger CLI). The full matrix is
    copied into ``arbitration_out`` so ``lean_engine`` can cap confidence at
    Medium without re-running the arbitration.
    """
    from dr_engine.tools.dialectical_arbitration import run_b10_dialectical_arbitration

    fails, warns, matrix = run_b10_dialectical_arbitration(
        report_text, manifest,
        verified_evidence_ids=verified_evidence_ids,
        pooled_subjects=pooled_subjects,
    )
    if isinstance(arbitration_out, dict):
        arbitration_out.clear()
        arbitration_out.update(matrix)
    return fails, warns


def run_v9_bullshit_filters(
    report_text: str,
    manifest: dict[str, Any],
    model_env: dict[str, float],
    verified_evidence_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Runs deterministic filters B1-B9. Returns ``(failures, warnings)``.

    ``verified_evidence_ids`` is supplied by the verification stage: only these
    IDs have had their quotes checked verbatim against immutable snapshots.
    When present, B9 cannot be satisfied by an unverified manifest quote.
    """
    failures: list[str] = []
    warnings: list[str] = []
    domain = str(manifest.get("domain", "general")).lower().strip()
    verdict = normalize_verdict(manifest.get("verdict", ""))
    low_text = report_text.lower()

    # -------------------------------------------------------------------------
    # RULE B1: The "No Fake EV" & Unit Breakeven Law
    # -------------------------------------------------------------------------
    # v10.0: `n=30` buried in an appendix no longer disarms B1. Each fake-EV
    # trigger must carry its OWN local empirical sample size, and n must be >= 30.
    uncalibrated = unmitigated_spans(
        report_text, FAKE_EV_PROB_RE,
        mitigation_re=EMPIRICAL_N_RE, validator=_n_at_least_30, window=200,
    )
    if uncalibrated:
        sample = ", ".join(repr(t[1][:48]) for t in uncalibrated[:2])
        failures.append(
            "B1 (No Fake EV): report uses uncalibrated subjective scenario probabilities "
            f"(e.g. {sample}) without a locally attached empirical sample size (n >= 30). "
            "An `n=...` in an unrelated section does not calibrate an EV table. "
            "Replace subjective EV with deterministic Unit Breakeven & Churn Replacement math."
        )

    if domain in ("product", "saas", "b2b"):
        req_vars = ("required_clients_breakeven", "monthly_churn_replacements")
        missing_vars = [v for v in req_vars if v not in model_env]
        if missing_vars:
            failures.append(
                f"B1 (Unit Breakeven): SaaS/Product `python:model` is missing mandatory unit-economics "
                f"variables: {', '.join(missing_vars)}"
            )

    # -------------------------------------------------------------------------
    # RULE B2: Zero-Liability Solo Operational Physics (Product / SaaS)
    # -------------------------------------------------------------------------
    if domain in ("product", "saas", "b2b"):
        arch_mode = str(manifest.get("architecture_mode", "")).lower().strip()
        if arch_mode not in ALLOWED_SOLO_ARCHITECTURES:
            failures.append(
                f"B2 (Operational Physics): manifest `architecture_mode`={arch_mode!r} is not in "
                f"allowed zero-liability solo patterns {sorted(ALLOWED_SOLO_ARCHITECTURES)}"
            )
        if verdict in POSITIVE_VERDICTS:
            # v10.0: the rejection must be attached to EACH mutating proposal.
            # A single "avoid" anywhere in the report no longer disarms B2.
            unmitigated = unmitigated_spans(
                report_text, MUTATING_LIABILITY_RE,
                terms=("rejected", "reject", "avoid", "do not build", "we will not", "read-only instead"),
                window=200,
            )
            if unmitigated:
                sample = ", ".join(repr(t[1][:48]) for t in unmitigated[:2])
                failures.append(
                    f"B2 (Operational Physics): proposes high-liability mutating architecture "
                    f"({sample}) without rejecting it locally in favor of a Read-Only / "
                    f"Preflight / BYOD design"
                )

    # -------------------------------------------------------------------------
    # RULE B3: Modern Microstructure, Jacobian Friction Gate & Runnable Code (Quant)
    # -------------------------------------------------------------------------
    if domain in ("quant", "finance", "trading", "microstructure"):
        cp = manifest.get("counterparty_physics", {}) or {}
        if not isinstance(cp, dict):
            cp = {}
        if not cp.get("forced_actor"):
            failures.append("B3 (Microstructure Physics): `counterparty_physics.forced_actor` is missing")

        sample_end = safe_int(cp.get("sample_end_year", 0))
        if sample_end is None:
            failures.append(
                f"B3 (Malformed Sample Period): `counterparty_physics.sample_end_year` = "
                f"{cp.get('sample_end_year')!r} is not an integer year; modern-survival cannot be certified"
            )
        elif sample_end < 2023:
            failures.append(
                f"B3 (Anti-Textbook Decay): `counterparty_physics.sample_end_year` is {sample_end} (< 2023); "
                f"strategies must prove survival on modern 2023-2026 market structure"
            )

        # v10.0: one "refuted" in an unrelated chapter no longer disarms every
        # anomaly. Each decayed-anomaly mention needs its OWN local refutation.
        anomaly_mitigations = ("refuted", "decayed", "dead", "killed", "invalidated", "опроверган", "failed")
        for anomaly, reason in REFUTED_TEXTBOOK_ANOMALIES.items():
            hits = unmitigated_spans(
                report_text, re.compile(re.escape(anomaly), re.I),
                terms=anomaly_mitigations, window=220,
            )
            if hits:
                failures.append(
                    f"B3 (Textbook Alpha Trap): mentions refuted anomaly {anomaly!r} "
                    f"without locally refuting it ({reason})"
                )

        # Check Jacobian Friction Tipping Point: Friction / 1R Stop <= 3.0% (0.030)
        fric_share = safe_number(model_env.get("friction_share_of_1r"))
        fallback_edge = (
            safe_number(cp.get("gross_edge_bp"), 0.0) or 0.0
        ) - (safe_number(cp.get("friction_cost_bp"), 0.0) or 0.0)
        net_edge = safe_number(model_env.get("net_alpha_bp"), fallback_edge)
        if fric_share is None:
            failures.append(
                "B3 (Jacobian Friction Gate): `python:model` must compute a finite "
                "`friction_share_of_1r = total_friction_bp / stop_1r_bp` (NaN/Inf rejected)"
            )
        elif fric_share > 0.030 and verdict in POSITIVE_VERDICTS:
            failures.append(
                f"B3 (Jacobian Friction Gate): `friction_share_of_1r` is {fric_share:.1%} (> 3.0% tipping point) "
                f"yet verdict is {verdict!r}; must be NO-GO / KILL or widen structural horizon"
            )
        if net_edge is None:
            failures.append("B3 (Net Expectancy Gate): net edge is not a finite number")
        elif net_edge <= 0 and verdict not in NEGATIVE_VERDICTS:
            failures.append(f"B3 (Net Expectancy Gate): net edge is {net_edge:.2f} bp (<= 0) without a NO-GO/KILL verdict")

        code_blocks = extract_fenced_python_code(report_text)
        failures.extend(verify_runnable_code_blocks(code_blocks, min_loc=35))

    # -------------------------------------------------------------------------
    # RULE B4: The "ChatGPT Wrapper" Falsification Test (Product / SaaS)
    # -------------------------------------------------------------------------
    if domain in ("product", "saas", "b2b"):
        cgpt = manifest.get("chatgpt_falsification", {})
        mech = str(cgpt.get("mechanism", "")).lower().strip()
        why_fails = str(cgpt.get("why_raw_llm_fails", "")).strip()
        if mech not in STRUCTURAL_MOAT_MECHANISMS or len(why_fails) < 40:
            failures.append(
                f"B4 (ChatGPT Falsification): manifest `chatgpt_falsification` must declare a valid "
                f"`mechanism` in {sorted(STRUCTURAL_MOAT_MECHANISMS)} and a concrete `why_raw_llm_fails` (>= 40 chars)"
            )

    # -------------------------------------------------------------------------
    # RULE B5: WTP vs. Complaint Separation & 14-Day Demand Test
    # -------------------------------------------------------------------------
    if domain in ("product", "saas", "b2b"):
        for ev in manifest.get("evidence", []):
            if ev.get("kind") == "review_pain" and ev.get("proves") == "willingness_to_pay_new_entrant":
                failures.append(
                    f"B5 (WTP Conflation): {ev.get('id')} is a complaint quote (`review_pain`); "
                    f"complaints prove `incumbent_weakness`, NEVER `willingness_to_pay_new_entrant`"
                )
        dtest = manifest.get("demand_test_14d", {}) or {}
        threshold = safe_number(dtest.get("pass_threshold_count")) if isinstance(dtest, dict) else None
        if not dtest.get("protocol") or threshold is None or threshold <= 0:
            failures.append(
                "B5 (14-Day Falsifiable Test): manifest `demand_test_14d` must define `protocol` "
                "and a finite positive numeric `pass_threshold_count` (no passive 'HOLD' paralysis)"
            )

    f_ext, w_ext = run_b6_to_b8_domain_filters(report_text, manifest, model_env)
    failures.extend(f_ext)
    warnings.extend(w_ext)
    f_b9, w_b9 = run_b9_temporal_and_benchmark_filter(
        report_text, manifest, model_env, verified_evidence_ids=verified_evidence_ids
    )
    failures.extend(f_b9)
    warnings.extend(w_b9)
    return failures, warnings


def _selftest() -> int:
    # 1. Verify that a flawed SaaS report (Fake EV + 2-Way Sync + No ChatGPT moat) is caught by B1, B2, B4, B5
    bad_report = """# Bad SaaS Report
| Scenario | Win Prob | Payoff |
| **Base** | 15% | $10,000 |
We will build a two-way real-time sync that overwrites inventory across channels.
"""
    bad_manifest = {"domain": "saas", "verdict": "GO", "architecture_mode": "mutating_write_sync"}
    f_bad, _ = run_v9_bullshit_filters(bad_report, bad_manifest, {})
    assert any("B1 (No Fake EV)" in x for x in f_bad), f"Missed B1: {f_bad}"
    assert any("B2 (Operational Physics)" in x for x in f_bad), f"Missed B2: {f_bad}"
    assert any("B4 (ChatGPT Falsification)" in x for x in f_bad), f"Missed B4: {f_bad}"
    assert any("B5 (14-Day Falsifiable Test)" in x for x in f_bad), f"Missed B5: {f_bad}"

    # 2. Verify that a compliant Quant report with modern microstructure, <3% friction/1R, and runnable code passes
    good_quant_report = """# US100 0DTE Gamma Pinning & Cash-Close Imbalance Engine
```python
import math

class ZeroDTEGammaExecutionEngine:
    def __init__(self, stop_bp: float, spread_bp: float, slip_bp: float):
        self.stop_bp = stop_bp
        self.spread_bp = spread_bp
        self.slip_bp = slip_bp

    def friction_ratio(self) -> float:
        total_rt = self.spread_bp + 2.0 * self.slip_bp
        return total_rt / self.stop_bp if self.stop_bp > 0 else 1.0

    def evaluate_bar(self, net_gex_bn: float, moc_imbalance_mm: float, vol_bps: float) -> dict:
        ratio = self.friction_ratio()
        if ratio > 0.030:
            return {"signal": 0, "reason": "FRICTION_KILL_GATE"}
        if net_gex_bn <= -2.5 and abs(moc_imbalance_mm) >= 500.0:
            direction = 1 if moc_imbalance_mm > 0 else -1
            expected_gross = 0.42 * vol_bps
            net_ev = expected_gross - (self.spread_bp + 2.0 * self.slip_bp)
            if net_ev > 2.5:
                return {"signal": direction, "net_ev_bp": round(net_ev, 2), "stop_bp": self.stop_bp}
        return {"signal": 0, "reason": "NO_FORCED_FLOW"}

    def position_contracts(self, equity_usd: float, risk_pct: float, point_val: float, stop_pts: float) -> int:
        if stop_pts <= 0 or point_val <= 0:
            return 0
        dollar_risk = equity_usd * risk_pct
        return max(0, int(math.floor(dollar_risk / (stop_pts * point_val))))

    def is_regular_trading_hours(self, hour: int, minute: int) -> bool:
        minute_of_day = hour * 60 + minute
        return 570 <= minute_of_day <= 960

    def compute_daily_pnl_bps(self, gross_move_pts: float, point_val: float, stop_pts: float) -> float:
        ratio = self.friction_ratio()
        if ratio > 0.030:
            return 0.0
        gross_bps = (gross_move_pts / stop_pts) * self.stop_bp
        net_bps = gross_bps - (self.spread_bp + 2.0 * self.slip_bp)
        return round(net_bps, 2)
```
"""
    good_quant_manifest = {
        "domain": "quant",
        "verdict": "CONDITIONAL_GO",
        "counterparty_physics": {
            "forced_actor": "Short-gamma 0DTE options market makers delta-hedging into MOC imbalance",
            "sample_end_year": 2026,
            "gross_edge_bp": 8.4,
            "friction_cost_bp": 2.4,
        },
    }
    good_env = {"friction_share_of_1r": 0.024, "net_alpha_bp": 6.0}
    f_good, _ = run_v9_bullshit_filters(good_quant_report, good_quant_manifest, good_env)
    assert not f_good, f"Expected 0 failures on compliant quant report, got: {f_good}"
    # 3. Verify Rule B6 (Biotech/Clinical)
    bad_bio_report = "Murine model showed complete remission in mice cohort."
    bad_bio_manifest = {"domain": "biotech", "verdict": "GO", "clinical_physics": {"endpoint_type": "biomarker_only", "trial_phase": 0}}
    f_bio, _ = run_v9_bullshit_filters(bad_bio_report, bad_bio_manifest, {})
    assert any("B6 (Endpoint Rigor)" in x for x in f_bio)
    assert any("B6 (Preclinical Translation Trap)" in x for x in f_bio)
    assert any("B6 (Clinical Power & Attrition)" in x for x in f_bio)

    # 4. Verify Rule B7 (Legal/Tax)
    bad_tax_report = "Using Section 1256 and Bulgarian ЗДДФЛ for trading gains."
    bad_tax_manifest = {"domain": "tax", "verdict": "GO", "normative_physics": {"jurisdiction": "BG", "primary_statute": "ЗДДФЛ", "authority_tier": "administrative_guidance"}}
    f_tax, _ = run_v9_bullshit_filters(bad_tax_report, bad_tax_manifest, {})
    assert any("B7 (Sub-Statutory Guidance Trap)" in x for x in f_tax)
    assert any("B7 (Jurisdiction Conflation)" in x for x in f_tax)
    assert any("B7 (Tax Friction Math)" in x for x in f_tax)

    # 5. Verify Rule B8 (Hardware/DeepTech)
    bad_hw_manifest = {"domain": "deeptech", "verdict": "GO", "physical_limits": {"limit_name": "carnot_efficiency"}}
    bad_hw_env = {"thermodynamic_headroom_ratio": 0.99, "bom_unit_cost_usd": 150.0, "first_pass_yield_pct": 85.0}
    f_hw, _ = run_v9_bullshit_filters("# Carnot Engine", bad_hw_manifest, bad_hw_env)
    assert any("B8 (Thermodynamic Violation)" in x for x in f_hw)

    # 6. Verify Rule B9 (Temporal Recency & Benchmark Grounding)
    bad_ai_report = "# Най-добрият AI модел за финанси е BloombergGPT\nТой превъзхожда всички други модели."
    bad_ai_manifest = {"domain": "ai", "verdict": "GO", "evidence": []}
    f_ai, _ = run_v9_bullshit_filters(bad_ai_report, bad_ai_manifest, {})
    assert any("B9 (Deprecated Dinosaur SOTA Trap)" in x for x in f_ai), f"Missed dinosaur trap: {f_ai}"
    assert any("B9 (Uncalibrated SOTA Claim)" in x for x in f_ai), f"Missed uncalibrated SOTA: {f_ai}"

    good_ai_report = "# Най-добрият AI модел за финанси е Gemini 4 Carbon с резултат 63 [E001]\nBloombergGPT е остарял модел от 2023."
    good_ai_manifest = {
        "domain": "ai",
        "verdict": "GO",
        "evidence": [{"id": "E001", "source": "S001", "quote": "Rank 1: Gemini 4 Carbon (high) - Overall Score: 63 on Artificial Analysis"}]
    }
    f_good_ai, _ = run_v9_bullshit_filters(good_ai_report, good_ai_manifest, {})
    assert not any("B9" in x for x in f_good_ai), f"Unexpected B9 failure on compliant report: {f_good_ai}"

    print("[SELFTEST PASS] All v10.0 Bullshit Filters (B0-B9, scoped + fail-closed) verified.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
