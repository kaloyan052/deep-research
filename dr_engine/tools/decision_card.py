#!/usr/bin/env python3
"""Deep Research Engine v9.0 — AST-to-JavaScript Interactive Decision Card Compiler.

Compiles a verified study directory (`report.md` + `sources/index.jsonl`) into a
zero-dependency, single-file HTML5 Decision Card (`decision_card.html`) featuring:
  1. AST-to-JS Transpilation of all `python:model` blocks:
     - Exogenous constants (`var = 8.4`) become live interactive stress-test sliders.
     - Endogenous formulas (`var = expr`) recompute in real time (< 1 ms) in the browser,
       including all `lean_engine.py` built-in microstructure helpers (`net_edge_bp`,
       `hold_cost_bp`, `sharpe_annual`, `kelly_half`, `wilson_lower_95`).
  2. Exact Numerical Jacobian Elasticity (dY/Y / dX/X) & Break-Even Tipping Points.
  3. Expandable SHA-256 Cryptographic Evidence & Popperian Kill-Hypothesis Ledger.

Pure Python 3.10+ stdlib. Zero external JS/CSS CDNs (100% air-gapped offline HTML).
Windows cp1252-safe.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import math
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.lean_engine import (
    _eval_ast_node,
    _extract_embedded_blocks,
    execute_model_block,
    verify_study,
)


@dataclass
class InputParameter:
    name: str
    default_val: float
    min_val: float
    max_val: float
    step_val: float
    model_id: str


@dataclass
class DerivedMetric:
    name: str
    baseline_val: float
    js_expr: str
    py_expr: str
    model_id: str
    elasticities: dict[str, float] = field(default_factory=dict)
    breakeven_bounds: dict[str, float] = field(default_factory=dict)
    # v10.0: which tipping points were solved exactly (bisection) vs. by the
    # legacy first-order Newton extrapolation used when no sign change exists.
    breakeven_exact: dict[str, bool] = field(default_factory=dict)
    # Populated by compute_monte_carlo() at render time (not at compile time,
    # keeping the <50 ms compiler selftest budget intact).
    monte_carlo: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Python `ast` -> JavaScript Expression Transpiler
# ---------------------------------------------------------------------------
JS_BINOP_MAP = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "Math.floor_div",
    ast.Mod: "%",
    ast.Pow: "**",
}

JS_FUNC_MAP = {
    "abs": "Math.abs",
    "min": "Math.min",
    "max": "Math.max",
    "round": "dr_round",
    "sum": "dr_sum",
    "sqrt": "Math.sqrt",
    "log": "Math.log",
    "log10": "Math.log10",
    "exp": "Math.exp",
    "hold_cost_bp": "hold_cost_bp",
    "net_edge_bp": "net_edge_bp",
    "sharpe_annual": "sharpe_annual",
    "kelly_half": "kelly_half",
    "wilson_lower_95": "wilson_lower_95",
}


def _ast_expr_to_js(node: ast.AST) -> str:
    """Recursively transpiles a safe Python AST expression node into clean JavaScript."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return repr(float(node.value))
        raise ValueError(f"Unsupported constant in JS transpiler: {node.value!r}")
    if isinstance(node, ast.Name):
        return f"env.{node.id}"
    if isinstance(node, ast.UnaryOp):
        operand_js = _ast_expr_to_js(node.operand)
        if isinstance(node.op, ast.USub):
            return f"(-({operand_js}))"
        if isinstance(node.op, ast.UAdd):
            return f"(+({operand_js}))"
        raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left_js = _ast_expr_to_js(node.left)
        right_js = _ast_expr_to_js(node.right)
        if isinstance(node.op, ast.FloorDiv):
            return f"Math.floor(({left_js}) / ({right_js}))"
        op_str = JS_BINOP_MAP.get(type(node.op))
        if not op_str:
            raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
        return f"(({left_js}) {op_str} ({right_js}))"
    if isinstance(node, (ast.List, ast.Tuple)):
        elts_js = ", ".join(_ast_expr_to_js(e) for e in node.elts)
        return f"[{elts_js}]"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn_name = node.func.id
        js_fn = JS_FUNC_MAP.get(fn_name)
        if not js_fn:
            raise ValueError(f"Unsupported function in JS transpiler: {fn_name}")
        args_js = [_ast_expr_to_js(a) for a in node.args]
        return f"{js_fn}({', '.join(args_js)})"
    raise ValueError(f"Unsupported AST node in JS transpiler: {type(node).__name__}")


def _is_literal_number_node(node: ast.AST) -> float | None:
    """Returns float value if `node` is a numeric literal (`8.4` or `-2.5`), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.USub, ast.UAdd))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        val = float(node.operand.value)
        return -val if isinstance(node.op, ast.USub) else val
    return None


def _slider_domain_for_value(val: float) -> tuple[float, float, float]:
    """Computes ergonomic (min_val, max_val, step_val) for an interactive slider."""
    if val == 0.0:
        return (-10.0, 10.0, 0.1)
    mag = abs(val)
    if val > 0:
        lo = round(0.1 * val, 6)
        hi = round(2.5 * val, 6)
    else:
        lo = round(2.5 * val, 6)
        hi = round(0.1 * val, 6)
    step = 10 ** (math.floor(math.log10(mag)) - 2) if mag > 0 else 0.01
    step = max(1e-4, min(step, 10.0))
    return (lo, hi, round(step, 6))


# ---------------------------------------------------------------------------
# 1b. v10.0: Single-parse model evaluator & distribution engine
# ---------------------------------------------------------------------------
class CompiledModel:
    """Evaluate a ``python:model`` program with exogenous overrides, once parsed.

    ``execute_model_block`` re-parses the source on every call, which is fine
    for a handful of Jacobian evaluations but wasteful for a Monte Carlo run.
    Exogenous (input) assignments are skipped so the supplied stress values
    remain authoritative; all derived assignments are evaluated in order with
    the engine's own sandboxed AST evaluator (no ``eval``, no builtins).
    """

    def __init__(self, full_code: str, input_defaults: dict[str, float]):
        tree = ast.parse(full_code, mode="exec")
        self.input_names = set(input_defaults)
        self.baseline = {k: float(v) for k, v in input_defaults.items()}
        self.assignments: list[tuple[str, ast.AST]] = [
            (stmt.targets[0].id, stmt.value)
            for stmt in tree.body
            if isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ]

    def evaluate(self, overrides: dict[str, float]) -> dict[str, float]:
        # All exogenous inputs must be present even when only one is stressed,
        # otherwise derived expressions referencing a sibling input raise.
        env: dict[str, Any] = {**self.baseline, **{k: float(v) for k, v in overrides.items()}}
        for name, node in self.assignments:
            if name in self.input_names:
                continue
            val = _eval_ast_node(node, env)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                env[name] = round(float(val), 6)
            else:
                env[name] = val
        return env


def _solve_breakeven_bisection(
    model: CompiledModel, input_name: str, metric_name: str,
    lo: float, hi: float, max_iter: int = 40, tol: float = 1e-7,
) -> float | None:
    """Locate the true zero crossing by bisection on the executed model.

    v9.0 (and the protocol's own CHANGELOG) claimed bisection but actually used
    a single first-order Newton step ``x* = x0 - y0/(dy/dx)``, which is wrong
    for any non-linear model and can land far outside the slider domain.
    """

    def f(x: float) -> float | None:
        value = model.evaluate({input_name: x}).get(metric_name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return float(value) if math.isfinite(float(value)) else None

    f_lo, f_hi = f(lo), f(hi)
    if f_lo is None or f_hi is None or f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if f_mid is None:
            return None
        if abs(f_mid) < tol or (hi - lo) < 1e-9:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def _lcg_stream(seed: int):
    """Deterministic 31-bit LCG in (0, 1); no external RNG, fully reproducible."""
    state = (seed & 0x7FFFFFFF) or 1
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / 2147483648.0


def compute_monte_carlo(
    full_code: str,
    inputs: list[InputParameter],
    metrics: list[DerivedMetric],
    n_samples: int = 1200,
    sigma_frac: float = 0.10,
    seed: int | None = None,
    correlation: Any | None = None,
    regime: str | None = None,
    sigma_by_input: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Deterministic distributional stress test of every derived metric.

    v10.0 default (``correlation=None``, ``regime=None``): each exogenous input
    is perturbed by an independent truncated Gaussian with σ = 10% of baseline.
    That path is preserved byte-for-byte for reproducibility.

    v11.0 opt-in: when a correlation spec or a named :data:`MACRO_REGIMES`
    entry is supplied, shocks are drawn jointly as ``z_c = L·z + μ_r`` where
    ``Σ = L Lᵀ`` (Cholesky) and ``μ_r`` is the regime's declared mean-shift
    vector. This captures the real physics where friction, latency and
    volatility move together. Every declared correlation, shrinkage repair and
    mean shift is returned in the provenance block for audit.

    No subjective scenario weights are introduced: these are sensitivity
    measurements, not Expected Value guesses (Rule B1 remains intact).

    Returns P5/P50/P95, mean, P(metric < 0), P(metric < baseline), a histogram,
    empirical ``VaR₉₉`` / ``CVaR₉₉``, and fully reproducible provenance.
    """
    if not inputs or not metrics:
        return {"n_samples": 0, "metrics": {}}
    digest = hashlib.sha256(full_code.encode("utf-8")).hexdigest()
    base_seed = seed if seed is not None else int(digest[:8], 16)
    rng = _lcg_stream(base_seed)
    model = CompiledModel(full_code, {i.name: i.default_val for i in inputs})
    baseline = {i.name: i.default_val for i in inputs}
    names = [m.name for m in metrics]
    samples: dict[str, list[float]] = {n: [] for n in names}
    input_names = [i.name for i in inputs]

    # --- v11.0: optional declared correlation structure + regime shifts -----
    from dr_engine.tools.risk_engine import (
        MACRO_REGIMES, build_correlation_matrix, cholesky, correlated_shocks,
        empirical_var_cvar, regime_correlation_spec, regime_mean_shifts,
    )
    regime_spec = MACRO_REGIMES.get(regime) if regime else None
    effective_sigma = sigma_frac * (float(regime_spec["sigma_multiplier"]) if regime_spec else 1.0)
    use_correlated = (correlation is not None) or (regime_spec is not None)
    L: list[list[float]] | None = None
    mu: list[float] | None = None
    corr_info: Any = None

    if use_correlated:
        spec = correlation
        if spec is None and regime_spec is not None:
            spec = regime_correlation_spec(input_names, regime)
        matrix, meta = build_correlation_matrix(input_names, spec or {})
        L, chol_info = cholesky(matrix)
        fallback = False
        if L is None:
            identity = [[1.0 if a == b else 0.0 for b in range(len(input_names))]
                        for a in range(len(input_names))]
            L, chol_info = cholesky(identity, jitter=False)
            fallback = True
        mu = regime_mean_shifts(input_names, regime) if regime_spec else [0.0] * len(input_names)
        corr_info = {
            **meta,
            "matrix": matrix,
            "cholesky": chol_info,
            "fallback_to_identity": fallback,
            "regime": regime,
            "regime_description": (regime_spec or {}).get("description", ""),
            "sigma_multiplier": (regime_spec or {}).get("sigma_multiplier", 1.0),
            "mean_shifts": dict(zip(input_names, mu)),
        }

    for _ in range(n_samples):
        overrides: dict[str, float] = {}
        if L is None:
            # v10.0 default path -- unchanged for reproducibility.
            for inp in inputs:
                u1, u2 = next(rng), next(rng)
                u1 = min(max(u1, 1e-12), 1.0)
                z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
                z = max(-2.0, min(2.0, z))
                perturbed = inp.default_val * (1.0 + sigma_frac * z)
                overrides[inp.name] = min(max(perturbed, inp.min_val), inp.max_val)
        else:
            z: list[float] = []
            for _inp in inputs:
                u1, u2 = next(rng), next(rng)
                u1 = min(max(u1, 1e-12), 1.0)
                zv = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
                z.append(max(-2.0, min(2.0, zv)))
            zc = correlated_shocks(L, z, mu, clamp=3.0)
            for k, inp in enumerate(inputs):
                rel = (sigma_by_input or {}).get(inp.name, 1.0)
                perturbed = inp.default_val * (1.0 + effective_sigma * float(rel) * zc[k])
                overrides[inp.name] = min(max(perturbed, inp.min_val), inp.max_val)
        env = model.evaluate(overrides)
        for name in names:
            v = env.get(name)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
                samples[name].append(float(v))

    out: dict[str, Any] = {}
    for m in metrics:
        vals = sorted(samples.get(m.name, []))
        if not vals:
            continue
        n = len(vals)
        def pct(q: float) -> float:
            idx = min(n - 1, max(0, int(round(q * (n - 1)))))
            return round(vals[idx], 4)
        tail = empirical_var_cvar(vals, alpha=0.99)
        out[m.name] = {
            "n": n,
            "p5": pct(0.05), "p50": pct(0.50), "p95": pct(0.95),
            "mean": round(sum(vals) / n, 4),
            "p_below_zero": round(sum(1 for v in vals if v < 0) / n, 4),
            "p_below_baseline": round(sum(1 for v in vals if v < m.baseline_val) / n, 4),
            "histogram": _histogram_bins(vals),
            "hist_lo": round(vals[0], 4), "hist_hi": round(vals[-1], 4),
            "var_99": tail["var_99"], "cvar_99": tail["cvar_99"],
            "q_tail": tail["q_tail"], "tail_n": tail["tail_n"],
            "var_99_alpha": 0.99,
        }
    return {
        "n_samples": n_samples,
        "sigma_frac": sigma_frac,
        "effective_sigma_frac": round(effective_sigma, 6),
        "seed": base_seed,
        "code_sha256": digest,
        "baseline": baseline,
        "correlation": corr_info,
        "regime": regime,
        "risk_convention": (
            "Y is a gain; VaR99 = -Q0.01(Y), CVaR99 = -E[Y|Y<=Q0.01(Y)]. "
            "Negative VaR means even the 1% worst case is still a gain."
        ),
        "metrics": out,
    }


def _histogram_bins(values: list[float], bins: int = 18) -> list[int]:
    """Compact histogram counts for an inline, CDN-free SVG sparkline."""
    if not values:
        return []
    lo, hi = values[0], values[-1]
    if hi - lo < 1e-12:
        return [len(values)] + [0] * (bins - 1)
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / width))
        counts[idx] += 1
    return counts


def render_histogram_svg(counts: list[int], width: int = 168, height: int = 38) -> str:
    """Render a static inline SVG histogram (no JS library, no CDN)."""
    if not counts:
        return ""
    peak = max(counts) or 1
    n = len(counts)
    bw = width / n
    rects = []
    for i, c in enumerate(counts):
        h = (c / peak) * (height - 2)
        rects.append(
            f'<rect x="{i * bw:.1f}" y="{height - h:.1f}" width="{max(0.8, bw - 0.7):.1f}" '
            f'height="{h:.1f}" fill="#38bdf8" opacity="0.85"/>'
        )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Monte Carlo distribution histogram">'
        f'<line x1="0" y1="{height - 0.5}" x2="{width}" y2="{height - 0.5}" '
        f'stroke="#1f2937" stroke-width="1"/>' + "".join(rects) + "</svg>"
    )


def compute_stress_scenarios(
    full_code: str, inputs: list[InputParameter], metrics: list[DerivedMetric],
) -> list[dict[str, Any]]:
    """Deterministic +/-1 sigma and +/-2 sigma joint stress presets.

    These are *not* subjective scenario weights (Rule B1): they are fixed,
    reproducible perturbations of measured inputs, presented side by side.
    """
    if not inputs:
        return []
    model = CompiledModel(full_code, {i.name: i.default_val for i in inputs})
    presets = [
        ("Baseline", 0.0), ("Adverse (-1s)", -1.0), ("Severe (-2s)", -2.0),
        ("Upside (+1s)", 1.0),
    ]
    rows: list[dict[str, Any]] = []
    for label, k in presets:
        overrides = {
            i.name: min(max(i.default_val * (1.0 + 0.10 * k), i.min_val), i.max_val)
            for i in inputs
        }
        env = model.evaluate(overrides)
        rows.append({
            "scenario": label,
            "values": {
                m.name: round(float(env[m.name]), 4)
                if isinstance(env.get(m.name), (int, float)) and not isinstance(env.get(m.name), bool)
                else None
                for m in metrics
            },
        })
    return rows


def compute_regime_stress_scenarios(
    full_code: str,
    inputs: list[InputParameter],
    metrics: list[DerivedMetric],
    regimes: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic joint macro-regime stress presets (v11.0).

    Unlike subjective Base/Bear/Stress probability weights (forbidden by B1),
    these are declared, reproducible mean-shift vectors applied to correlated
    input families. Each row reports the regime correlation rho, sigma
    multiplier and the value of every derived metric under that regime.
    """
    if not inputs:
        return []
    from dr_engine.tools.risk_engine import MACRO_REGIMES, regime_mean_shifts
    names = list(regimes) if regimes else list(MACRO_REGIMES)
    model = CompiledModel(full_code, {i.name: i.default_val for i in inputs})
    rows: list[dict[str, Any]] = []
    for regime in names:
        spec = MACRO_REGIMES.get(regime)
        if not spec:
            continue
        mu = regime_mean_shifts([i.name for i in inputs], regime)
        overrides = {
            inp.name: min(
                max(inp.default_val * (1.0 + 0.10 * float(spec["sigma_multiplier"]) * mu[k]),
                    inp.min_val),
                inp.max_val,
            )
            for k, inp in enumerate(inputs)
        }
        env = model.evaluate(overrides)
        rows.append({
            "regime": regime,
            "description": spec["description"],
            "group_rho": spec["group_rho"],
            "sigma_multiplier": spec["sigma_multiplier"],
            "shocked_inputs": [inputs[k].name for k, v in enumerate(mu) if v],
            "values": {
                m.name: round(float(env[m.name]), 4)
                if isinstance(env.get(m.name), (int, float)) and not isinstance(env.get(m.name), bool)
                else None
                for m in metrics
            },
        })
    return rows


def render_risk_svg(
    metric_summary: dict[str, Any],
    width: int = 260,
    height: int = 66,
) -> str:
    """Inline SVG risk canvas: histogram + VaR99 line + CVaR tail shading.

    Pure static SVG, zero CDN, zero JavaScript. Bins to the left of the
    empirical 1% quantile are coloured as the loss tail (red); bins between
    VaR and CVaR are amber; the remainder is the normal region.
    """
    counts = metric_summary.get("histogram") or []
    if not counts:
        return ""
    lo = float(metric_summary.get("hist_lo", 0.0))
    hi = float(metric_summary.get("hist_hi", 1.0))
    span = hi - lo
    q_tail = float(metric_summary.get("q_tail", lo))
    cvar_val = float(metric_summary.get("cvar_99", 0.0))
    cvar_point = -cvar_val  # CVaR is reported as a loss; invert for the value axis
    n = len(counts)
    bw = width / n
    peak = max(counts) or 1

    def x_of(v: float) -> float:
        return 0.0 if span <= 1e-12 else max(0.0, min(width, (v - lo) / span * width))

    parts: list[str] = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Empirical distribution with VaR99 and CVaR99 markers">',
        f'<line x1="0" y1="{height - 12.5}" x2="{width}" y2="{height - 12.5}" '
        f'stroke="#1f2937" stroke-width="1"/>',
    ]
    for i, c in enumerate(counts):
        left_val = lo + span * i / n
        h = (c / peak) * (height - 16)
        colour = "#38bdf8"
        if left_val <= cvar_point:
            colour = "#ef4444"
        elif left_val <= q_tail:
            colour = "#f59e0b"
        parts.append(
            f'<rect x="{i * bw:.1f}" y="{height - 12 - h:.1f}" '
            f'width="{max(0.8, bw - 0.7):.1f}" height="{h:.1f}" '
            f'fill="{colour}" opacity="0.88"/>'
        )
    x_var = x_of(q_tail)
    x_cvar = x_of(cvar_point)
    parts.append(
        f'<line x1="{x_var:.1f}" y1="0" x2="{x_var:.1f}" y2="{height - 12}" '
        f'stroke="#ef4444" stroke-width="1.6" stroke-dasharray="3,2"/>'
    )
    parts.append(
        f'<line x1="{x_cvar:.1f}" y1="0" x2="{x_cvar:.1f}" y2="{height - 12}" '
        f'stroke="#f59e0b" stroke-width="1.2"/>'
    )
    parts.append(
        f'<text x="{min(width - 34, x_var + 2):.1f}" y="10" fill="#ef4444" '
        f'font-size="8" font-family="monospace">VaR99</text>'
    )
    parts.append(
        f'<text x="{max(1, x_cvar - 34):.1f}" y="{height - 2}" fill="#f59e0b" '
        f'font-size="8" font-family="monospace">CVaR</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def safe_href(url: str) -> str:
    """Only http(s) links are clickable; reject ``javascript:`` / ``data:``."""
    u = str(url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else "#"


# ---------------------------------------------------------------------------
# 2. Model Block Compiler & Numerical Jacobian Sensitivity Engine
# ---------------------------------------------------------------------------
def compile_models_for_decision_card(
    model_blocks: list[tuple[str, str]],
) -> tuple[list[InputParameter], list[DerivedMetric], str]:
    """Parses all `python:model` blocks into InputParameters, DerivedMetrics,
    and computes exact numerical elasticities and break-even tipping points."""
    inputs: list[InputParameter] = []
    metrics: list[DerivedMetric] = []
    combined_lines: list[str] = []

    baseline_env: dict[str, float] = {}
    for mid, code_str in model_blocks:
        combined_lines.append(code_str)
        emitted = execute_model_block(code_str, initial_env=baseline_env)
        baseline_env.update(emitted)

        tree = ast.parse(code_str, mode="exec")
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                var_name = stmt.targets[0].id
                lit_val = _is_literal_number_node(stmt.value)
                if lit_val is not None:
                    lo, hi, stp = _slider_domain_for_value(lit_val)
                    inputs.append(
                        InputParameter(
                            name=var_name,
                            default_val=lit_val,
                            min_val=lo,
                            max_val=hi,
                            step_val=stp,
                            model_id=mid,
                        )
                    )
                else:
                    js_expr = _ast_expr_to_js(stmt.value)
                    py_expr = ast.unparse(stmt.value) if hasattr(ast, "unparse") else var_name
                    metrics.append(
                        DerivedMetric(
                            name=var_name,
                            baseline_val=baseline_env.get(var_name, 0.0),
                            js_expr=js_expr,
                            py_expr=py_expr,
                            model_id=mid,
                        )
                    )

    full_code = "\n".join(combined_lines)

    # Helper to evaluate all derived metrics when overriding a single input variable
    def _eval_with_override(inp_name: str, new_val: float) -> dict[str, float]:
        override_lines: list[str] = []
        for ln in full_code.splitlines():
            if re.match(rf"^\s*{re.escape(inp_name)}\s*=", ln):
                override_lines.append(f"{inp_name} = {new_val!r}")
            else:
                override_lines.append(ln)
        return execute_model_block("\n".join(override_lines))

    # Compute Numerical Jacobian Elasticities & Linear Break-Even Tipping Points
    for inp in inputs:
        x0 = inp.default_val
        dx = max(abs(x0) * 0.01, 1e-4)
        env_plus = _eval_with_override(inp.name, x0 + dx)
        env_minus = _eval_with_override(inp.name, x0 - dx)

        for m in metrics:
            y0 = m.baseline_val
            dy_dx = (env_plus.get(m.name, y0) - env_minus.get(m.name, y0)) / (2.0 * dx)
            if abs(y0) > 1e-9 and abs(x0) > 1e-9:
                elast = (dy_dx * x0) / y0
                m.elasticities[inp.name] = round(elast, 2)
            # If dy_dx is non-zero, compute 1st-order zero-crossing tipping point x* where Y(x*) = 0
            if abs(dy_dx) > 1e-9:
                x_star = x0 - (y0 / dy_dx)
                m.breakeven_bounds[inp.name] = round(x_star, 4)

    # v10.0: refine the highest-leverage tipping point of each metric by TRUE
    # bisection on the executed model. The linear Newton step above remains as
    # a labelled fallback for inputs with no sign change in the slider domain.
    if inputs and metrics:
        compiled = CompiledModel(full_code, {i.name: i.default_val for i in inputs})
        for m in metrics:
            for inp in inputs:
                m.breakeven_exact.setdefault(inp.name, False)
                exact = _solve_breakeven_bisection(
                    compiled, inp.name, m.name, inp.min_val, inp.max_val
                )
                if exact is not None:
                    m.breakeven_bounds[inp.name] = round(exact, 4)
                    m.breakeven_exact[inp.name] = True

    return inputs, metrics, full_code


# ---------------------------------------------------------------------------
# 3. Single-File HTML5 Generative UI Synthesizer
# ---------------------------------------------------------------------------
def render_decision_card_html(study_dir: Path, verification: Any | None = None) -> str:
    """Compile a study directory into a self-contained HTML5 Decision Card.

    ``verification`` may be supplied by ``cmd_build`` to avoid re-running the
    verify stage. v10.0 adds deterministic Monte Carlo distributions, exact
    tipping points, joint stress presets and scheme-sanitised source links.
    """
    rep = verification if verification is not None else verify_study(study_dir)
    raw_report = (study_dir / "report.md").read_text(encoding="utf-8")
    manifest, model_blocks, prose_text = _extract_embedded_blocks(raw_report)
    if not manifest and (study_dir / "manifest.json").exists():
        manifest = json.loads((study_dir / "manifest.json").read_text(encoding="utf-8"))

    idx_path = study_dir / "sources" / "index.jsonl"
    sources: dict[str, dict[str, Any]] = {}
    if idx_path.exists():
        for ln in idx_path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rec = json.loads(ln)
                sources[rec["id"]] = rec

    inputs, metrics, full_code = compile_models_for_decision_card(model_blocks)

    # v10.0: deterministic distributional stress analytics (no CDN, no RNG deps).
    mc = compute_monte_carlo(full_code, inputs, metrics)
    for m in metrics:
        if m.name in mc.get("metrics", {}):
            m.monte_carlo = mc["metrics"][m.name]
    stress_rows = compute_stress_scenarios(full_code, inputs, metrics)
    mc_meta = (
        f"{mc.get('n_samples', 0)} seeded draws | sigma=±{mc.get('sigma_frac', 0):.0%} per input | "
        f"seed={mc.get('seed', 0)} | model sha256={str(mc.get('code_sha256', ''))[:12]}"
    )
    mc_html_rows: list[str] = []
    for m in metrics:
        d = m.monte_carlo
        if not d:
            continue
        p_bad = float(d.get("p_below_zero", 0.0))
        risk_color = "#ef4444" if p_bad > 0.20 else ("#f59e0b" if p_bad > 0.05 else "#10b981")
        exact_note = ", ".join(
            f"{k}={m.breakeven_bounds[k]:g}" + ("" if m.breakeven_exact.get(k) else " (linear est.)")
            for k in list(m.breakeven_bounds)[:3]
        ) or "—"
        mc_html_rows.append(
            "<tr>"
            f"<td><code>{html.escape(m.name)}</code></td>"
            f"<td>{render_histogram_svg(d.get('histogram', []))}</td>"
            f"<td>P5 {d['p5']} | <strong>P50 {d['p50']}</strong> | P95 {d['p95']}</td>"
            f"<td style=\"color:{risk_color};font-weight:700\">{p_bad:.1%}</td>"
            f"<td><small>{html.escape(exact_note)}</small></td>"
            "</tr>"
        )
    mc_html = "".join(mc_html_rows) or "<tr><td colspan='5'>No executable model metrics found.</td></tr>"

    # --- v11.0 Frontier 2: correlated regimes, VaR99 / CVaR99 ---------------
    STRESS_REGIME = "Liquidity Crunch"
    mc_regime = compute_monte_carlo(
        full_code, inputs, metrics, n_samples=600, regime=STRESS_REGIME,
    ) if inputs and metrics else {"metrics": {}, "correlation": None}
    regime_rows = compute_regime_stress_scenarios(full_code, inputs, metrics)
    corr_info = mc_regime.get("correlation") or {}
    chol_info = corr_info.get("cholesky") or {}
    shifted = [k for k, v in (corr_info.get("mean_shifts") or {}).items() if v]
    risk_meta = (
        f"Stress regime: <strong>{html.escape(STRESS_REGIME)}</strong> | "
        f"declared correlated shocks on {len(shifted)} inputs "
        f"(<code>{html.escape(', '.join(shifted[:6])) or 'none'}</code>) | "
        f"sigma x{html.escape(str(corr_info.get('sigma_multiplier', '-')))} | "
        f"Cholesky repair={html.escape(str(chol_info.get('repair', 'none')))} "
        f"(shrinkage={html.escape(str(chol_info.get('shrinkage', 0.0)))}) | "
        f"{mc_regime.get('n_samples', 0)} correlated draws"
    )
    risk_html_rows: list[str] = []
    for m in metrics:
        base = (mc.get("metrics", {}).get(m.name) or {})
        stressed = (mc_regime.get("metrics", {}).get(m.name) or {})
        if not stressed:
            continue
        var_b, cvar_b = base.get("var_99"), base.get("cvar_99")
        var_s, cvar_s = stressed.get("var_99"), stressed.get("cvar_99")
        worse = (cvar_s is not None and cvar_b is not None and cvar_s > cvar_b)
        flag = "WORSE" if worse else "within baseline"
        flag_color = "#ef4444" if worse else "#10b981"
        risk_html_rows.append(
            "<tr>"
            f"<td><code>{html.escape(m.name)}</code></td>"
            f"<td>{render_risk_svg(stressed)}</td>"
            f"<td>VaR99 {var_b} / CVaR {cvar_b}</td>"
            f"<td><strong>VaR99 {var_s}</strong> / <strong>CVaR {cvar_s}</strong><br>"
            f"<small>P(loss)={stressed.get('p_below_zero', 0):.1%}, tail n={stressed.get('tail_n', 0)}</small></td>"
            f"<td style=\"color:{flag_color};font-weight:700\">{flag}</td>"
            "</tr>"
        )
    risk_html = "".join(risk_html_rows) or "<tr><td colspan='5'>No executable model metrics found.</td></tr>"

    regime_html_rows: list[str] = []
    for row in regime_rows:
        cells = "".join(f"<td>{'—' if v is None else v}</td>" for v in row["values"].values())
        shocked = ", ".join(row["shocked_inputs"]) or "none (no name match)"
        regime_html_rows.append(
            f"<tr><td><strong>{html.escape(row['regime'])}</strong><br>"
            f"<small style='color:var(--muted)'>rho={row['group_rho']}, "
            f"sigma x{row['sigma_multiplier']}<br>shocked: {html.escape(shocked[:90])}</small></td>{cells}</tr>"
        )
    regime_header = "".join(f"<th>{html.escape(m.name)}</th>" for m in metrics)
    regime_html = (
        "<tr><th>Declared macro regime (no probability weight)</th>" + regime_header + "</tr>"
        + "".join(regime_html_rows)
    )

    stress_html_rows: list[str] = []
    for row in stress_rows:
        cells = "".join(
            f"<td>{'—' if v is None else v}</td>" for v in row["values"].values()
        )
        stress_html_rows.append(f"<tr><td><strong>{html.escape(row['scenario'])}</strong></td>{cells}</tr>")
    stress_header = "".join(f"<th>{html.escape(m.name)}</th>" for m in metrics)
    stress_html = (
        f"<tr><th>Deterministic joint shock</th>{stress_header}</tr>"
        + "".join(stress_html_rows)
    )

    title_match = re.search(r"^#\s+(.+)$", raw_report, re.M)
    title = title_match.group(1).strip() if title_match else study_dir.name
    verdict_badge = "PASS" if rep.passed else "FAIL"
    verdict_color = "#10b981" if rep.passed else "#ef4444"

    inputs_json = json.dumps([inp.__dict__ for inp in inputs], ensure_ascii=False)
    metrics_json = json.dumps([m.__dict__ for m in metrics], ensure_ascii=False)

    # Build Evidence Table HTML
    ev_rows: list[str] = []
    for ev in manifest.get("evidence", []):
        eid = html.escape(str(ev.get("id", "")))
        sid = html.escape(str(ev.get("source", "")))
        tier = html.escape(str(ev.get("tier", "T3")))
        quote = html.escape(str(ev.get("quote", "")))
        smeta = sources.get(ev.get("source", ""), {})
        s_url = html.escape(safe_href(str(smeta.get("url", "#"))))
        s_sha = html.escape(str(smeta.get("sha256", ""))[:12])
        ev_rows.append(
            f"<tr>"
            f"<td><code>{eid}</code></td>"
            f"<td><span class='badge'>{tier}</span></td>"
            f"<td><a href='{s_url}' target='_blank' rel='noopener'>{sid}</a><br><small>sha256: <code>{s_sha}</code></small></td>"
            f"<td>&ldquo;{quote}&rdquo;</td>"
            f"</tr>"
        )

    # Build Kill Hypotheses HTML
    kill_rows: list[str] = []
    for k in manifest.get("kills", []):
        kid = html.escape(str(k.get("id", "")))
        kverd = html.escape(str(k.get("verdict", "")).upper())
        keids = html.escape(", ".join(k.get("eids", [])))
        kill_rows.append(
            f"<tr><td><code>{kid}</code></td><td><strong>{kverd}</strong></td><td><code>{keids}</code></td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Decision Card — {html.escape(title)}</title>
<style>
  :root {{
    --bg: #0b0f19; --panel: #111827; --border: #1f2937; --text: #f3f4f6;
    --muted: #9ca3af; --accent: #38bdf8; --ok: #10b981; --danger: #ef4444;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    line-height: 1.5;
  }}
  .container {{ max-width: 1280px; margin: 0 auto; }}
  .header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 20px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; margin-bottom: 20px;
  }}
  .kpi-strip {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }}
  .kpi {{
    background: var(--panel); border: 1px solid var(--border); padding: 14px;
    border-radius: 8px;
  }}
  .kpi .label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; }}
  .kpi .val {{ font-size: 22px; font-weight: 700; color: var(--accent); margin-top: 4px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  @media (max-width: 900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  .panel {{
    background: var(--panel); border: 1px solid var(--border); padding: 20px;
    border-radius: 8px;
  }}
  .slider-row {{ margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }}
  .slider-head {{ display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 4px; }}
  input[type=range] {{ width: 100%; accent-color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid var(--border); padding: 10px; text-align: left; vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 600; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px;
    background: #1e293b; color: var(--accent);
  }}
  a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <div style="font-size:12px;color:var(--muted);">DR_ENGINE v9.0 EXECUTABLE DECISION CARD</div>
      <h1 style="margin:4px 0 0 0;font-size:22px;">{html.escape(title)}</h1>
    </div>
    <div style="background:{verdict_color};color:#000;font-weight:800;padding:8px 16px;border-radius:6px;">
      GATE: {verdict_badge} ({html.escape(rep.max_confidence)} Conf)
    </div>
  </div>

  <div class="kpi-strip">
    <div class="kpi"><div class="label">Epistemic Index (EI)</div><div class="val">{rep.epistemic_index}/100</div></div>
    <div class="kpi"><div class="label">Info Density (IDI)</div><div class="val">{rep.information_density_index}</div></div>
    <div class="kpi"><div class="label">Independent N_eff</div><div class="val">{rep.n_eff_clusters}</div></div>
    <div class="kpi"><div class="label">Algebraic Closure</div><div class="val">{rep.bound_units}/{rep.total_claim_units}</div></div>
    <div class="kpi"><div class="label">Verified Quotes</div><div class="val">{rep.n_evidence}</div></div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <h2 style="margin-top:0;font-size:16px;">Exogenous Stress-Test Sliders (<code>python:model</code> Inputs)</h2>
      <div id="sliders-root"></div>
      <button onclick="resetSliders()" style="margin-top:8px;padding:6px 12px;background:#1e293b;color:#fff;border:1px solid var(--border);border-radius:4px;cursor:pointer;">
        Reset to Baseline
      </button>
    </div>
    <div class="panel">
      <h2 style="margin-top:0;font-size:16px;">Reactive Model Outputs &amp; Jacobian Tipping Points</h2>
      <table>
        <thead>
          <tr><th>Metric</th><th>Live Value</th><th>Baseline</th><th>Top Elasticity / Break-Even</th></tr>
        </thead>
        <tbody id="metrics-body"></tbody>
      </table>
    </div>
  </div>

  <div class="panel" style="margin-bottom:20px;">
    <h2 style="margin-top:0;font-size:16px;">Monte Carlo Distribution &amp; Exact Tipping Points (v10.0)</h2>
    <p style="color:var(--muted);font-size:12px;margin-top:0;">{mc_meta}</p>
    <p style="color:var(--muted);font-size:12px;">All exogenous inputs are shocked <strong>jointly</strong> by a seeded truncated Gaussian. This is a sensitivity measurement, not a subjective Expected Value scenario (Rule B1). "P(value &lt; 0)" is the observed breach frequency; "Tipping" is the exact zero-crossing solved by bisection on the executed model.</p>
    <table>
      <thead><tr><th>Metric</th><th>Distribution</th><th>P5 / P50 / P95</th><th>P(value &lt; 0)</th><th>Break-even x*</th></tr></thead>
      <tbody>{mc_html}</tbody>
    </table>
  </div>

  <div class="panel" style="margin-bottom:20px;">
    <h2 style="margin-top:0;font-size:16px;">Deterministic Joint Stress Presets</h2>
    <table>
      <thead>{stress_html}</thead>
    </table>
  </div>

  <div class="panel" style="margin-bottom:20px;">
    <h2 style="margin-top:0;font-size:16px;">Correlated Regime Stress &amp; Empirical Tail Risk (v11.0)</h2>
    <p style="color:var(--muted);font-size:12px;margin-top:0;">{risk_meta}</p>
    <p style="color:var(--muted);font-size:12px;">Shocks are drawn jointly via Cholesky <code>z_c = L z + mu_r</code>, not independently. VaR99 = &#8722;Q0.01(Y) and CVaR99 = &#8722;E[Y | Y &#8804; Q0.01(Y)] are measured empirically from the simulated distribution. A negative VaR means even the 1% worst case is still a gain. Regimes carry <strong>no</strong> subjective probability weight (Rule B1).</p>
    <table>
      <thead><tr><th>Metric</th><th>Empirical distribution + VaR/CVaR markers</th><th>Baseline tail</th><th>Stress-regime tail</th><th>Delta</th></tr></thead>
      <tbody>{risk_html}</tbody>
    </table>
  </div>

  <div class="panel" style="margin-bottom:20px;">
    <h2 style="margin-top:0;font-size:16px;">Declared Macro Stress Regimes</h2>
    <table>
      <thead>{regime_html}</thead>
    </table>
  </div>

  <div class="panel" style="margin-bottom:20px;">
    <h2 style="margin-top:0;font-size:16px;">Popperian Disconfirmation Ledger (Pre-Registered Kill Hypotheses)</h2>
    <table>
      <thead><tr><th>Kill ID</th><th>Verdict</th><th>Grounding Evidence IDs</th></tr></thead>
      <tbody>{"".join(kill_rows)}</tbody>
    </table>
  </div>

  <div class="panel">
    <h2 style="margin-top:0;font-size:16px;">Cryptographic Evidence Audit Trail (SHA-256 Grounded)</h2>
    <table>
      <thead><tr><th>EID</th><th>Tier</th><th>Source &amp; SHA-256</th><th>Verbatim Snapshot Span</th></tr></thead>
      <tbody>{"".join(ev_rows)}</tbody>
    </table>
  </div>
</div>

<script>
const MODEL_INPUTS = {inputs_json};
const MODEL_METRICS = {metrics_json};

// Built-in quantitative & epistemic helper functions matching `lean_engine.py` SAFE_FUNCS
function dr_round(val, digits=4) {{
  const f = Math.pow(10, digits);
  return Math.round(val * f) / f;
}}
function dr_sum(arr) {{ return arr.reduce((a, b) => a + b, 0); }}
function hold_cost_bp(spread_bp, nights, annual_swap_bp) {{
  return spread_bp + nights * (annual_swap_bp / 365.0);
}}
function net_edge_bp(gross_bp, spread_bp, slippage_bp, comm_bp=0.0) {{
  return gross_bp - (spread_bp + slippage_bp + comm_bp);
}}
function sharpe_annual(mean_ret, std_ret, periods=252.0) {{
  return std_ret > 0 ? (mean_ret / std_ret) * Math.sqrt(periods) : 0.0;
}}
function kelly_half(win_prob, payoff_ratio) {{
  return payoff_ratio > 0 ? 0.5 * (win_prob - (1.0 - win_prob) / payoff_ratio) : 0.0;
}}
function wilson_lower_95(k, n) {{
  if (n <= 0) return 0.0;
  const p = k / n, z2 = 1.96 * 1.96;
  return (p + z2 / (2 * n) - 1.96 * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n);
}}

const state = {{}};
MODEL_INPUTS.forEach(inp => {{ state[inp.name] = inp.default_val; }});

function initUI() {{
  const root = document.getElementById("sliders-root");
  root.innerHTML = "";
  MODEL_INPUTS.forEach(inp => {{
    const row = document.createElement("div");
    row.className = "slider-row";
    row.innerHTML = `
      <div class="slider-head">
        <span><code>${{inp.name}}</code> <small style="color:var(--muted)">(${{inp.model_id}})</small></span>
        <strong id="lbl-${{inp.name}}">${{state[inp.name]}}</strong>
      </div>
      <input type="range" id="rng-${{inp.name}}" min="${{inp.min_val}}" max="${{inp.max_val}}" step="${{inp.step_val}}" value="${{state[inp.name]}}">
    `;
    root.appendChild(row);
    const rng = row.querySelector("input");
    rng.addEventListener("input", (e) => {{
      state[inp.name] = parseFloat(e.target.value);
      document.getElementById("lbl-" + inp.name).textContent = state[inp.name];
      recomputeModel();
    }});
  }});
  recomputeModel();
}}

function recomputeModel() {{
  const env = Object.assign({{}}, state);
  const tbody = document.getElementById("metrics-body");
  tbody.innerHTML = "";
  MODEL_METRICS.forEach(m => {{
    let val = 0.0;
    try {{
      val = Function("env", "dr_round", "dr_sum", "hold_cost_bp", "net_edge_bp", "sharpe_annual", "kelly_half", "wilson_lower_95",
        "return " + m.js_expr)(env, dr_round, dr_sum, hold_cost_bp, net_edge_bp, sharpe_annual, kelly_half, wilson_lower_95);
    }} catch (err) {{
      val = NaN;
    }}
    env[m.name] = val;
    const color = val < 0 ? "var(--danger)" : "var(--ok)";
    const elastEntries = Object.entries(m.elasticities || {{}}).sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]));
    let sensInfo = "—";
    if (elastEntries.length > 0) {{
      const [topVar, topEl] = elastEntries[0];
      const beVal = (m.breakeven_bounds || {{}})[topVar];
      sensInfo = `E(${{topVar}})=${{topEl}}x` + (beVal !== undefined ? ` | Tipping=${{beVal}}` : "");
    }}
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${{m.name}}</code><br><small style="color:var(--muted)">${{m.py_expr}}</small></td>
      <td style="font-weight:700;color:${{color}}">${{Number.isFinite(val) ? val.toFixed(4) : "ERR"}}</td>
      <td style="color:var(--muted)">${{m.baseline_val}}</td>
      <td><small>${{sensInfo}}</small></td>
    `;
    tbody.appendChild(tr);
  }});
}}

function resetSliders() {{
  MODEL_INPUTS.forEach(inp => {{
    state[inp.name] = inp.default_val;
    const rng = document.getElementById("rng-" + inp.name);
    if (rng) rng.value = inp.default_val;
    const lbl = document.getElementById("lbl-" + inp.name);
    if (lbl) lbl.textContent = inp.default_val;
  }});
  recomputeModel();
}}

initUI();
</script>
</body>
</html>
"""


def cmd_build(args: argparse.Namespace) -> int:
    """Fail-closed build: a study that does not pass verification is not a
    decision instrument and must not be handed to an executive or investor.
    """
    d = Path(args.dir)
    out_path = Path(args.out) if args.out else (d / "decision_card.html")
    rep = verify_study(d)
    if not rep.passed and not getattr(args, "allow_failed", False):
        print("[DECISION CARD REFUSED] The study has not passed verification.")
        for f in rep.failures[:12]:
            print(f"  [FAIL] {f}")
        print("Fix the study, or pass --allow-failed to render an explicitly FAIL-marked card.")
        return 2
    html_str = render_decision_card_html(d, verification=rep)
    out_path.write_text(html_str, encoding="utf-8")
    print(
        f"[DECISION CARD OK] Wrote {len(html_str)} chars -> {out_path} "
        f"| gate={'PASS' if rep.passed else 'FAIL'} | EI={rep.epistemic_index}/100"
    )
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    model_code = """
gross_bp = 8.4
spread_bp = 1.2
slippage_rt_bp = 1.8
stop_1r_bp = 100.0
total_friction_bp = spread_bp + slippage_rt_bp
friction_share_of_1r = total_friction_bp / stop_1r_bp
net_alpha_bp = net_edge_bp(gross_bp, spread_bp, slippage_rt_bp)
"""
    inputs, metrics, _ = compile_models_for_decision_card([("C001", model_code.strip())])
    assert len(inputs) == 4, f"Expected 4 exogenous inputs, got {len(inputs)}"
    assert len(metrics) == 3, f"Expected 3 derived metrics, got {len(metrics)}"

    net_m = next(m for m in metrics if m.name == "net_alpha_bp")
    assert net_m.baseline_val == 5.4
    # Break-even gross_bp where net_alpha_bp == 0 must be exactly 3.0 bps (spread 1.2 + slippage 1.8)
    assert abs(net_m.breakeven_bounds["gross_bp"] - 3.0) < 1e-3
    assert net_m.breakeven_exact.get("gross_bp") is True
    assert "net_edge_bp(env.gross_bp, env.spread_bp, env.slippage_rt_bp)" in net_m.js_expr

    # v10.0: a NON-LINEAR model where the v9.0 linear Newton step is wrong.
    nonlinear = """
gross_bp = 20.0
spread_bp = 2.0
cost_bp = spread_bp * spread_bp
net_bp = gross_bp - cost_bp - 4.0
"""
    n_inputs, n_metrics, n_code = compile_models_for_decision_card([("C002", nonlinear.strip())])
    n_metric = next(m for m in n_metrics if m.name == "net_bp")
    spread_inp = next(i for i in n_inputs if i.name == "spread_bp")
    # Exact root: 20 - spread^2 - 4 = 0  ->  spread = 4.0
    if spread_inp.min_val <= 4.0 <= spread_inp.max_val:
        assert abs(n_metric.breakeven_bounds["spread_bp"] - 4.0) < 1e-2, (
            f"bisection failed on non-linear model: {n_metric.breakeven_bounds}"
        )
        assert n_metric.breakeven_exact.get("spread_bp") is True

    # Deterministic Monte Carlo: reproducible, ordered quantiles, valid SVG.
    mc1 = compute_monte_carlo(model_code.strip(), inputs, metrics, n_samples=200, seed=42)
    mc2 = compute_monte_carlo(model_code.strip(), inputs, metrics, n_samples=200, seed=42)
    assert mc1 == mc2, "Monte Carlo is not reproducible for a fixed seed"
    assert mc1["seed"] == 42 and mc1["code_sha256"]
    for name, d in mc1["metrics"].items():
        assert d["p5"] <= d["p50"] <= d["p95"], f"quantiles out of order for {name}"
        assert 0.0 <= d["p_below_zero"] <= 1.0
        assert len(d["histogram"]) == 18
    assert "<svg" in render_histogram_svg(mc1["metrics"]["net_alpha_bp"]["histogram"])

    scenarios = compute_stress_scenarios(model_code.strip(), inputs, metrics)
    assert [r["scenario"] for r in scenarios] == [
        "Baseline", "Adverse (-1s)", "Severe (-2s)", "Upside (+1s)"
    ]

    # v11.0: correlated regime Monte Carlo with empirical VaR99 / CVaR99.
    corr = {"groups": [(["spread_bp", "slippage_rt_bp"], 0.90)]}
    stressed = compute_monte_carlo(model_code.strip(), inputs, metrics,
                                   n_samples=300, seed=42,
                                   correlation=corr, regime="Liquidity Crunch")
    assert stressed["regime"] == "Liquidity Crunch"
    assert stressed["correlation"]["cholesky"]["positive_definite"]
    assert stressed["correlation"]["mean_shifts"]["spread_bp"] == 1.6
    for name, d in stressed["metrics"].items():
        assert d["var_99"] is not None and d["cvar_99"] is not None
        assert d["cvar_99"] >= d["var_99"] - 1e-6, f"CVaR < VaR for {name}"
        assert d["tail_n"] >= 1 and d["hist_lo"] <= d["hist_hi"]
    assert mc1["metrics"]["net_alpha_bp"]["var_99"] is not None
    svg = render_risk_svg(stressed["metrics"]["net_alpha_bp"])
    assert "<svg" in svg and "<rect" in svg and "VaR99" in svg and "CVaR" in svg

    regime_rows = compute_regime_stress_scenarios(model_code.strip(), inputs, metrics)
    assert [r["regime"] for r in regime_rows] == [
        "Baseline", "Liquidity Crunch", "High-Inflation Squeeze", "Latency Breakdown"
    ]
    assert regime_rows[1]["group_rho"] == 0.85
    assert "spread_bp" in regime_rows[1]["shocked_inputs"]

    assert safe_href("https://example.com") == "https://example.com"
    assert safe_href("javascript:alert(1)") == "#"
    assert safe_href("data:text/html,x") == "#"

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 50.0, f"Selftest exceeded 50ms budget: {elapsed_ms:.2f}ms"
    print(f"[SELFTEST PASS] decision_card v11.0 (bisection + correlated MC + VaR/CVaR + regimes + fail-closed) verified in {elapsed_ms:.2f} ms.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_b = sub.add_parser("build", help="Compile study directory into an interactive HTML5 Decision Card")
    p_b.add_argument("--dir", required=True, help="Path to study directory")
    p_b.add_argument("--out", help="Output HTML path (default: <dir>/decision_card.html)")
    p_b.add_argument("--allow-failed", action="store_true",
                     help="Render a FAIL-marked card even when verification did not pass")
    p_b.set_defaults(fn=cmd_build)

    p_st = sub.add_parser("selftest", help="Run zero-mock verification (< 50 ms)")
    p_st.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
