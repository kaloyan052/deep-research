#!/usr/bin/env python3
"""Deep Research Engine v11.0 — Correlated Risk & Regime Stress Engine.

v10.0 Monte Carlo perturbed every exogenous input independently with a fixed
σ = 10%. That is physically wrong for finance, macro and hardware: when market
friction widens, latency spikes and volatility rises *together*. Independent
draws systematically understate tail risk.

This module supplies a zero-dependency correlated shock engine:

  * :func:`cholesky` -- lower-triangular decomposition ``Σ = L Lᵀ`` with a
    deterministic diagonal-jitter schedule for numerically non-PSD matrices;
  * :func:`build_correlation_matrix` -- named pair/group/matrix specifications;
  * :func:`correlated_shocks` -- ``z_c = L z + μ_r`` where ``μ_r`` is a named
    macro regime's mean-shift vector;
  * :func:`empirical_var_cvar` -- empirical ``VaR₉₉`` and Expected Shortfall
    (``CVaR₉₉``), with no distributional assumption.

All computations are pure Python 3.10+ stdlib, deterministic given a seed, and
Windows cp1252-safe. Correlation structure is DECLARED and reported -- it is
never inferred from an LLM's opinion or hidden inside a subjective weight.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

__all__ = [
    "cholesky", "validate_correlation_matrix", "build_correlation_matrix",
    "normalize_correlation_spec", "correlated_shocks", "empirical_var_cvar",
    "quantile", "MACRO_REGIMES", "regime_mean_shifts", "regime_correlation_spec",
    "structural_correlation_spec", "risk_summary",
]

# Repair schedules for a declared matrix that is not positive-definite.
# Stage 1 is diagonal jitter (numerical borderline cases). Stage 2 is the
# standard Ledoit-Wolf-style shrinkage toward identity: Σ_λ = (1-λ)Σ + λI,
# which is the honest way to handle a genuinely inconsistent correlation
# structure. The repair type and amount are ALWAYS reported, never silent.
_JITTER_SCHEDULE = (0.0, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3)
_SHRINKAGE_SCHEDULE = (0.01, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 0.90)


def _try_cholesky(matrix: Sequence[Sequence[float]], eps: float) -> list[list[float]] | None:
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                d = float(matrix[i][i]) + eps - s
                if d <= 0.0 or not math.isfinite(d):
                    return None
                L[i][j] = math.sqrt(d)
            else:
                if L[j][j] == 0.0:
                    return None
                L[i][j] = (float(matrix[i][j]) - s) / L[j][j]
    return L


def cholesky(matrix: Sequence[Sequence[float]], jitter: bool = True) -> tuple[list[list[float]] | None, dict[str, Any]]:
    """Compute lower-triangular ``L`` with ``Σ = L Lᵀ``.

    Args:
        matrix: Square symmetric correlation/covariance matrix.
        jitter: When True, retry with increasing diagonal regularization if the
            declared matrix is not positive-definite.

    Returns:
        ``(L, info)``. ``L`` is ``None`` only if the matrix is irreparable;
        ``info`` records dimension, jitter applied, and any validation errors.
    """
    errors = validate_correlation_matrix(matrix, allow_covariance_diag=True)
    if errors:
        return None, {"dimension": len(matrix), "jitter": None, "errors": errors}

    n = len(matrix)
    schedule = _JITTER_SCHEDULE if jitter else (0.0,)
    for eps in schedule:
        L = _try_cholesky(matrix, eps)
        if L is not None:
            return L, {
                "dimension": n, "jitter": eps, "shrinkage": 0.0,
                "positive_definite": True, "errors": [],
                "repaired": eps > 0.0,
                "repair": "diagonal_jitter" if eps > 0.0 else "none",
            }
    if jitter:
        for lam in _SHRINKAGE_SCHEDULE:
            shrunk = [
                [(1.0 - lam) * float(matrix[i][j]) + (lam if i == j else 0.0)
                 for j in range(n)]
                for i in range(n)
            ]
            L = _try_cholesky(shrunk, 0.0)
            if L is not None:
                return L, {
                    "dimension": n, "jitter": 0.0, "shrinkage": lam,
                    "positive_definite": True, "errors": [],
                    "repaired": True, "repair": "identity_shrinkage",
                    "note": f"declared correlation was indefinite; shrunk toward identity by lambda={lam}",
                }
    return None, {
        "dimension": n, "jitter": None, "shrinkage": None,
        "positive_definite": False,
        "errors": ["matrix could not be made positive-definite by jitter or shrinkage"],
    }


def validate_correlation_matrix(
    matrix: Sequence[Sequence[float]], allow_covariance_diag: bool = True,
) -> list[str]:
    """Return a list of structural errors; empty means the matrix is usable."""
    n = len(matrix)
    errors: list[str] = []
    if n == 0:
        return ["empty matrix"]
    for row in matrix:
        if len(row) != n:
            return ["matrix is not square"]
    for i in range(n):
        for j in range(n):
            v = float(matrix[i][j])
            if not math.isfinite(v):
                errors.append(f"non-finite entry [{i}][{j}]")
            if abs(v) > 1.0 + 1e-9 and not (i == j and allow_covariance_diag):
                errors.append(f"off-diagonal |rho| > 1 at [{i}][{j}]")
            if abs(float(matrix[i][j]) - float(matrix[j][i])) > 1e-8:
                errors.append(f"asymmetric at [{i}][{j}]")
        if float(matrix[i][i]) <= 0.0:
            errors.append(f"non-positive diagonal at [{i}]")
    return sorted(set(errors))


def normalize_correlation_spec(
    names: Sequence[str], spec: Any,
) -> tuple[list[list[float]], dict[str, Any]]:
    """Normalise a user-supplied correlation spec into a full matrix.

    Accepted forms (all deterministic, no model inference)::

        None                                   -> identity
        {"pairs": [(a, b, rho), ...]}          -> named pair correlations
        {"groups": [(names, rho), ...]}        -> equicorrelated groups
        {(a, b): rho, ...}                    -> direct pair map
        {"matrix": [[...]], "order": [...]}    -> explicit matrix
    """
    n = len(names)
    identity = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    meta: dict[str, Any] = {"spec_kind": "identity", "pairs": 0, "groups": 0}
    if spec is None:
        return identity, meta

    index = {name: i for i, name in enumerate(names)}
    matrix = [row[:] for row in identity]

    def set_pair(a: str, b: str, rho: float) -> None:
        if a not in index or b not in index or a == b:
            return
        r = max(-0.999, min(0.999, float(rho)))
        matrix[index[a]][index[b]] = r
        matrix[index[b]][index[a]] = r
        meta["pairs"] += 1

    if isinstance(spec, dict) and "matrix" in spec:
        raw = spec["matrix"]
        order = list(spec.get("order") or names)
        pos = {name: i for i, name in enumerate(order)}
        out = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        for i, a in enumerate(names):
            for j, b in enumerate(names):
                if a in pos and b in pos:
                    ri, rj = pos[a], pos[b]
                    if ri < len(raw) and rj < len(raw[ri]):
                        out[i][j] = float(raw[ri][rj])
        meta["spec_kind"] = "explicit_matrix"
        return out, meta

    if isinstance(spec, dict) and ("pairs" in spec or "groups" in spec):
        for item in spec.get("pairs") or []:
            if isinstance(item, (list, tuple)) and len(item) == 3:
                set_pair(str(item[0]), str(item[1]), float(item[2]))
            elif isinstance(item, dict):
                set_pair(str(item.get("a")), str(item.get("b")), float(item.get("rho", 0)))
        for group in spec.get("groups") or []:
            members, rho = group
            members = [str(m) for m in members]
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    set_pair(members[x], members[y], rho)
            meta["groups"] += 1
        meta["spec_kind"] = "pairs_and_groups"
        return matrix, meta

    if isinstance(spec, dict):
        for key, rho in spec.items():
            if isinstance(key, (tuple, list)) and len(key) == 2:
                set_pair(str(key[0]), str(key[1]), float(rho))
            elif isinstance(key, str) and ("|" in key or "::" in key):
                sep = "|" if "|" in key else "::"
                a, b = key.split(sep, 1)
                set_pair(a.strip(), b.strip(), float(rho))
        meta["spec_kind"] = "pair_map"
        return matrix, meta

    return identity, meta


def build_correlation_matrix(names: Sequence[str], spec: Any = None) -> tuple[list[list[float]], dict[str, Any]]:
    """Build and validate a named correlation matrix (convenience wrapper)."""
    matrix, meta = normalize_correlation_spec(names, spec)
    errors = validate_correlation_matrix(matrix)
    meta["errors"] = errors
    return matrix, meta


def correlated_shocks(
    L: Sequence[Sequence[float]],
    z: Sequence[float],
    mean_shifts: Sequence[float] | None = None,
    clamp: float = 3.0,
) -> list[float]:
    """Apply ``z_c = L z + μ_r`` and clamp to ±``clamp`` standard deviations."""
    n = len(L)
    out: list[float] = []
    for i in range(n):
        value = sum(float(L[i][j]) * float(z[j]) for j in range(min(n, len(z))))
        if mean_shifts is not None and i < len(mean_shifts):
            value += float(mean_shifts[i])
        out.append(max(-clamp, min(clamp, value)))
    return out


# ---------------------------------------------------------------------------
# Declared macro stress regimes (NOT subjective scenario probabilities).
# A regime is a deterministic joint mean-shift vector + a correlation structure.
# There are no weights or likelihoods attached: these are stress measurements.
# ---------------------------------------------------------------------------
MACRO_REGIMES: dict[str, dict[str, Any]] = {
    "Baseline": {
        "description": "No joint shock; identity correlation.",
        "sigma_multiplier": 1.0,
        "mean_shock_patterns": {},
        "group_rho": 0.0,
        "shock_patterns": (),
    },
    "Liquidity Crunch": {
        "description": "Bid-ask spread, slippage and fees widen together while fill volume collapses.",
        "sigma_multiplier": 1.8,
        "mean_shock_patterns": {
            "spread": 1.6, "slip": 1.6, "friction": 1.6, "fee": 1.6,
            "commission": 1.6, "cost": 1.2, "impact": 1.4,
            "vol": 1.3, "volatility": 1.3,
            "volume": -1.2, "liquidity": -1.2, "fill": -1.2,
        },
        "group_rho": 0.85,
        "shock_patterns": (
            "spread", "slip", "friction", "fee", "commission", "cost",
            "impact", "vol", "volatility", "volume", "liquidity", "fill",
        ),
    },
    "High-Inflation Squeeze": {
        "description": "Rates, input costs and discount rates rise together; real margins compress.",
        "sigma_multiplier": 1.5,
        "mean_shock_patterns": {
            "rate": 1.4, "inflation": 1.6, "discount": 1.3, "cost": 1.4,
            "price": 1.2, "wage": 1.3, "bom": 1.3, "margin": -1.0,
            "yield": -0.9, "return": -1.0,
        },
        "group_rho": 0.75,
        "shock_patterns": (
            "rate", "inflation", "discount", "cost", "price", "wage",
            "bom", "margin", "yield", "return",
        ),
    },
    "Latency Breakdown": {
        "description": "Queueing delay, timeouts and retries spike while throughput collapses.",
        "sigma_multiplier": 1.7,
        "mean_shock_patterns": {
            "latency": 1.8, "timeout": 1.7, "delay": 1.6, "queue": 1.6,
            "backoff": 1.4, "retry": 1.4, "throughput": -1.4,
            "capacity": -1.2, "speed": -1.2, "qps": -1.4,
        },
        "group_rho": 0.80,
        "shock_patterns": (
            "latency", "timeout", "delay", "queue", "backoff", "retry",
            "throughput", "capacity", "speed", "qps",
        ),
    },
}


def regime_mean_shifts(names: Sequence[str], regime: str) -> list[float]:
    """Map a named regime to a per-input mean-shift vector (units of σ).

    Matching is deterministic substring matching on the input variable name.
    Unmatched inputs receive a zero shift; every applied shift is reported.
    """
    spec = MACRO_REGIMES.get(regime)
    if not spec:
        return [0.0] * len(names)
    patterns: dict[str, float] = spec["mean_shock_patterns"]
    # Longest pattern wins, so the specific "volume" (-1.2) is not swallowed
    # by the generic "vol" (+1.3). Fully deterministic for equal lengths.
    ordered = sorted(patterns.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    out: list[float] = []
    for name in names:
        low = name.lower()
        best = 0.0
        for pattern, shift in ordered:
            if pattern in low:
                best = float(shift)
                break
        out.append(best)
    return out


def regime_correlation_spec(names: Sequence[str], regime: str) -> dict[str, Any]:
    """Equicorrelate all inputs that a regime's patterns actually touch."""
    spec = MACRO_REGIMES.get(regime)
    if not spec or not spec.get("group_rho"):
        return {}
    patterns = tuple(spec.get("shock_patterns") or ())
    members = [
        n for n in names
        if any(p in n.lower() for p in patterns)
    ]
    if len(members) < 2:
        return {}
    return {"groups": [(members, float(spec["group_rho"]))]}


def structural_correlation_spec(names: Sequence[str], rho: float = 0.60) -> dict[str, Any]:
    """Auto-declare a correlation structure from variable-name families.

    This is a *declared*, reproducible grouping (friction-like inputs move
    together, scale-like inputs move together). It is not an estimate and is
    always printed in the Decision Card so a reviewer can reject it.
    """
    families: dict[str, list[str]] = {
        "friction": [n for n in names if any(
            p in n.lower() for p in ("spread", "slip", "friction", "fee", "commission"))],
        "scale": [n for n in names if any(
            p in n.lower() for p in ("volume", "capital", "equity", "size", "notional"))],
        "cost": [n for n in names if any(
            p in n.lower() for p in ("cost", "bom", "price", "rate"))],
    }
    groups = [(members, rho) for members in families.values() if len(members) >= 2]
    return {"groups": groups} if groups else {}


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation-free empirical quantile on PRE-SORTED values."""
    if not sorted_values:
        return float("nan")
    q = max(0.0, min(1.0, float(q)))
    idx = int(round(q * (len(sorted_values) - 1)))
    return float(sorted_values[max(0, min(len(sorted_values) - 1, idx))])


def empirical_var_cvar(values: Iterable[float], alpha: float = 0.99) -> dict[str, Any]:
    """Empirical Value-at-Risk and Expected Shortfall for a GAIN-like metric.

    Convention (documented so sign errors cannot hide):
      * ``Y`` is a gain (net alpha / net saving / throughput headroom).
      * ``Q = quantile(Y, 1-alpha)`` is the 1% left-tail outcome.
      * ``VaR = -Q``  (positive = loss at the stated confidence).
      * ``CVaR = -E[Y | Y <= Q]`` (Expected Shortfall of the tail).
    A **negative** VaR means even the 1% worst case is still a gain.

    No normality assumption is made: both statistics are computed directly
    from the simulated empirical distribution.
    """
    vals = sorted(
        float(v) for v in values
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
    )
    if not vals:
        return {"var_99": None, "cvar_99": None, "q_tail": None, "tail_n": 0,
                "alpha": alpha, "n": 0}
    q = 1.0 - float(alpha)
    threshold = quantile(vals, q)
    tail = [v for v in vals if v <= threshold] or [threshold]
    var = -threshold
    cvar = -(sum(tail) / len(tail))
    return {
        "var_99": round(var, 4),
        "cvar_99": round(cvar, 4),
        "q_tail": round(threshold, 4),
        "tail_n": len(tail),
        "alpha": alpha,
        "n": len(vals),
        "cvar_ge_var": cvar >= var - 1e-9,
        "var_negative_means_no_loss": var < 0.0,
    }


def risk_summary(values: Iterable[float], alpha: float = 0.99) -> dict[str, Any]:
    """Combine dispersion, tail risk and breach frequency into one record."""
    vals = sorted(
        float(v) for v in values
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
    )
    if not vals:
        return {"n": 0}
    tail = empirical_var_cvar(vals, alpha=alpha)
    return {
        "n": len(vals),
        "p1": round(quantile(vals, 0.01), 4),
        "p5": round(quantile(vals, 0.05), 4),
        "p50": round(quantile(vals, 0.50), 4),
        "p95": round(quantile(vals, 0.95), 4),
        "mean": round(sum(vals) / len(vals), 4),
        "p_below_zero": round(sum(1 for v in vals if v < 0) / len(vals), 4),
        **tail,
    }


def _selftest() -> int:
    # Cholesky correctness: L Lᵀ reconstructs Σ.
    sigma = [[1.0, 0.8, 0.3], [0.8, 1.0, 0.5], [0.3, 0.5, 1.0]]
    L, info = cholesky(sigma)
    assert L is not None and info["positive_definite"]
    recon = [[sum(L[i][k] * L[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
    for i in range(3):
        for j in range(3):
            assert abs(recon[i][j] - sigma[i][j]) < 1e-9
    assert not validate_correlation_matrix(sigma)
    assert validate_correlation_matrix([[1.0, 1.5], [1.5, 1.0]])
    # Genuinely indefinite matrix (rho12=+0.99, rho13=-0.99, rho23=+0.99)
    # is repaired by REPORTED shrinkage toward identity; without repair it
    # must be refused rather than silently producing correlated garbage.
    bad = [[1.0, 0.99, -0.99], [0.99, 1.0, 0.99], [-0.99, 0.99, 1.0]]
    assert not validate_correlation_matrix(bad)
    L_bad, info_bad = cholesky(bad)
    assert L_bad is not None and info_bad["repaired"]
    assert info_bad["repair"] == "identity_shrinkage" and info_bad["shrinkage"] > 0
    L_nojit, info_nojit = cholesky(bad, jitter=False)
    assert L_nojit is None and not info_nojit["positive_definite"]

    names = ["spread_bp", "slippage_bp", "fee_bp", "volume"]
    mat, meta = build_correlation_matrix(
        names, {"groups": [(names[:3], 0.85)]})
    assert mat[0][1] == 0.85 and mat[1][2] == 0.85 and mat[0][3] == 0.0
    assert meta["pairs"] == 3 and meta["groups"] == 1
    assert not meta["errors"]

    # Correlated shocks actually couple variables: a shock to input 0 must
    # propagate into input 1, which an identity matrix would leave at zero.
    L2, _ = cholesky([[1.0, 0.9], [0.9, 1.0]])
    zc = correlated_shocks(L2, [1.0, 0.0])
    assert abs(zc[0] - 1.0) < 1e-9 and zc[1] > 0.5, f"coupling failed: {zc}"
    Lind, _ = cholesky([[1.0, 0.0], [0.0, 1.0]])
    assert correlated_shocks(Lind, [1.0, 0.0])[1] == 0.0
    assert correlated_shocks(L2, [99.0, -99.0], clamp=2.0)[0] <= 2.0

    # Regime mean shifts are declared, deterministic and name-driven.
    shifts = regime_mean_shifts(names, "Liquidity Crunch")
    assert shifts[0] == 1.6 and shifts[3] == -1.2
    assert regime_mean_shifts(names, "Baseline") == [0.0] * len(names)
    assert regime_correlation_spec(names, "Liquidity Crunch")["groups"][0][1] == 0.85
    assert structural_correlation_spec(names)["groups"]

    # VaR / CVaR: empirical, CVaR >= VaR, negative VaR means no 1% loss.
    vals = [-10.0] + [float(i) for i in range(1, 100)]
    r = empirical_var_cvar(vals)
    assert r["cvar_ge_var"] and r["cvar_99"] >= r["var_99"]
    assert r["tail_n"] >= 1 and r["n"] == 100
    positive = empirical_var_cvar([float(i) for i in range(1, 101)])
    assert positive["var_negative_means_no_loss"]
    assert risk_summary(vals)["p50"] == 50.0

    print("[SELFTEST PASS] risk_engine v11.0 (Cholesky/regimes/VaR-CVaR) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
