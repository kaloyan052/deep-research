#!/usr/bin/env python3
"""Deep Research Engine v9.0 — Turn 0 Autonomous Zero-Token Spec & Skeptic Swarm Engine.

Takes a raw 1-sentence research prompt and autonomously:
  1. Classifies the epistemic domain (`quant`, `saas`, `biotech`, `legal`, `deeptech`).
  2. Extracts core technical entities and formulates 4 orthogonal Sub-Questions (SQ1..SQ4).
  3. Deploys the Adversarial Skeptic Swarm to generate 3 falsifiable Kill Hypotheses (K1..K3)
     and disconfirmation search vectors (hunting postmortems, regime decay, and friction traps).
  4. Queries keyless primary registries (OpenAlex, arXiv, CrossRef) and practitioner communities
     (Reddit, Hacker News, StackExchange via `community_engine.py`).
  5. Reconstructs OpenAlex inverted-index abstracts and arXiv summaries into `inline_sources`
     while optimizing URL selection for Inverse-HHI hostname diversity (N_eff >= 4.0).
  6. Emits a complete `study_spec.json` ready for `lean_engine.py ingest`.

Pure Python 3.10+ stdlib. Zero LLM tokens. Zero paid API keys. Windows cp1252-safe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.dethrone import (  # noqa: E402
    RECENCY_WINDOWS_DAYS,
    build_dethroning_vectors,
    detect_superlative_claims,
    extract_leader_value,
)
from dr_engine.tools.ead_gate import PROTOCOL_VERSION, render_ead_template  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; DR-AutoSpec/12.0; +https://dr-engine.local/epistemic)"

# v10.0: fail-loud collector provenance. v9.0 swallowed every network error
# with `except Exception: pass`, so a total blackout emitted a "complete"
# study_spec with zero sources and no warning.
LAST_COLLECTION_REPORT: dict[str, list[dict[str, str]]] = {"ok": [], "failed": []}


def _report(name: str, ok: bool, detail: str) -> None:
    LAST_COLLECTION_REPORT["ok" if ok else "failed"].append(
        {"collector": name, "detail": str(detail)[:200]}
    )


def _year_of(value: object, default: int = 0) -> int:
    """Parse a 4-digit year honestly; unknown -> ``default`` (never a fake year)."""
    s = str(value or "")[:4]
    return int(s) if s.isdigit() and 1900 <= int(s) <= 2100 else default

STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "are", "was", "were",
    "have", "has", "not", "but", "what", "all", "when", "can", "more", "than",
    "into", "only", "other", "such", "their", "which", "would", "about", "there",
    "how", "does", "why", "what", "evaluate", "analyze", "research", "study",
    "impact", "effect", "using", "based", "between", "across", "under", "over",
}

DOMAIN_LEXICONS: dict[str, tuple[str, ...]] = {
    "quant": (
        "0dte", "gamma", "gex", "vanna", "charm", "futures", "microstructure", "slippage",
        "sharpe", "alpha", "order flow", "lob", "intraday", "m15", "h1", "options",
        "volatility", "cointegration", "stat arb", "fx", "dax", "us100", "nq", "spx",
        "spread", "dealer hedging", "auction", "imbalance", "prop firm", "drawdown",
    ),
    "saas": (
        "saas", "b2b", "churn", "arr", "mrr", "cac", "ltv", "pricing", "subscription",
        "shopify", "stripe", "webhook", "api quota", "erp", "crm", "workflow", "plugin",
        "extension", "self-serve", "enterprise", "seat", "onboarding", "retention",
    ),
    "biotech": (
        "clinical", "phase 2", "phase 3", "fda", "ema", "biomarker", "surrogate",
        "endpoint", "pharmacokinetics", "half-life", "dosage", "toxicity", "adverse event",
        "placebo", "cohort", "randomized", "longevity", "peptides", "glp-1", "receptor",
        "oncology", "assay", "in vivo", "bioavailability", "titration",
    ),
    "legal": (
        "tax", "statute", "irc", "regulation", "compliance", "safe harbor", "withholding",
        "vat", "зддфл", "зкпо", "нап", "еоод", "treaty", "nexus", "audit", "deduction",
        "directive", "court", "precedent", "liability", "fiduciary", "gdpr", "filing",
    ),
    "deeptech": (
        "semiconductor", "asic", "fpga", "gpu", "battery", "thermodynamic", "carnot",
        "energy density", "wh/kg", "watts", "bom", "wafer", "yield", "photonics",
        "robotics", "actuator", "sensor", "lidar", "Grid", "inverter", "electrolysis",
    ),
    # v10.0: the AI/SOTA frontier was NOT a domain at all. v9.0 gated B9 and
    # `is_model_query` on ("ai","tech","software","finance") -- all unreachable
    # -- so the engine's flagship anti-citation-lag rule never fired.
    "ai": (
        "llm", "foundation model", "chatbot arena", "artificial analysis", "sota",
        "leaderboard", "frontier model", "gpt-", "claude", "gemini", "benchmark index",
        "ai model", "language model", "swe-bench", "lmarena", "non-hallucination",
    ),
}

# Domain-specific Adversarial Skeptic Swarm templates: (K1_friction, K2_decay, K3_liability)
SKEPTIC_SWARM_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "quant": {
        "K1": {
            "hypothesis": (
                "Round-turn execution friction (top-of-book spread widening + market-order slippage "
                "+ exchange fees) exceeds 3.0% of the 1R structural stop or consumes >= 100% of gross edge."
            ),
            "search_suffix": "slippage spread widening execution friction commission capacity decay",
        },
        "K2": {
            "hypothesis": (
                "The signal decayed post-2023 as institutional market makers internalized flow "
                "or front-ran the anomaly window."
            ),
            "search_suffix": "alpha decay post-2023 crowded trade front-running refuted",
        },
        "K3": {
            "hypothesis": (
                "Tail-risk inventory drawdowns during illiquid regime transitions or overnight/funding "
                "charges invalidate risk-adjusted expectancy."
            ),
            "search_suffix": "tail risk drawdown liquidity drought margin call blowup",
        },
    },
    "saas": {
        "K1": {
            "hypothesis": (
                "Customer acquisition friction and monthly logo churn require replacing more clients "
                "per month than a solo non-sales operator can acquire organically."
            ),
            "search_suffix": "churn rate cancel subscription billing complaint switching cost",
        },
        "K2": {
            "hypothesis": (
                "Frontier LLM native capabilities or incumbent platform bundling solve 80% of the "
                "workflow at zero marginal cost (ChatGPT Wrapper / Bundling Kill)."
            ),
            "search_suffix": "native feature bundled free alternative wrapper obsolete",
        },
        "K3": {
            "hypothesis": (
                "Two-way mutating API sync bugs, rate-limit quotas, or mission-critical data liability "
                "create unsustainable 24/7 support burden."
            ),
            "search_suffix": "api rate limit broken sync downtime data loss support nightmare",
        },
    },
    "biotech": {
        "K1": {
            "hypothesis": (
                "Phase 2 effect size suffers >= 40% Winner's Curse shrinkage in Phase 3 or fails "
                "to translate from surrogate biomarker to hard clinical endpoint."
            ),
            "search_suffix": "Phase 3 failure surrogate endpoint discordance effect size shrinkage",
        },
        "K2": {
            "hypothesis": (
                "Dose-limiting toxicities, Grade >= 3 adverse events, or real-world non-adherence "
                "exceed 20% discontinuation threshold."
            ),
            "search_suffix": "adverse events discontinuation rate toxicity tolerability dropout",
        },
        "K3": {
            "hypothesis": (
                "Subgroup p-hacking, underpowered sample size (power < 80%), or active-comparator "
                "selection bias invalidates statistical significance under multiplicity correction."
            ),
            "search_suffix": "post-hoc subgroup p-hacking publication bias failed replication",
        },
    },
    "legal": {
        "K1": {
            "hypothesis": (
                "Non-binding administrative guidance or out-of-jurisdiction precedent is contradicted "
                "by binding statutory text or appellate rulings."
            ),
            "search_suffix": "statutory text court ruling invalidated administrative guidance",
        },
        "K2": {
            "hypothesis": (
                "Substance-over-form or step-transaction anti-abuse doctrines reclassify the structure, "
                "triggering retroactive tax, interest, and statutory penalties."
            ),
            "search_suffix": "substance over form reclassification audit penalty retroactive",
        },
        "K3": {
            "hypothesis": (
                "Annual compliance, reporting, accounting, and audit-defense friction exceeds the "
                "gross tax or regulatory arbitrage savings."
            ),
            "search_suffix": "compliance cost reporting burden filing rejection audit trigger",
        },
    },
    "deeptech": {
        "K1": {
            "hypothesis": (
                "Claimed system efficiency or energy density violates thermodynamic/physical limits "
                "(> 95% of Carnot/Shannon/Shockley-Queisser limit) or parasitic balance-of-plant losses."
            ),
            "search_suffix": "thermodynamic limit parasitic loss thermal throttling degradation",
        },
        "K2": {
            "hypothesis": (
                "Low-Rate Initial Production (LRIP) manufacturing yield losses and BOM unit costs "
                "prevent positive gross margin at realistic volume."
            ),
            "search_suffix": "manufacturing yield loss BOM cost overrun scaling bottleneck",
        },
        "K3": {
            "hypothesis": (
                "Single-source geopolitical or foundry supply-chain dependencies create an unhedgeable "
                "lead-time or export-control single point of failure."
            ),
            "search_suffix": "supply chain bottleneck single source lead time shortage",
        },
    },
    # v10.0: AI/SOTA-specific disconfirmation vectors (benchmark staleness,
    # vendor self-reporting, and cost/latency physics).
    "ai": {
        "K1": {
            "hypothesis": (
                "The cited leaderboard is stale or a bundled offline seed: the model ranking changed "
                "within the last evaluation cycle, so the 'current SOTA' claim is already obsolete."
            ),
            "search_suffix": "leaderboard update deprecated model benchmark revision staleness",
        },
        "K2": {
            "hypothesis": (
                "The superiority claim rests on vendor-reported or in-distribution numbers rather than "
                "an independent Tier-2 measured benchmark, or is an artifact of prompt/contamination leakage."
            ),
            "search_suffix": "vendor self reported contamination benchmark overfit independent evaluation",
        },
        "K3": {
            "hypothesis": (
                "Inference cost, latency, context limits or rate quotas at production volume erase the "
                "capability advantage in the actual deployment economics."
            ),
            "search_suffix": "inference cost latency rate limit production throughput scaling",
        },
    },
    # v10.0: an unmatched prompt must not silently become a quant study (which
    # would apply the 3% friction gate and alpha-decay kills to a legal or
    # medical question). "general" gets neutral, domain-agnostic kills.
    "general": {
        "K1": {
            "hypothesis": (
                "The central claim is supported only by secondary or self-interested sources and is "
                "contradicted by primary documents or independent measurements."
            ),
            "search_suffix": "primary source contradiction independent verification refuted",
        },
        "K2": {
            "hypothesis": (
                "The evidence base is temporally stale relative to the current regime, so the "
                "conclusion no longer holds."
            ),
            "search_suffix": "post publication regime change decay superseded withdrawn",
        },
        "K3": {
            "hypothesis": (
                "Implementation friction, unit economics or operational liability exceeds the "
                "claimed benefit once measured end-to-end."
            ),
            "search_suffix": "hidden cost implementation failure operational burden breakeven",
        },
    },
}


@dataclass
class CandidateLead:
    title: str
    url: str
    host: str
    source_type: str  # "academic" | "preprint" | "community_pain" | "community_tech" | "adversarial"
    inline_text: str = ""
    score: float = 0.0
    # v10.0: 0 means "unknown", NOT 2026. A fabricated current year would
    # silently win the recency tie-break in `optimize_lead_diversity` and feed
    # the B9 temporal gate.
    pub_year: int = 0


def classify_prompt_domain(prompt: str) -> str:
    """Deterministically classify a prompt into one of 6 domains (or ``general``).

    v10.0: unmatched prompts no longer default to ``quant``. Assuming a quant
    domain for an unrelated question applied the 3% friction gate, alpha-decay
    kills and microstructure sub-questions to legal, medical and AI studies.
    """
    low = prompt.lower()
    scores: dict[str, int] = {d: 0 for d in DOMAIN_LEXICONS}
    for dom, keywords in DOMAIN_LEXICONS.items():
        for kw in keywords:
            if kw.lower() in low:
                scores[dom] += 2 if " " in kw else 1
    best_dom = max(scores, key=lambda d: scores[d])
    return best_dom if scores[best_dom] > 0 else "general"


# v12.0: O_dethrone needs a *named* leader, not the first two tokens of the
# prompt. "Who holds the deadlift world record of 510 kg" has no leader name;
# "Hafþór Björnsson holds ..." does. Interrogatives and method verbs are
# excluded, and a single capitalised word at sentence start is not a person.
_LEADER_STOPWORDS = frozenset({
    "who", "what", "which", "when", "where", "why", "how", "is", "are", "was",
    "does", "do", "still", "holds", "hold", "the", "a", "an", "of", "for",
    "and", "current", "best", "top", "leading", "new", "evaluate", "assess",
    "analyze", "analyse", "compare", "determine", "estimate", "investigate",
    "world", "record", "state", "sota", "model", "llm",
})
_PROPER_NAME_RE = re.compile(
    r"\b([A-ZÀ-ÞА-ЯЁ][^\W\d_]{1,}(?:\s+[A-ZÀ-ÞА-ЯЁ][^\W\d_]{1,}){1,2})\b"
)


def infer_leader(prompt: str) -> str:
    """Extract a plausible named leader; fall back to an honest generic label.

    Never fabricates a person. When the prompt contains no proper name the
    adversarial vectors target "the current leader" instead of silently
    turning an interrogative into a named entity.
    """
    low = str(prompt or "").lower()
    for match in _PROPER_NAME_RE.finditer(str(prompt or "")):
        words = match.group(1).split()
        if any(w.lower() in _LEADER_STOPWORDS for w in words):
            continue
        if any(w.isdigit() for w in words):
            continue
        return " ".join(words)[:80]
    return "the current leader"


def extract_core_entities(prompt: str, max_terms: int = 6) -> list[str]:
    """Extracts high-signal technical tokens, tickers, statutes, and multi-word phrases."""
    # Preserve hyphenated terms, alphanumeric codes (0DTE, US100, GLP-1, M15), and Cyrillic words
    raw_tokens = re.findall(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_./§-]{2,}", prompt)
    kept: list[str] = []
    seen: set[str] = set()
    for tok in raw_tokens:
        clean = tok.strip(".,;:!?()[]{}")
        low = clean.lower()
        if len(clean) < 3 or low in STOPWORDS or low in seen:
            continue
        seen.add(low)
        kept.append(clean)
    return kept[:max_terms]


def build_adversarial_spec_skeleton(prompt: str) -> dict[str, Any]:
    """Synthesizes deterministic Sub-Questions (SQ1..SQ4), Kill Hypotheses (K1..K3),
    and Adversarial Search Queries from a raw 1-sentence prompt with zero LLM tokens."""
    domain = classify_prompt_domain(prompt)
    entities = extract_core_entities(prompt)
    core_focus = " ".join(entities) if entities else prompt.strip()
    swarm = SKEPTIC_SWARM_TEMPLATES[domain]

    sub_questions = {
        "SQ1": f"Primary mechanism and structural physics of {core_focus} ({domain} domain)",
        "SQ2": f"Empirical magnitude, out-of-sample survival (2023-2026), and heterogeneity across regimes for {core_focus}",
        "SQ3": f"Friction, unit-economics breakeven, and execution/operational cost structure of {core_focus}",
        "SQ4": f"Adversarial postmortems, practitioner failure modes, and regulatory/counterparty constraints on {core_focus}",
    }

    kill_hypotheses = {
        "K1": {
            "query": f"{core_focus} {swarm['K1']['search_suffix']}",
            "hypothesis": swarm["K1"]["hypothesis"],
        },
        "K2": {
            "query": f"{core_focus} {swarm['K2']['search_suffix']}",
            "hypothesis": swarm["K2"]["hypothesis"],
        },
        "K3": {
            "query": f"{core_focus} {swarm['K3']['search_suffix']}",
            "hypothesis": swarm["K3"]["hypothesis"],
        },
    }

    # v10.0: `.split()[1]` raised IndexError for a one-word suffix. Slice safely.
    pain_terms = " ".join(swarm["K1"]["search_suffix"].split()[:2])
    search_vectors = {
        "primary_academic": core_focus,
        "practitioner_pain": f"{core_focus} {pain_terms}".strip(),
        "practitioner_tech": f"{core_focus} workaround implementation benchmark",
        "skeptic_k1": kill_hypotheses["K1"]["query"],
        "skeptic_k2": kill_hypotheses["K2"]["query"],
    }

    return {
        "prompt": prompt.strip(),
        "domain": domain,
        "entities": entities,
        "core_focus": core_focus,
        "sub_questions": sub_questions,
        "kill_hypotheses": kill_hypotheses,
        "search_vectors": search_vectors,
    }


# ---------------------------------------------------------------------------
# Keyless Scientific & Registry Connectors (OpenAlex, arXiv, CrossRef)
# ---------------------------------------------------------------------------
def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Reconstructs verbatim plain-text abstract from OpenAlex's `abstract_inverted_index`."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    pos_map: dict[int, str] = {}
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for p in positions:
                if isinstance(p, int):
                    pos_map[p] = word
    if not pos_map:
        return ""
    max_pos = max(pos_map.keys())
    words = [pos_map.get(i, "") for i in range(max_pos + 1)]
    text = " ".join(w for w in words if w)
    return re.sub(r"\s+", " ", text).strip()


def query_openalex_works(query: str, max_results: int = 4, timeout: float = 12.0) -> list[CandidateLead]:
    """Query OpenAlex with relevance + recency ranking, NOT citation count.

    v9.0 used ``sort=cited_by_count:desc`` and ``score = cited_by + 15``. That
    is precisely the Academic Citation Lag the mission exists to eliminate: a
    2021 paper with 900 citations outranked a 2026 result with 3. v10.0 ranks
    by relevance, applies a bounded log citation prior and an explicit recency
    bonus, and records every failure in ``LAST_COLLECTION_REPORT``.
    """
    q_enc = urllib.parse.quote_plus(query)
    api_url = (
        f"https://api.openalex.org/works?search={q_enc}"
        f"&filter=from_publication_date:2021-01-01,has_abstract:true"
        f"&sort=relevance_score:desc&per-page={max_results}"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    leads: list[CandidateLead] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        for item in data.get("results") or []:
            title = str(item.get("title") or "OpenAlex Study").strip()
            pub_year = _year_of(item.get("publication_year"))
            cited_by = int(item.get("cited_by_count") or 0)
            doi = item.get("doi") or item.get("id") or ""
            oa_url = (item.get("open_access") or {}).get("oa_url") or doi
            abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
            if len(abstract) < 80:
                continue
            authors = [
                (a.get("author") or {}).get("display_name", "")
                for a in (item.get("authorships") or [])[:3]
            ]
            auth_str = ", ".join(a for a in authors if a) or "OpenAlex Authors"
            host = urllib.parse.urlparse(str(oa_url)).hostname or "openalex.org"
            recency_bonus = max(0.0, (pub_year - 2020) * 5.0) if pub_year else 0.0
            score = 20.0 + recency_bonus + min(20.0, math.log1p(max(0, cited_by)) * 2.0)
            snapshot_body = (
                f"=== PRIMARY SCIENTIFIC REGISTRY SNAPSHOT (OpenAlex) ===\n"
                f"Title: {title}\n"
                f"Authors: {auth_str} | Year: {pub_year or 'unknown'} | Citations: {cited_by} | DOI: {doi}\n\n"
                f"Abstract: {abstract}\n"
            )
            leads.append(
                CandidateLead(
                    title=title, url=str(oa_url), host=host.removeprefix("www."),
                    source_type="academic", inline_text=snapshot_body,
                    score=float(score), pub_year=pub_year,
                )
            )
        _report("openalex", True, f"{len(leads)} works")
    except Exception as exc:
        _report("openalex", False, f"{type(exc).__name__}: {exc}")
    return leads


def query_arxiv_preprints(query: str, max_results: int = 3, timeout: float = 12.0) -> list[CandidateLead]:
    """Queries the keyless arXiv Atom API and extracts full abstract snapshots."""
    q_enc = urllib.parse.quote_plus(f"all:{query}")
    # v10.0: HTTPS (v9.0 used plaintext HTTP) and honest unknown dates.
    api_url = f"https://export.arxiv.org/api/query?search_query={q_enc}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    leads: list[CandidateLead] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = re.sub(r"\s+", " ", (entry.findtext("atom:title", "", ns) or "").strip())
            summary = re.sub(r"\s+", " ", (entry.findtext("atom:summary", "", ns) or "").strip())
            link_id = (entry.findtext("atom:id", "", ns) or "").strip()
            published = (entry.findtext("atom:published", "", ns) or "")[:10]
            pub_year = _year_of(published)
            if len(summary) < 80 or not link_id:
                continue
            snapshot_body = (
                f"=== ARXIV PREPRINT SNAPSHOT ===\n"
                f"Title: {title}\n"
                f"Published: {published or 'unknown'} | URL: {link_id}\n\n"
                f"Abstract: {summary}\n"
            )
            leads.append(
                CandidateLead(
                    title=title, url=link_id, host="arxiv.org",
                    source_type="preprint", inline_text=snapshot_body,
                    score=25.0 + (5.0 if pub_year >= 2025 else 0.0), pub_year=pub_year,
                )
            )
        _report("arxiv", True, f"{len(leads)} preprints")
    except Exception as exc:
        _report("arxiv", False, f"{type(exc).__name__}: {exc}")
    return leads


# ---------------------------------------------------------------------------
# Inverse-HHI Hostname Diversity Optimizer
# ---------------------------------------------------------------------------
def optimize_lead_diversity(
    candidates: list[CandidateLead],
    max_per_host: int = 2,
    max_total: int = 12,
) -> tuple[list[CandidateLead], float]:
    """Selects top leads while enforcing per-hostname caps to maximize Inverse-HHI N_eff."""
    ordered = sorted(candidates, key=lambda c: (c.score, c.pub_year), reverse=True)
    selected: list[CandidateLead] = []
    host_counts: dict[str, int] = {}
    seen_urls: set[str] = set()

    for c in ordered:
        if c.url in seen_urls:
            continue
        h = (c.host or "unknown").lower().removeprefix("www.")
        if host_counts.get(h, 0) >= max_per_host:
            continue
        seen_urls.add(c.url)
        host_counts[h] = host_counts.get(h, 0) + 1
        selected.append(c)
        if len(selected) >= max_total:
            break

    total = len(selected)
    if total == 0:
        return [], 0.0
    hhi = sum((cnt / total) ** 2 for cnt in host_counts.values())
    n_eff = round(1.0 / hhi, 2) if hhi > 0 else 0.0
    return selected, n_eff


def generate_autonomous_study_spec(
    prompt: str,
    offline_only: bool = False,
    max_urls: int = 10,
) -> dict[str, Any]:
    """End-to-end Turn 0 compiler with fail-loud collector provenance.

    v10.0 changes vs v9.0:
      * every collector outcome is recorded in ``collector_provenance``;
        a total discovery blackout emits a warning instead of a silently
        "complete" spec with zero sources;
      * the ``ai`` domain is reachable and ``is_model_query`` no longer tests
        domains the classifier can never return;
      * benchmark radar output is explicitly marked ``unverified_bundled`` and
        is excluded from B9 grounding by ``lean_engine``;
      * unknown publication years are 0, never a fabricated current year.
    """
    global LAST_COLLECTION_REPORT
    LAST_COLLECTION_REPORT = {"ok": [], "failed": []}
    skeleton = build_adversarial_spec_skeleton(prompt)
    candidates: list[CandidateLead] = []
    warnings: list[str] = []
    unverified_inline: list[str] = []
    benchmark_provenance: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # v12.0 FRONTIER 1 — Active Dethroning Protocol (O_dethrone).
    # A "#1" / "world record" / "leading model" / "fastest" / "cheapest" /
    # "standard consensus" claim is perishable. NEVER accept the first
    # high-SEO answer: spawn adversarial recency-anchored vectors designed
    # specifically to break the identified leader before certifying it.
    # Dates come from dt.date.today(); no calendar year is hardcoded.
    # ------------------------------------------------------------------
    leader_claims = detect_superlative_claims(prompt)
    numeric = extract_leader_value(prompt)
    leader = infer_leader(prompt)
    metric = str(numeric["metric"])
    dethrone_vectors = build_dethroning_vectors(leader, metric) if leader_claims else []
    dethroning: dict[str, Any] = {
        "protocol_active": bool(leader_claims),
        "leader": leader,
        "metric": metric,
        "leader_value": numeric["value"],
        "leader_unit": numeric["unit"],
        "claim_kinds": [c.kind for c in leader_claims],
        "recency_windows_days": list(RECENCY_WINDOWS_DAYS),
        "vector_count": len(dethrone_vectors),
        "vectors": [asdict(v) for v in dethrone_vectors],
        "generated_at": dt.date.today().isoformat(),
        "required_manifest_record": (
            "manifest.dethroning[]: status intact|dethroned, vectors_run >= 8, "
            "window_days in 30|90, checked_at within 30 days, recency_verified=true, "
            "and snapshot-verified evidence_ids (Rule B11)"
        ),
    }
    for vec in dethrone_vectors:
        if vec.lang == "en":
            skeleton["search_vectors"].setdefault(
                f"dethrone_{vec.window_days}d_en", vec.query
            )
    if leader_claims:
        warnings.append(
            "SUPERLATIVE CLAIM DETECTED "
            f"({', '.join(dethroning['claim_kinds'])}): O_dethrone spawned "
            f"{len(dethrone_vectors)} adversarial vectors over the most recent "
            "30/90 days. Rule B11 will REFUSE certification until "
            "manifest.dethroning[] proves the leader was not superseded."
        )

    if not offline_only:
        # 1. Primary scientific discovery (OpenAlex + arXiv), recency-ranked.
        candidates.extend(query_openalex_works(skeleton["search_vectors"]["primary_academic"], max_results=4))
        candidates.extend(query_arxiv_preprints(skeleton["search_vectors"]["primary_academic"], max_results=2))
        # 2. Adversarial Skeptic Swarm scientific query (K1 disconfirmation).
        candidates.extend(query_openalex_works(skeleton["search_vectors"]["skeptic_k1"], max_results=2))

        # 3. Practitioner & Community discovery via `community_engine.py`.
        try:
            from dr_engine.tools.community_engine import search_community_discussions
            pain_hits = search_community_discussions(
                skeleton["core_focus"],
                platforms=["reddit", "hn", "stackexchange"],
                target_kind="review_pain", limit_per_platform=2,
            )
            tech_hits = search_community_discussions(
                skeleton["core_focus"],
                platforms=["reddit", "hn", "stackexchange"],
                target_kind="technical_lead", limit_per_platform=2,
            )
            for h in pain_hits + tech_hits:
                url = str(h.get("url") or "")
                if not url:
                    continue
                host = (urllib.parse.urlparse(url).hostname or h.get("platform", "community")).lower().removeprefix("www.")
                candidates.append(CandidateLead(
                    title=str(h.get("title") or ""), url=url, host=host,
                    source_type=f"community_{h.get('kind', 'general')}",
                    inline_text="", score=float(h.get("signal_score") or 10.0),
                    pub_year=_year_of(h.get("date")),
                ))
            _report("community_engine", True, f"{len(pain_hits) + len(tech_hits)} discussions")
        except Exception as exc:
            _report("community_engine", False, f"{type(exc).__name__}: {exc}")

        # 4. Benchmark Radar. v10.0: reachable for AI/model queries, and
        #    explicitly flagged as an UNVERIFIED bundled offline seed.
        try:
            from dr_engine.tools.benchmark_radar import BenchmarkRadar, resolve_category
            p_low = prompt.lower()
            is_model_query = any(
                w in p_low for w in (
                    "model", "ai", "llm", "sota", "best", "модел", "индекс",
                    "benchmark", "leaderboard", "arena",
                )
            )
            if is_model_query:
                cat = resolve_category("finance" if skeleton["domain"] in ("quant", "finance") else "coding")
                bm_text = BenchmarkRadar.render_snapshot(cat)
                bm_reg = BenchmarkRadar.get_benchmark(cat)
                benchmark_provenance = {
                    **BenchmarkRadar.provenance(cat),
                    "freshness": BenchmarkRadar.staleness(cat),
                    "grounds_b9": False,
                    "required_action": "run benchmark_radar.py fetch --dir <study> before citing",
                }
                unverified_inline.append(bm_reg["url"])
                candidates.append(CandidateLead(
                    title=f"{bm_reg['index_name']} (UNVERIFIED BUNDLED SEED)",
                    url=bm_reg["url"], host="artificialanalysis.ai",
                    source_type="unverified_bundled_benchmark_seed",
                    inline_text=bm_text,
                    # Deliberately low: a hardcoded seed must not outrank a
                    # fetched primary source in the diversity selection.
                    score=12.0, pub_year=0,
                ))
                _report("benchmark_radar", True, f"bundled seed ({cat}); live fetch still required")
        except Exception as exc:
            _report("benchmark_radar", False, f"{type(exc).__name__}: {exc}")

        # 5. Deep Trench & Obscure Practitioner Miner (v10.0 telemetry).
        try:
            from dr_engine.tools.trench_miner import mine_all_trenches, get_last_ledger_summary
            trench_items = mine_all_trenches(prompt, domain=skeleton["domain"], max_total_items=4)
            led = get_last_ledger_summary()
            _report(
                "trench_miner", led.get("succeeded", 0) > 0,
                f"{led.get('succeeded')}/{led.get('collectors')} collectors ok, "
                f"{led.get('items')} raw items, {led.get('bot_walled')} bot-walled",
            )
            if led.get("bot_walled"):
                warnings.append(
                    f"TRENCH BLOCKADE: {led['bot_walled']} practitioner endpoints returned a "
                    "bot wall. Trench quota cannot be certified complete from these sources."
                )
            for it in trench_items:
                h = urllib.parse.urlparse(it.url).hostname or it.platform.lower()
                candidates.append(CandidateLead(
                    title=f"{it.platform} ({it.channel}): {it.title}",
                    url=it.url, host=h.lower().removeprefix("www."),
                    source_type="practitioner_trench",
                    inline_text=it.render_snapshot_block(),
                    score=35.0 if it.alpha_flag else 20.0,
                    pub_year=_year_of(it.date) if it.date_known else 0,
                ))
        except Exception as exc:
            _report("trench_miner", False, f"{type(exc).__name__}: {exc}")

        # 6. v12.0: actively try to DETHROME the identified leader by mining
        #    the adversarial vectors across practitioner trenches. These are
        #    disconfirmation sources, not confirmatory ones.
        if leader_claims:
            try:
                from dr_engine.tools.trench_miner import mine_dethroning_vectors
                d_items = mine_dethroning_vectors(dethrone_vectors, timeout=6.0, max_items=4)
                _report("dethroning_miner", bool(d_items), f"{len(d_items)} upset leads")
                for it in d_items:
                    h = urllib.parse.urlparse(it.url).hostname or "trench.local"
                    candidates.append(CandidateLead(
                        title=f"O_dethrone [{it.lang.upper()}]: {it.title}",
                        url=it.url, host=h.lower().removeprefix("www."),
                        source_type="adversarial_dethroning",
                        inline_text=it.render_snapshot_block(),
                        score=40.0 if it.alpha_flag else 22.0,
                        pub_year=_year_of(it.date) if it.date_known else 0,
                    ))
                if not d_items:
                    warnings.append(
                        "DETHRONING BLACKOUT: no practitioner upset leads were "
                        "recovered. The superlative claim remains UNVERIFIED "
                        "(fail-closed); do not certify it as current."
                    )
            except Exception as exc:
                _report("dethroning_miner", False, f"{type(exc).__name__}: {exc}")

    if not candidates:
        warnings.append(
            "DISCOVERY BLACKOUT: all collectors returned zero leads. This spec is "
            "NOT research-ready; check collector_provenance and network access."
        )

    selected, expected_neff = optimize_lead_diversity(candidates, max_per_host=2, max_total=max_urls)
    inline_sources: dict[str, str] = {}
    remote_urls: list[str] = []
    for lead in selected:
        if lead.inline_text and len(lead.inline_text) >= 120:
            inline_sources[lead.url] = lead.inline_text
        else:
            remote_urls.append(lead.url)

    return {
        "study_title": prompt.strip(),
        "generated_at": dt.date.today().isoformat(),
        "domain": skeleton["domain"],
        "entities": skeleton["entities"],
        "expected_pre_ingest_neff": expected_neff,
        "community_kind": "all",
        "community_min_score": 2,
        "sub_questions": skeleton["sub_questions"],
        "kill_hypotheses": skeleton["kill_hypotheses"],
        "adversarial_search_vectors": skeleton["search_vectors"],
        # v12.0: this marker makes the EAD (R18) and dethroning (B11) gates
        # MANDATORY at verification time for every study generated from v12.
        "protocol_version": PROTOCOL_VERSION,
        "dethroning": dethroning,
        "ead_scaffold": render_ead_template(),
        "ead_required_sections": [
            "Superficial Consensus", "Trench Ground-Truth (The Alpha)", "Delta Impact",
        ],
        "inline_sources": inline_sources,
        "urls": remote_urls,
        # v10.0 provenance (consumed by lean_engine ingest/verify).
        "unverified_inline_sources": unverified_inline,
        "benchmark_provenance": benchmark_provenance,
        "collector_provenance": {
            "ok": list(LAST_COLLECTION_REPORT["ok"]),
            "failed": list(LAST_COLLECTION_REPORT["failed"]),
        },
        "warnings": warnings,
    }


def cmd_generate(args: argparse.Namespace) -> int:
    spec = generate_autonomous_study_spec(
        args.prompt,
        offline_only=args.offline,
        max_urls=args.max_urls,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prov = spec.get("collector_provenance", {})
    print(
        f"[AUTO-SPEC OK] Domain={spec['domain']} | Entities={spec['entities']} | "
        f"Inline={len(spec['inline_sources'])} | RemoteURLs={len(spec['urls'])} | "
        f"Pre-Ingest N_eff={spec['expected_pre_ingest_neff']} -> {out_path}"
    )
    print(
        f"[COLLECTORS] ok={len(prov.get('ok', []))} failed={len(prov.get('failed', []))} "
        f"| warnings={len(spec.get('warnings', []))}"
    )
    for w in spec.get("warnings", []):
        print(f"  WARN  {w}")
    for f in prov.get("failed", []):
        print(f"  [COLLECTOR FAIL] {f['collector']}: {f['detail'][:120]}")
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    t0 = time.perf_counter()

    # 1. Verify deterministic domain classification across all 5 epistemic domains
    assert classify_prompt_domain("Evaluate 0DTE SPX dealer gamma exposure and M15 slippage") == "quant"
    assert classify_prompt_domain("B2B Shopify inventory webhook SaaS churn and API quota") == "saas"
    assert classify_prompt_domain("GLP-1 receptor agonist Phase 3 surrogate endpoint toxicity") == "biotech"
    assert classify_prompt_domain("Bulgarian ЗДДФЛ and IRC Section 1256 tax safe harbor audit") == "legal"
    assert classify_prompt_domain("Solid-state battery Wh/kg Carnot thermodynamic BOM yield") == "deeptech"
    # v10.0: the AI frontier is a real domain and unmatched prompts are honest.
    assert classify_prompt_domain("Best LLM on the Artificial Analysis leaderboard for SOTA coding") == "ai"
    assert classify_prompt_domain("A question with no domain vocabulary at all") == "general"

    # 2. Verify OpenAlex inverted index abstract reconstruction
    inv_idx = {
        "Across": [0],
        "500": [1],
        "sessions,": [2],
        "0DTE": [3],
        "gamma": [4],
        "imbalance": [5],
        "yields": [6],
        "8.4": [7],
        "bps.": [8],
    }
    abstract = reconstruct_openalex_abstract(inv_idx)
    assert abstract == "Across 500 sessions, 0DTE gamma imbalance yields 8.4 bps."

    # 3. Verify Adversarial Skeptic Swarm & Inverse-HHI Optimizer
    spec = generate_autonomous_study_spec(
        "Evaluate US100 M15 0DTE gamma imbalance momentum after spread and slippage friction",
        offline_only=True,
    )
    assert spec["domain"] == "quant"
    assert len(spec["sub_questions"]) == 4
    assert len(spec["kill_hypotheses"]) == 3
    assert "3.0%" in spec["kill_hypotheses"]["K1"]["hypothesis"]

    synthetic_leads = [
        CandidateLead("Paper 1", "https://openalex.org/W1", "openalex.org", "academic", score=50),
        CandidateLead("Paper 2", "https://openalex.org/W2", "openalex.org", "academic", score=45),
        CandidateLead("Paper 3", "https://openalex.org/W3", "openalex.org", "academic", score=40),  # Capped!
        CandidateLead("Preprint 1", "https://arxiv.org/abs/2501.01", "arxiv.org", "preprint", score=35),
        CandidateLead("Reddit 1", "https://reddit.com/r/algotrading/1", "reddit.com", "community_pain", score=30),
        CandidateLead("HN 1", "https://news.ycombinator.com/item?id=1", "news.ycombinator.com", "community_tech", score=28),
        CandidateLead("Quant SE 1", "https://quant.stackexchange.com/q/1", "quant.stackexchange.com", "community_tech", score=26),
    ]
    kept, neff = optimize_lead_diversity(synthetic_leads, max_per_host=2, max_total=6)
    assert len(kept) == 6
    assert sum(1 for c in kept if c.host == "openalex.org") == 2
    assert neff >= 4.5, f"Expected diversified N_eff >= 4.5, got {neff}"

    # 4. v10.0: offline spec still carries provenance fields and never fabricates years.
    assert spec["domain"] == "quant"
    assert "collector_provenance" in spec and "warnings" in spec
    assert all(c.pub_year >= 0 for c in synthetic_leads)
    assert _year_of("unknown") == 0 and _year_of(2026) == 2026
    assert build_adversarial_spec_skeleton("Which LLM is SOTA")["domain"] == "ai"
    assert len(build_adversarial_spec_skeleton("Which LLM is SOTA")["kill_hypotheses"]) == 3

    # 5. v12.0: every spec is v12, and a superlative prompt spawns the
    #    Active Dethroning Protocol with computed 30/90-day windows.
    assert spec["protocol_version"] == "12.0"
    assert "ead_scaffold" in spec and len(spec["ead_required_sections"]) == 3
    record_spec = generate_autonomous_study_spec(
        "Who holds the deadlift world record of 510 kg and is still #1?",
        offline_only=True,
    )
    dth = record_spec["dethroning"]
    assert dth["protocol_active"] and dth["vector_count"] >= 16
    assert dth["leader_value"] == 510.0 and dth["leader_unit"] == "kg"
    assert dth["leader"] == "the current leader", dth["leader"]
    assert infer_leader("Hafþór Björnsson holds the deadlift world record of 510 kg") == "Hafþór Björnsson"
    assert infer_leader("Evaluate US100 M15 0DTE gamma exposure") == "the current leader"
    assert {v["window_days"] for v in dth["vectors"]} == {30, 90}
    assert any("surpassed by" in v["query"] for v in dth["vectors"])
    assert all(v["until"] == dt.date.today().isoformat() for v in dth["vectors"])
    assert all(
        (dt.date.today() - dt.date.fromisoformat(v["since"])).days == v["window_days"]
        for v in dth["vectors"]
    ), "recency window must be computed, not hardcoded"
    assert any("SUPERLATIVE CLAIM DETECTED" in w for w in record_spec["warnings"])
    assert "dethrone_30d_en" in record_spec["adversarial_search_vectors"]

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 50.0, f"Selftest exceeded 50ms budget: {elapsed_ms:.2f}ms"
    print(f"[SELFTEST PASS] auto_spec v12.0 (Turn 0 + O_dethrone + EAD + provenance) verified in {elapsed_ms:.2f} ms (< 50.0 ms).")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate", help="Generate study_spec.json from a 1-sentence prompt")
    p_gen.add_argument("--prompt", required=True, help="1-sentence research objective")
    p_gen.add_argument("--out", required=True, help="Output path for study_spec.json")
    p_gen.add_argument("--max-urls", type=int, default=10)
    p_gen.add_argument("--offline", action="store_true", help="Build spec skeleton without network calls")
    p_gen.set_defaults(fn=cmd_generate)

    p_st = sub.add_parser("selftest", help="Run zero-mock verification (< 50 ms)")
    p_st.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
