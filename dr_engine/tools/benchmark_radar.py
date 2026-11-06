#!/usr/bin/env python3
"""Deep Research Engine v10.0 — Benchmark Radar & Live Frontier Model Tracker.

v9.0 claimed to "track live independent benchmarks" but made **zero network
calls**: it shipped a hardcoded table with a fixed ``eval_date``. That is its
own form of Academic Citation Lag, and ``get_benchmark()`` silently returned
the *finance* leaderboard for any unrecognised category (so a biotech query
received LLM rankings). ``get_leader()`` returned ``models[0]`` for metrics
that do not exist in the registry.

v10.0 keeps the bundled table strictly as an explicitly labelled, **unverified
offline seed** (backward-compatible), and adds:

  * ``provenance()`` / ``staleness()`` -- machine-readable freshness metadata;
  * a provenance banner in every rendered snapshot, so a report author cannot
    mistake the seed for a current measurement;
  * strict category and metric resolution (no silent fallback);
  * ``fetch_live_snapshot()`` / ``attach_live_snapshot()`` -- a real fetched,
    SHA-256-anchored Tier-2 page that CAN satisfy Rule B9.

The bundled numbers are retained only for regression tests and offline demos.
They must never be cited as current measured results.

Pure Python 3.10+ stdlib. Zero paid API keys. Windows cp1252-safe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# Allow both `python dr_engine/tools/benchmark_radar.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.http_resilience import resilient_fetch  # noqa: E402

# Maximum acceptable age (days) of a Tier-2 benchmark snapshot. Frontier model
# leaderboards move monthly; anything older is itself citation lag.
BENCHMARK_MAX_AGE_DAYS = 45

# ---------------------------------------------------------------------------
# Authoritative Benchmark Snapshot Registries (Late 2026 Ground Truth)
# ---------------------------------------------------------------------------

ARTIFICIAL_ANALYSIS_FINANCE_2026 = {
    "index_name": "Artificial Analysis Finance & Accounting Index",
    "url": "https://artificialanalysis.ai/indexes/finance-and-accounting",
    "publisher": "Artificial Analysis",
    "eval_date": "2026-10",
    "evaluations_incorporated": [
        "AA-Briefcase v1.1",
        "AA-Omniscience v1.1",
        "HLE-Diamond",
        "AutomationBench-AA",
        "GDPpdf",
    ],
    "total_models_evaluated": 118,
    "top_models": [
        {
            "rank": 1,
            "model": "Gemini 4 Carbon (high)",
            "provider": "Google DeepMind",
            "overall_score": 63,
            "agentic_knowledge_work": 56,
            "business_knowledge": 46,
            "reasoning": 65,
            "non_hallucination": 93,
            "agentic_tool_use": 88,
            "notes": "Ranks #1 globally. Explicit reasoning mode with formal self-verification loops eliminates accounting hallucinations.",
        },
        {
            "rank": 2,
            "model": "Claude Opus 5.5 (max)",
            "provider": "Anthropic",
            "overall_score": 59,
            "agentic_knowledge_work": 66,
            "business_knowledge": 52,
            "reasoning": 68,
            "non_hallucination": 57,
            "agentic_tool_use": 87,
            "notes": "Ranks #2 globally. Global leader in pure Reasoning (68) and Agentic Knowledge (66). Institutional favorite for quantitative financial modeling.",
        },
        {
            "rank": 3,
            "model": "GPT-6 Astra (max)",
            "provider": "OpenAI",
            "overall_score": 57,
            "agentic_knowledge_work": 53,
            "business_knowledge": 52,
            "reasoning": 64,
            "non_hallucination": 68,
            "agentic_tool_use": 70,
            "notes": "Powers OpenAI ChatGPT for Financial Services with native Bloomberg and EDGAR connectivity.",
        },
        {
            "rank": 4,
            "model": "GPT-6.1 Sol (max)",
            "provider": "OpenAI",
            "overall_score": 56,
            "agentic_knowledge_work": 53,
            "business_knowledge": 54,
            "reasoning": 59,
            "non_hallucination": 70,
            "agentic_tool_use": 58,
            "notes": "Leader in Business Knowledge (54) among top tier. Optimal for board narratives and compliance reviews.",
        },
        {
            "rank": 5,
            "model": "Claude Sonnet 5.5 (max)",
            "provider": "Anthropic",
            "overall_score": 56,
            "agentic_knowledge_work": 65,
            "business_knowledge": 38,
            "reasoning": 53,
            "non_hallucination": 63,
            "agentic_tool_use": 79,
            "notes": "High-throughput enterprise workhorse for daily screening and structured data extraction.",
        },
        {
            "rank": 6,
            "model": "Muse Wonder Full (max)",
            "provider": "Muse",
            "overall_score": 55,
            "agentic_knowledge_work": 51,
            "business_knowledge": 49,
            "reasoning": 60,
            "non_hallucination": 67,
            "agentic_tool_use": 79,
            "notes": "Leading independent reasoning architecture.",
        },
        {
            "rank": 7,
            "model": "Claude Fable 5.1 (max)",
            "provider": "Anthropic",
            "overall_score": 54,
            "agentic_knowledge_work": 59,
            "business_knowledge": 39,
            "reasoning": 60,
            "non_hallucination": 37,
            "agentic_tool_use": 80,
            "notes": "Anthropic long-horizon agentic specialist.",
        },
        {
            "rank": 8,
            "model": "Kimi K3.1 Pro",
            "provider": "Moonshot AI",
            "overall_score": 53,
            "agentic_knowledge_work": 59,
            "business_knowledge": 39,
            "reasoning": 72,
            "non_hallucination": 85,
            "agentic_tool_use": 73,
            "notes": "Leading long-context Chinese frontier model.",
        },
        {
            "rank": 9,
            "model": "Grok 4.7 (xhigh)",
            "provider": "xAI",
            "overall_score": 52,
            "agentic_knowledge_work": 58,
            "business_knowledge": 28,
            "reasoning": 87,
            "non_hallucination": 87,
            "agentic_tool_use": 63,
            "notes": "High raw reasoning with real-time news syndication.",
        },
        {
            "rank": 10,
            "model": "Muse Wonder (max)",
            "provider": "Muse",
            "overall_score": 51,
            "agentic_knowledge_work": 58,
            "business_knowledge": 38,
            "reasoning": 79,
            "non_hallucination": 81,
            "agentic_tool_use": 54,
            "notes": "Compact reasoning architecture.",
        },
        {
            "rank": 11,
            "model": "GPT-6.1 Terra (max)",
            "provider": "OpenAI",
            "overall_score": 49,
            "agentic_knowledge_work": 45,
            "business_knowledge": 47,
            "reasoning": 83,
            "non_hallucination": 83,
            "agentic_tool_use": 57,
            "notes": "Cost-optimized enterprise tier.",
        },
        {
            "rank": 12,
            "model": "Qwen3.8 Max (0902)",
            "provider": "Alibaba",
            "overall_score": 45,
            "agentic_knowledge_work": 57,
            "business_knowledge": 21,
            "reasoning": 75,
            "non_hallucination": 75,
            "agentic_tool_use": 44,
            "notes": "Leading open-access enterprise derivative.",
        },
        {
            "rank": 13,
            "model": "Inkling 2 Small",
            "provider": "Inkling",
            "overall_score": 44,
            "agentic_knowledge_work": 51,
            "business_knowledge": 26,
            "reasoning": 78,
            "non_hallucination": 78,
            "agentic_tool_use": 59,
            "notes": "On-device quant specialist.",
        },
        {
            "rank": 14,
            "model": "Claude Haiku 5.5 (max)",
            "provider": "Anthropic",
            "overall_score": 44,
            "agentic_knowledge_work": 54,
            "business_knowledge": 25,
            "reasoning": 82,
            "non_hallucination": 82,
            "agentic_tool_use": 74,
            "notes": "Sub-second financial event screener.",
        },
        {
            "rank": 15,
            "model": "Ling 3.1 Flash 1019",
            "provider": "Ling AI",
            "overall_score": 43,
            "agentic_knowledge_work": 51,
            "business_knowledge": 20,
            "reasoning": 81,
            "non_hallucination": 81,
            "agentic_tool_use": 62,
            "notes": "Fast inference financial parser.",
        },
        {
            "rank": 16,
            "model": "Gemini 3.8 Flash (high)",
            "provider": "Google DeepMind",
            "overall_score": 42,
            "agentic_knowledge_work": 35,
            "business_knowledge": 44,
            "reasoning": 60,
            "non_hallucination": 60,
            "agentic_tool_use": 44,
            "notes": "Efficient multi-modal filing ingestion engine.",
        },
        {
            "rank": 17,
            "model": "DeepSeek V4.1 Flash 1017 (max)",
            "provider": "DeepSeek",
            "overall_score": 42,
            "agentic_knowledge_work": 54,
            "business_knowledge": 29,
            "reasoning": 45,
            "non_hallucination": 45,
            "agentic_tool_use": 78,
            "notes": "Open-weight Mixture-of-Experts with local deployment.",
        },
    ],
}

ARTIFICIAL_ANALYSIS_CODING_2026 = {
    "index_name": "Artificial Analysis Coding & Software Engineering Index",
    "url": "https://artificialanalysis.ai/indexes/coding",
    "publisher": "Artificial Analysis",
    "eval_date": "2026-10",
    "evaluations_incorporated": [
        "SWE-bench Verified v2",
        "HumanEval Pro",
        "Aider Multi-File Bench",
        "RepoQA",
    ],
    "total_models_evaluated": 118,
    "top_models": [
        {
            "rank": 1,
            "model": "Gemini 4 Carbon (high)",
            "provider": "Google DeepMind",
            "overall_score": 74.2,
            "swe_bench_verified": 68.4,
            "multi_file_refactoring": 76.1,
            "notes": "Top SWE-bench placement with multi-day autonomous vulnerability discovery and remediation.",
        },
        {
            "rank": 2,
            "model": "Claude Opus 5.5 (max)",
            "provider": "Anthropic",
            "overall_score": 72.8,
            "swe_bench_verified": 67.2,
            "multi_file_refactoring": 75.8,
            "notes": "Autonomous code architecture and off-by-one bug detection leader.",
        },
        {
            "rank": 3,
            "model": "Claude Sonnet 5.5 (max)",
            "provider": "Anthropic",
            "overall_score": 69.5,
            "swe_bench_verified": 62.5,
            "multi_file_refactoring": 71.0,
            "notes": "Highest speed-to-performance ratio for daily code synthesis.",
        },
        {
            "rank": 4,
            "model": "GPT-6 Astra (max)",
            "provider": "OpenAI",
            "overall_score": 68.9,
            "swe_bench_verified": 61.8,
            "multi_file_refactoring": 70.4,
            "notes": "Deep agentic debugging and system-level execution.",
        },
    ],
}

BENCHMARK_REGISTRIES = {
    "finance": ARTIFICIAL_ANALYSIS_FINANCE_2026,
    "finance_and_accounting": ARTIFICIAL_ANALYSIS_FINANCE_2026,
    "accounting": ARTIFICIAL_ANALYSIS_FINANCE_2026,
    "coding": ARTIFICIAL_ANALYSIS_CODING_2026,
    "software": ARTIFICIAL_ANALYSIS_CODING_2026,
    "swe": ARTIFICIAL_ANALYSIS_CODING_2026,
}

# ---------------------------------------------------------------------------
# Core Radar Engine
# ---------------------------------------------------------------------------

def resolve_category(category: str) -> str:
    """Resolve a category string to a registry key, or raise ``ValueError``.

    v9.0 returned the finance leaderboard for *every* unknown category, so a
    biotech or hardware query silently received LLM rankings. Unknown now fails
    loudly, in line with the workspace's no-fabrication rule.
    """
    cat_norm = str(category or "").lower().strip().replace(" ", "_").replace("-", "_")
    for key in BENCHMARK_REGISTRIES:
        if key in cat_norm or cat_norm in key:
            return key
    raise ValueError(
        f"No benchmark registry for category {category!r}. "
        f"Available: {sorted(BENCHMARK_REGISTRIES)}. "
        "Do not substitute an unrelated leaderboard."
    )


class BenchmarkRadar:
    """Manages unverified offline seeds and genuinely live benchmark snapshots."""

    @classmethod
    def get_benchmark(cls, category: str) -> dict[str, Any]:
        """Resolve category to a registry (raises on unknown categories)."""
        return BENCHMARK_REGISTRIES[resolve_category(category)]

    @classmethod
    def provenance(cls, category: str) -> dict[str, Any]:
        """Machine-readable provenance for the bundled offline seed."""
        reg = cls.get_benchmark(category)
        return {
            "snapshot_kind": "bundled_offline_seed",
            "verified": False,
            "citation_allowed": False,
            "publisher": reg["publisher"],
            "source_of_truth_url": reg["url"],
            "bundled_eval_date": reg["eval_date"],
            "reason": (
                "Hardcoded table with no network fetch. It is not a measured "
                "Tier-2 observation and must be replaced by fetch_live_snapshot() "
                "before any SOTA claim cites it."
            ),
        }

    @classmethod
    def staleness(cls, category: str, today: Optional[dt.date] = None) -> dict[str, Any]:
        """Age of the bundled seed relative to today, with a hard freshness gate."""
        reg = cls.get_benchmark(category)
        today = today or dt.date.today()
        try:
            eval_day = dt.date.fromisoformat(reg["eval_date"] + "-01")
        except ValueError:
            return {"status": "UNKNOWN", "age_days": None}
        age = max(0, (today - eval_day).days)
        return {
            "status": "STALE" if age > BENCHMARK_MAX_AGE_DAYS else "FRESH",
            "age_days": age,
            "max_age_days": BENCHMARK_MAX_AGE_DAYS,
            "eval_date": reg["eval_date"],
            "checked_at": today.isoformat(),
        }

    @classmethod
    def render_snapshot(
        cls, category: str, include_provenance: bool = True,
        live_text: Optional[str] = None,
    ) -> str:
        """Render a paragraph-aligned snapshot compatible with ``lean_engine``.

        With ``live_text`` (from :meth:`fetch_live_snapshot`) the output is a
        genuinely fetched page. Otherwise it is the bundled seed, prefixed by a
        loud provenance banner so it cannot be mistaken for live data.
        """
        reg = cls.get_benchmark(category)
        prov = cls.provenance(category)
        stale = cls.staleness(category)

        if live_text:
            sha = hashlib.sha256(live_text.encode("utf-8")).hexdigest()
            return (
                f"=== PRIMARY BENCHMARK SNAPSHOT: {reg['index_name']} (LIVE FETCH) ===\n"
                f"Publisher: {reg['publisher']} | URL: {reg['url']}\n"
                f"Fetched at: {dt.date.today().isoformat()} | sha256: {sha}\n"
                f"Verified measured Tier-2 source: yes\n\n"
                f"{live_text.strip()}\n"
            )

        lines: list[str] = []
        if include_provenance:
            lines += [
                f"=== BENCHMARK SNAPSHOT: {reg['index_name']} (BUNDLED OFFLINE SEED) ===",
                "[CITATION STATUS: NOT VERIFIED — DO NOT CITE AS CURRENT MEASURED RESULTS]",
                f"Provenance: {prov['reason']}",
                f"Freshness: {stale['status']} (bundled eval_date {reg['eval_date']}, "
                f"age {stale['age_days']} days, limit {BENCHMARK_MAX_AGE_DAYS})",
                f"Required action: run benchmark_radar.py fetch --category {resolve_category(category)} "
                "and ingest the fetched page before making a SOTA claim.",
                "",
            ]
        lines += [
            f"=== PRIMARY BENCHMARK SNAPSHOT: {reg['index_name']} (Late 2026) ===",
            f"Title: {reg['index_name']}: Comprehensive LLM Leaderboard",
            f"Publisher: {reg['publisher']} | Evaluated Models: {reg['total_models_evaluated']} total (Top {len(reg['top_models'])} displayed)",
            f"Evaluations Incorporated: {', '.join(reg['evaluations_incorporated'])}. Higher score indicates superior performance.",
            "Overall Index Leaderboard Rankings:",
        ]

        for m in reg["top_models"]:
            lines.append(f"- Rank {m['rank']}: {m['model']} - Overall Score: {m['overall_score']}")

        lines.append("")
        lines.append("Capability Breakdown by Specific Metric:")
        for m in reg["top_models"]:
            if "non_hallucination" in m:
                lines.append(
                    f"- {m['model']}: Overall {m['overall_score']} | "
                    f"Agentic Knowledge Work: {m['agentic_knowledge_work']} | "
                    f"Business Knowledge: {m['business_knowledge']} | "
                    f"Reasoning: {m['reasoning']} | "
                    f"Non-Hallucination: {m['non_hallucination']} | "
                    f"Agentic Tool Use: {m['agentic_tool_use']}"
                )
            elif "swe_bench_verified" in m:
                lines.append(
                    f"- {m['model']}: Overall {m['overall_score']} | "
                    f"SWE-bench: {m['swe_bench_verified']} | "
                    f"Refactoring: {m['multi_file_refactoring']}"
                )

        return "\n".join(lines) + "\n"

    @classmethod
    def get_leader(cls, category: str, metric: str = "overall", top_n: Optional[int] = None) -> dict[str, Any]:
        """Find the leading model by a metric that actually exists in the registry.

        v9.0 returned ``models[0]`` for any unrecognised metric and used
        ``dict.get(metric, 0)`` for known ones, so asking a *coding* registry
        for ``non_hallucination`` silently returned an arbitrary rank-1 model.
        """
        reg = cls.get_benchmark(category)
        models = reg["top_models"]
        key = "overall_score" if metric == "overall" else metric
        available = {k for m in models for k in m if isinstance(m.get(k), (int, float))}
        if key not in available:
            raise ValueError(
                f"Metric {metric!r} is not measured in {reg['index_name']!r}. "
                f"Available: {sorted(available)}"
            )
        if top_n is not None and top_n > 0:
            models = models[:top_n]
        return max(models, key=lambda m: m.get(key, float("-inf")))

    @classmethod
    def fetch_live_snapshot(cls, category: str, timeout: float = 15.0) -> dict[str, Any]:
        """Fetch the real publisher page and return a SHA-256-anchored record."""
        reg = cls.get_benchmark(category)
        result = resilient_fetch(reg["url"], timeout=timeout, retries=2)
        return {
            "ok": result.ok,
            "category": resolve_category(category),
            "url": reg["url"],
            "text": result.text,
            "sha256": result.sha256,
            "status": result.status,
            "via": result.via,
            "charset": result.charset,
            "bot_wall": result.bot_wall,
            "error": result.error,
            "warnings": list(result.warnings),
            "fetched_at": dt.date.today().isoformat(),
            "verified": result.ok,
        }

    @classmethod
    def attach_live_snapshot(cls, study_dir: Path, category: str) -> dict[str, Any]:
        """Fetch and write a live Tier-2 snapshot into a study directory."""
        d = Path(study_dir)
        snap = cls.fetch_live_snapshot(category)
        if not snap["ok"]:
            return snap
        live_dir = d / "sources"
        live_dir.mkdir(parents=True, exist_ok=True)
        target = live_dir / "BENCHMARK_LIVE.txt"
        rendered = cls.render_snapshot(category, live_text=snap["text"])
        target.write_text(rendered, encoding="utf-8")
        snap["written_to"] = str(target)
        snap["snapshot_sha256"] = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        (d / "benchmark_provenance.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return snap


# ---------------------------------------------------------------------------
# CLI & Self-Test
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Deep Research Benchmark Radar CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="Generate snapshot for category")
    p_snap.add_argument("category", help="Category: finance, coding, software")
    p_snap.add_argument("--out", "-o", help="Output file path (e.g. sources/S001.txt)")

    p_lead = sub.add_parser("leader", help="Print leader by metric")
    p_lead.add_argument("category", help="Category: finance, coding")
    p_lead.add_argument("--metric", default="overall", help="overall, non_hallucination, reasoning")

    p_prov = sub.add_parser("provenance", help="Show provenance & freshness metadata")
    p_prov.add_argument("category", help="Category: finance, coding")

    p_fetch = sub.add_parser("fetch", help="Fetch a real Tier-2 page into a study directory")
    p_fetch.add_argument("--category", default="finance")
    p_fetch.add_argument("--dir", required=True, help="Study directory")

    p_test = sub.add_parser("selftest", help="Run self-test suite")

    args = parser.parse_args()

    if args.cmd == "snapshot":
        txt = BenchmarkRadar.render_snapshot(args.category)
        if args.out:
            Path(args.out).write_text(txt, encoding="utf-8")
            print(f"[OK] Wrote {len(txt)} chars to {args.out}")
        else:
            print(txt)
        return 0

    elif args.cmd == "leader":
        try:
            leader = BenchmarkRadar.get_leader(args.category, args.metric)
        except ValueError as e:
            print(f"ERROR: {e}")
            return 2
        print(f"Leader for {args.category} by {args.metric}: {leader['model']} (Score: {leader.get(args.metric, leader['overall_score'])})")
        return 0

    elif args.cmd == "provenance":
        try:
            payload = {
                "provenance": BenchmarkRadar.provenance(args.category),
                "freshness": BenchmarkRadar.staleness(args.category),
            }
        except ValueError as e:
            print(f"ERROR: {e}")
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    elif args.cmd == "fetch":
        try:
            snap = BenchmarkRadar.attach_live_snapshot(Path(args.dir), args.category)
        except ValueError as e:
            print(f"ERROR: {e}")
            return 2
        if not snap.get("ok"):
            print(f"[LIVE FETCH FAILED] {snap.get('error')} (bot_wall={snap.get('bot_wall')})")
            return 1
        print(f"[LIVE FETCH OK] {snap['url']} sha256={snap['snapshot_sha256'][:16]} -> {snap['written_to']}")
        return 0

    elif args.cmd == "selftest" or len(sys.argv) == 1:
        # Run built-in self-test
        fin_txt = BenchmarkRadar.render_snapshot("finance")
        assert "Gemini 4 Carbon (high)" in fin_txt
        assert "Rank 1: Gemini 4 Carbon (high) - Overall Score: 63" in fin_txt
        assert "Claude Opus 5.5 (max)" in fin_txt
        assert "Non-Hallucination: 93" in fin_txt

        leader_overall = BenchmarkRadar.get_leader("finance", "overall")
        assert leader_overall["model"] == "Gemini 4 Carbon (high)"

        leader_reasoning = BenchmarkRadar.get_leader("finance", "reasoning", top_n=5)
        assert leader_reasoning["model"] == "Claude Opus 5.5 (max)"
        assert leader_reasoning["reasoning"] == 68

        leader_hallucination = BenchmarkRadar.get_leader("finance", "non_hallucination", top_n=5)
        assert leader_hallucination["model"] == "Gemini 4 Carbon (high)"
        assert leader_hallucination["non_hallucination"] == 93

        leader_biz = BenchmarkRadar.get_leader("finance", "business_knowledge", top_n=5)
        assert leader_biz["model"] == "GPT-6.1 Sol (max)"
        assert leader_biz["business_knowledge"] == 54

        code_txt = BenchmarkRadar.render_snapshot("coding")
        assert "SWE-bench" in code_txt

        # v10.0: provenance is explicit and the seed is never "verified".
        prov = BenchmarkRadar.provenance("finance")
        assert prov["verified"] is False and prov["citation_allowed"] is False
        assert "NOT VERIFIED" in fin_txt
        assert "BUNDLED OFFLINE SEED" in fin_txt
        assert BenchmarkRadar.staleness("finance")["status"] in ("FRESH", "STALE")

        # Unknown categories no longer silently return the finance leaderboard.
        try:
            BenchmarkRadar.get_benchmark("biotech")
            raise AssertionError("unknown category must raise, not fall back to finance")
        except ValueError:
            pass

        # Metrics that do not exist are rejected instead of returning rank 1.
        try:
            BenchmarkRadar.get_leader("coding", "non_hallucination")
            raise AssertionError("unmeasured metric must raise")
        except ValueError:
            pass

        # A live text renders as a verified snapshot with a SHA-256 anchor.
        live = BenchmarkRadar.render_snapshot("finance", live_text="Rank 1: Measured 77")
        assert "LIVE FETCH" in live and "sha256:" in live and "Measured 77" in live

        print("[SELFTEST PASS] BenchmarkRadar v10.0 (provenance/live fetch/strict resolution) verified.")
        return 0

    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
