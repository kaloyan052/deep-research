#!/usr/bin/env python3
"""
dr_engine/evals/eval_runner.py — Epistemic Quality Benchmark Harness (v3.0)

Inspired by openai/evals.
Evaluates research claims, sources, deterministic calculations, and confidence declarations
against standardized epistemic benchmarks (E6, E8, R3, R6, R7, R8, R10) to verify 100%
precision and recall without regression.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dr_engine" / "tools"))

import calc  # noqa: E402
import check_report  # noqa: E402
import formula  # noqa: E402
import gate  # noqa: E402
import traps  # noqa: E402


DEFAULT_BENCHMARK = Path(__file__).resolve().parent / "benchmarks" / "epistemic_evals.jsonl"


def run_single_eval(case: Dict[str, Any]) -> Dict[str, Any]:
    case_id = case.get("id", "unknown")
    case_type = case.get("type", "general")
    expected_verdict = case.get("expected_verdict", "PASS")
    expected_code = case.get("expected_code")

    actual_verdict = "PASS"
    actual_code = None
    detail = ""

    if case_type == "source_tier_integrity":
        url = case.get("url", "")
        tier = case.get("tier", "T1")
        publisher = case.get("publisher", "")
        err = traps.check_source_tier_inflation(url, tier, publisher)
        if err:
            actual_verdict = "FAIL"
            actual_code = "E6"
            detail = err

    elif case_type == "probability_calibration":
        text = case.get("text", "")
        quote = case.get("quote", "")
        err = traps.check_uncalibrated_probabilities(text, quote)
        if err:
            actual_verdict = "FAIL"
            actual_code = "R7"
            detail = err

    elif case_type in ("killed_edge", "legal_conflation"):
        text = case.get("text", "")
        violations = traps.check_known_traps_in_text(text)
        if violations:
            actual_verdict = "FAIL"
            actual_code = "R8"
            detail = f"Asserted trap: {violations[0].get('name')}"

    elif case_type == "self_score":
        text = case.get("text", "")
        m = gate.SELF_SCORE_RE.search(text) or check_report.OVERCLAIM_RE.search(text)
        if m:
            actual_verdict = "FAIL"
            actual_code = "R6"
            detail = f"Self-score/overclaim detected: {m.group(0)}"

    elif case_type == "number_binding":
        text = case.get("text", "")
        quote = case.get("quote", "")
        bound = set(gate.numbers(quote))
        if case.get("calc_expr"):
            c_vars = {k: float(v) for k, v in (case.get("calc_vars") or {}).items()}
            c_res = calc.safe_eval(case["calc_expr"], c_vars)
            bound |= calc.bound_numbers_for_record({
                "result": c_res,
                "variables": c_vars,
                "unit": case.get("calc_unit", ""),
            })
        missing = gate.material(gate.numbers(text)) - bound
        if missing:
            is_formal_calc = bool(traps.FORMAL_CALC_RE.search(text) and gate.CALC_OPERATOR_RE.search(text))
            is_cal_sample = bool(gate.ESTIMATE_LABEL_RE.search(text) and traps.SAMPLE_SIZE_RE.search(text))
            if not (is_formal_calc or is_cal_sample):
                actual_verdict = "FAIL"
                actual_code = "R3"
                detail = f"Unbound numbers: {missing}"

    elif case_type == "calculation_integrity":
        expr = case.get("expr", "")
        variables = {k: float(v) for k, v in (case.get("variables") or {}).items()}
        stored_result = float(case.get("stored_result", 0.0))
        try:
            recomputed = calc.safe_eval(expr, variables)
            if not math.isclose(recomputed, stored_result, rel_tol=1e-7, abs_tol=1e-7):
                actual_verdict = "FAIL"
                actual_code = "E8"
                detail = f"Stored {stored_result} != recomputed {recomputed}"
        except Exception as exc:
            actual_verdict = "FAIL"
            actual_code = "E8"
            detail = f"Eval error: {exc}"

    elif case_type == "confidence_calibration":
        report_snippet = case.get("report_text", "")
        max_conf = case.get("max_confidence", "Medium")
        decl, _, _ = formula.extract_declared_confidence(report_snippet)
        if decl and formula.CONF_RANK[decl] > formula.CONF_RANK[max_conf]:
            actual_verdict = "FAIL"
            actual_code = "R10"
            detail = f"Declared '{decl}' exceeds mechanical ceiling '{max_conf}'"

    passed = (actual_verdict == expected_verdict)
    if expected_code and actual_code:
        passed = passed and (expected_code == actual_code)

    return {
        "id": case_id,
        "type": case_type,
        "expected_verdict": expected_verdict,
        "expected_code": expected_code,
        "actual_verdict": actual_verdict,
        "actual_code": actual_code,
        "passed": passed,
        "detail": detail,
    }


def run_benchmark_suite(
    benchmark_file: Path | None = None,
    output_markdown: Path | None = None,
) -> Dict[str, Any]:
    file_path = benchmark_file or DEFAULT_BENCHMARK
    if not file_path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {file_path}")

    cases = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                cases.append(json.loads(line))

    results = [run_single_eval(c) for c in cases]
    total = len(results)
    correct = sum(1 for r in results if r["passed"])
    accuracy = (correct / total) * 100 if total > 0 else 0.0

    by_type: Dict[str, Dict[str, int]] = {}
    for r in results:
        t = r["type"]
        if t not in by_type:
            by_type[t] = {"total": 0, "correct": 0}
        by_type[t]["total"] += 1
        if r["passed"]:
            by_type[t]["correct"] += 1

    summary = {
        "total_cases": total,
        "passed_cases": correct,
        "failed_cases": total - correct,
        "accuracy_pct": accuracy,
        "by_type": by_type,
        "results": results,
    }

    print("=" * 70)
    print(f"EPISTEMIC EVALS SCORECARD: {file_path.name}")
    print("=" * 70)
    print(f"Total Test Cases: {total} | Passed: {correct} | Failed: {total - correct}")
    print(f"Overall Accuracy: {accuracy:.1f}%\n")
    print("Category Breakdown:")
    for cat, stats in sorted(by_type.items()):
        cat_acc = (stats["correct"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        status_flag = "[OK]" if stats["correct"] == stats["total"] else "[FAIL]"
        print(f"  {status_flag} {cat:<25}: {stats['correct']}/{stats['total']} ({cat_acc:.0f}%)")

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("\nFailures:")
        for f_res in failures:
            print(f"  - {f_res['id']}: expected {f_res['expected_verdict']}({f_res['expected_code']}) "
                  f"got {f_res['actual_verdict']}({f_res['actual_code']}) | {f_res['detail']}")
    else:
        print("\nAll benchmark assertions PASSED with zero false positives and zero false negatives.")

    if output_markdown:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        md_lines = [
            "# Epistemic Evals Scorecard (v3.0)",
            "",
            f"- **Benchmark:** `{file_path.name}`",
            f"- **Accuracy:** **{accuracy:.1f}%** ({correct}/{total})",
            "",
            "## Category Breakdown",
            "",
            "| Category | Score | Pass Rate | Status |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for cat, stats in sorted(by_type.items()):
            cat_acc = (stats["correct"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            status_str = "PASS" if stats["correct"] == stats["total"] else "FAIL"
            md_lines.append(f"| {cat} | {stats['correct']}/{stats['total']} | {cat_acc:.0f}% | **{status_str}** |")
        md_lines.append("")
        output_markdown.write_text("\n".join(md_lines), encoding="utf-8")
        print(f"\nScorecard saved to: {output_markdown}")

    return summary


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run epistemic benchmark evaluation suite.")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK, help="Path to benchmark .jsonl file")
    parser.add_argument("--md", type=Path, help="Path to write Markdown scorecard")
    args = parser.parse_args()

    summary = run_benchmark_suite(args.benchmark, args.md)
    if summary["failed_cases"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
