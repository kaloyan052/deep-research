#!/usr/bin/env python3
"""
extract_doc.py — Automated Document Extractor with Source Grounding

Powered by Google's LangExtract library (open-source).
Extracts structured facts, contractual clauses, regulatory articles, and quantitative
metrics from lengthy documents (PDF, HTML, text), anchoring every claim to its exact
character span in the original text, and piping verified verbatim quotes directly
into the evidence.py pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import langextract as lx


PRESET_PROMPTS = {
    "prop_rules": (
        "Extract prop firm trading rules: maximum drawdown, daily loss limits, "
        "profit targets, consistency rules (CR1/CR2), minimum holding duration, "
        "news event restrictions, EA/VPS requirements, and forbidden practices."
    ),
    "legal_tax": (
        "Extract statutory and legal provisions: law articles, tax rates, filing deadlines, "
        "mandatory registration thresholds (e.g. VAT Art. 97a), DAC8/CARF reporting duties, "
        "reclassification risks (Art. 26(7)), and official regulatory sanctions."
    ),
    "quant_alpha": (
        "Extract quantitative market dynamics: Sharpe ratios, returns, out-of-sample periods, "
        "transaction costs (spread, commission, slippage, swap), intraday momentum windows, "
        "dealer gamma regimes, 0DTE statistics, and signal decay indicators."
    ),
    "general": (
        "Extract key empirical findings, numerical metrics, contractual requirements, "
        "and factual claims with exact source text spans."
    ),
}

PRESET_EXAMPLES = {
    "prop_rules": [
        lx.data.ExampleData(
            text="The maximum daily loss limit is 5% based on previous day balance, and trading is prohibited 2 minutes before red news.",
            extractions=[
                lx.data.Extraction(extraction_class="daily_loss", extraction_text="maximum daily loss limit is 5%"),
                lx.data.Extraction(extraction_class="news_rule", extraction_text="trading is prohibited 2 minutes before red news"),
            ],
        )
    ],
    "legal_tax": [
        lx.data.ExampleData(
            text="Pursuant to Art. 97a of the VAT Act, registration is mandatory 7 days before supplying services to EU entities.",
            extractions=[
                lx.data.Extraction(extraction_class="vat_rule", extraction_text="Art. 97a of the VAT Act"),
                lx.data.Extraction(extraction_class="deadline", extraction_text="mandatory 7 days before supplying services"),
            ],
        )
    ],
    "quant_alpha": [
        lx.data.ExampleData(
            text="The strategy achieves a Sharpe ratio of 1.42 out-of-sample between 2020 and 2026, with an average duration of 54 minutes.",
            extractions=[
                lx.data.Extraction(extraction_class="sharpe", extraction_text="Sharpe ratio of 1.42"),
                lx.data.Extraction(extraction_class="sample_period", extraction_text="out-of-sample between 2020 and 2026"),
                lx.data.Extraction(extraction_class="duration", extraction_text="average duration of 54 minutes"),
            ],
        )
    ],
    "general": [
        lx.data.ExampleData(
            text="The platform manages over $400,000 in simulated allocation with an annual fee of 420 EUR.",
            extractions=[
                lx.data.Extraction(extraction_class="allocation", extraction_text="$400,000 in simulated allocation"),
                lx.data.Extraction(extraction_class="fee", extraction_text="annual fee of 420 EUR"),
            ],
        )
    ],
}


def offline_heuristic_extract(text: str, category: str) -> List[Dict[str, Any]]:
    """
    Deterministic rule-and-regex extractor when running offline without Gemini API keys.
    Finds load-bearing factual sentences containing numbers, percentages, currency, or key rules.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    extractions = []
    
    number_pattern = re.compile(r"\b(?:\$|€|£)?\d+(?:\.\d+)?(?:%|k|M|bn|bps|pips|EUR|USD|BGN)?\b", re.IGNORECASE)
    keywords = {
        "prop_rules": ["drawdown", "loss", "profit", "consistency", "holding", "rule", "forbidden", "scale", "leverage", "swap", "minute", "second", "cap", "risk"],
        "legal_tax": [r"чл\.", r"art\.", "закон", "act", "данък", "tax", "ддс", "vat", "нап", "допк", "зкпо", "зддфл", "регистрация", "директива", "регламент"],
        "quant_alpha": ["sharpe", "alpha", "momentum", "decay", "spread", "cost", "sample", "0dte", "gamma", "gex", "reversal", "drift"],
        "general": ["%", "eur", "usd", "ratio", "threshold", "limit", "target", "fee"],
    }.get(category, ["%"])

    offset = 0
    for s in sentences:
        start_idx = text.find(s, offset)
        if start_idx == -1:
            start_idx = offset
        end_idx = start_idx + len(s)
        offset = end_idx

        s_clean = s.strip()
        if not s_clean or len(s_clean) < 15:
            continue

        has_number = bool(number_pattern.search(s_clean))
        matches_kw = any(kw.lower() in s_clean.lower() for kw in keywords)

        if has_number and matches_kw:
            # Classify
            ext_class = "metric_claim"
            if any(k in s_clean.lower() for k in ["drawdown", "loss", "загуба"]):
                ext_class = "loss_limit"
            elif any(k in s_clean.lower() for k in [r"чл\.", r"art\.", "данък", "tax"]):
                ext_class = "statutory_rule"
            elif any(k in s_clean.lower() for k in ["sharpe", "alpha", "моментум"]):
                ext_class = "quant_performance"

            extractions.append({
                "class": ext_class,
                "text": s_clean,
                "start": start_idx,
                "end": end_idx,
            })
            if len(extractions) >= 30:
                break

    return extractions


def run_extraction(
    file_path: str,
    category: str = "general",
    prompt: Optional[str] = None,
    api_key: Optional[str] = None,
    model_id: str = "gemini-2.5-flash",
    offline: bool = False,
    html_out: Optional[str] = None,
    json_out: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    source_id: Optional[str] = None,
    sq: str = "SQ1",
    tier: str = "T1",
    kind: str = "de_jure",
) -> List[Dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = path.read_text(encoding="utf-8", errors="ignore")
    prompt_desc = prompt or PRESET_PROMPTS.get(category, PRESET_PROMPTS["general"])
    examples = PRESET_EXAMPLES.get(category, PRESET_EXAMPLES["general"])

    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    use_online = bool(api_key) and not offline

    results: List[Dict[str, Any]] = []

    if use_online:
        print(f"[*] Running LangExtract online with model {model_id} on {path.name} ({len(text)} chars)...")
        try:
            annotated_doc = lx.extract(
                text_or_documents=text,
                prompt_description=prompt_desc,
                examples=examples,
                model_id=model_id,
                api_key=api_key,
                show_progress=True,
            )
            if hasattr(annotated_doc, "extractions") and annotated_doc.extractions:
                for ext in annotated_doc.extractions:
                    start = getattr(ext.char_interval, "start", None) if hasattr(ext, "char_interval") else None
                    end = getattr(ext.char_interval, "end", None) if hasattr(ext, "char_interval") else None
                    results.append({
                        "class": ext.extraction_class,
                        "text": ext.extraction_text,
                        "start": start,
                        "end": end,
                    })
        except Exception as e:
            print(f"[!] LangExtract online extraction failed ({e}), falling back to offline heuristic...")
            use_online = False

    if not use_online:
        print(f"[*] Running LangExtract offline heuristic extractor on {path.name} ({len(text)} chars)...")
        results = offline_heuristic_extract(text, category)

    print(f"[+] Found {len(results)} grounded candidate extractions.")

    # Create annotated document for visualization if HTML requested
    if html_out:
        lx_extractions = [
            lx.data.Extraction(
                extraction_class=r["class"],
                extraction_text=r["text"],
            )
            for r in results
        ]
        ann = lx.data.AnnotatedDocument(text=text, extractions=lx_extractions)
        html_code = lx.visualize(ann)
        out_html_path = Path(html_out)
        out_html_path.parent.mkdir(parents=True, exist_ok=True)
        out_html_path.write_text(str(html_code), encoding="utf-8")
        print(f"[+] Interactive visualization saved: {out_html_path}")

    # Output JSON if requested
    if json_out:
        out_json_path = Path(json_out)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[+] Extractions JSON saved: {out_json_path}")

    # Generate evidence.py add commands if evidence_dir and source_id are given
    if evidence_dir and source_id:
        print("\n" + "=" * 70)
        print("PIPELINE EVIDENCE COMMANDS (READY TO EXECUTE):")
        print("=" * 70)
        for i, r in enumerate(results[:10], start=1):
            quote = r["text"].replace('"', '\\"').replace("\n", " ").strip()
            # Truncate clean sentence if too long
            if len(quote) > 280:
                quote = quote[:277] + "..."
            claim = f"{r['class'].replace('_', ' ').capitalize()}: {quote[:60]}..."
            cmd = (
                f".venv\\Scripts\\python.exe dr_engine\\tools\\evidence.py add "
                f"--dir {evidence_dir} --source {source_id} --sq {sq} "
                f"--tier {tier} --kind {kind} --stance supports "
                f'--quote "{quote}" --claim "{claim}"'
            )
            print(f"{i}. {cmd}\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured facts with exact source grounding using Google LangExtract."
    )
    parser.add_argument("file", help="Path to input document (txt, html, md, etc.)")
    parser.add_argument(
        "--type",
        dest="category",
        choices=["prop_rules", "legal_tax", "quant_alpha", "general"],
        default="general",
        help="Preset category schema for extraction",
    )
    parser.add_argument("--prompt", help="Custom extraction prompt instruction")
    parser.add_argument("--api-key", help="Gemini API Key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model ID")
    parser.add_argument("--offline", action="store_true", help="Force deterministic offline extraction")
    parser.add_argument("--html", help="Path to write interactive HTML visualization")
    parser.add_argument("--json", help="Path to write output JSON")
    parser.add_argument("--evidence-dir", help="Path to research directory for evidence.py commands")
    parser.add_argument("--source", dest="source_id", help="Source ID (e.g. S001) for evidence.py commands")
    parser.add_argument("--sq", default="SQ1", help="Subquestion / Kill ID (e.g. SQ1, K1)")
    parser.add_argument("--tier", default="T1", choices=["T1", "T2", "T3", "T4", "T5"], help="Source tier")
    parser.add_argument("--kind", default="de_jure", choices=["de_jure", "de_facto", "empirical", "context"], help="Evidence kind")

    args = parser.parse_args()

    try:
        run_extraction(
            file_path=args.file,
            category=args.category,
            prompt=args.prompt,
            api_key=args.api_key,
            model_id=args.model,
            offline=args.offline,
            html_out=args.html,
            json_out=args.json,
            evidence_dir=args.evidence_dir,
            source_id=args.source_id,
            sq=args.sq,
            tier=args.tier,
            kind=args.kind,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
