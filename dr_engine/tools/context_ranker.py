#!/usr/bin/env python3
"""Deep Research Engine v12.0 — Polyglot Context Ranker + Insider BM25 Prior.

v12.0 Frontier 2: an obscure three-sentence insider comment in Korean,
Russian, German, Japanese, Spanish or Chinese is the "golden nugget", but a
plain BM25 score dilutes it among thousands of words of generic press-release
text. Passages carrying an :mod:`insider_anomaly` witness marker now receive a
fixed **3.0x BM25 prior boost**, are admitted to the candidate pool even with
zero lexical overlap (bounded prior-only floor), and get one reserved slot per
query so they reach ``context_pack.md`` rather than being truncated away. The
boost is recorded per passage (``bm25_base_score``, ``insider_prior``,
``insider_markers``) so the audit trail is reproducible.

v10.0 base:

Replaces the v9.0 ``rank_bm25_passages`` implementation, which had four
measurable defects:

  1. ``[a-zа-я0-9]{3,}`` tokenisation made CJK / Hangul / accented-Latin
     passages invisible to BM25 (6 of the 8 mined languages were discarded).
  2. ``p[:800]`` hard-truncated every long paragraph. A fee table or drawdown
     rule at character 900 was thrown away permanently, while ``len`` was
     computed on the *untruncated* text -- inconsistent length normalisation.
  3. No deduplication: the same passage could be emitted once per SQ/K, and
     syndicated text reposted across hosts counted as independent evidence.
  4. No diversity cap and no character budget: 5 passages x N queries could
     all come from one source and overflow the synthesis context window.

v10.0 uses overlapping windows (no information loss), script-aware tokens,
a bounded number-density prior, per-source diversity caps, shingle-Jaccard
syndication suppression, cross-query deduplication and a hard char budget.

Pure Python 3.10+ standard library. Windows cp1252-safe.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Allow both `python dr_engine/tools/context_ranker.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.insider_anomaly import (  # noqa: E402
    INSIDER_PRIOR_BOOST, scan_insider_markers,
)
from dr_engine.tools.polyglot_text import number_density, shingles, tokenize  # noqa: E402

__all__ = [
    "Passage", "build_passages", "rank_passages", "SPEC_STOPWORDS",
    "INSIDER_PRIOR_BOOST", "INSIDER_FLOOR_SCORE",
]

# A zero-BM25 insider passage is still a lead. The floor is deliberately tiny
# relative to a real lexical match; the reserved slot is what guarantees it is
# surfaced, not an inflated score.
INSIDER_FLOOR_SCORE = 0.05

# Spec-language boilerplate from `auto_spec.py` sub-questions. These are not
# evidence terms: ranking on them surfaces the methodology section, not facts.
SPEC_STOPWORDS = frozenset({
    "the", "and", "for", "that", "with", "from", "this", "are", "was", "were", "have",
    "has", "not", "but", "what", "all", "when", "can", "more", "than", "into", "only",
    "other", "such", "their", "which", "would", "about", "there", "how", "does", "why",
    "primary", "mechanism", "structural", "physics", "domain", "empirical", "magnitude",
    "survival", "heterogeneity", "across", "regimes", "friction", "unit", "economics",
    "breakeven", "execution", "operational", "cost", "costs", "structure", "adversarial",
    "postmortems", "practitioner", "failure", "failures", "modes", "regulatory",
    "counterparty", "constraints", "sample", "out", "evaluate", "analysis", "study",
    "impact", "effect", "using", "based", "between", "under", "over", "targeting",
    "target", "targets", "synthesize", "investigate", "assess", "determine",
    # Polyglot function words that would otherwise dominate non-English queries.
    "или", "при", "като", "това", "която", "които", "след", "през", "към", "със", "за", "на", "и", "в",
    "в", "на", "и", "с", "по", "от", "для", "это", "или", "как", "что",
    "der", "die", "das", "und", "für", "mit", "von", "im", "ein", "eine",
    "les", "des", "une", "avec", "pour", "dans", "est", "sur", "le", "la",
    "los", "las", "una", "con", "para", "por", "del", "en", "el", "que",
})


@dataclass
class Passage:
    """One bounded, exactly-located window of an immutable source snapshot."""

    sid: str
    pid: str
    text: str
    char_start: int
    tf: dict[str, int]
    length: int
    density: float
    shingle_set: set[tuple[str, ...]] = field(default_factory=set)
    # v12.0 Insider Anomaly Scorer diagnostics (defaults keep the v10 shape).
    insider_prior: float = 1.0
    insider_markers: list[dict[str, str]] = field(default_factory=list)
    insider_languages: list[str] = field(default_factory=list)
    insider_entropy: float = 0.0

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.text.strip().encode("utf-8")).hexdigest()[:16]

    @property
    def is_insider(self) -> bool:
        return self.insider_prior >= INSIDER_PRIOR_BOOST


def _window_spans(text: str, window_chars: int, overlap: int) -> list[tuple[int, str]]:
    """Split one paragraph into overlapping windows; no characters are lost."""
    if len(text) <= window_chars:
        return [(0, text)]
    step = max(1, window_chars - overlap)
    spans: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + window_chars]
        if chunk.strip():
            spans.append((start, chunk))
        if start + window_chars >= len(text):
            break
        start += step
    return spans


def build_passages(
    sources: dict[str, str],
    window_chars: int = 900,
    overlap: int = 180,
    min_chars: int = 60,
) -> list[Passage]:
    """Create BM25-indexable passage windows from every source snapshot.

    Unlike v9.0, a 5,000-character paragraph produces ~7 overlapping windows
    rather than one truncated 800-character prefix.
    """
    passages: list[Passage] = []
    for sid, text in sorted(sources.items()):
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", str(text)) if p.strip()]
        for p_idx, para in enumerate(paragraphs, 1):
            if len(para) < min_chars:
                continue
            windows = _window_spans(para, window_chars, overlap)
            for w_idx, (start, chunk) in enumerate(windows, 1):
                tokens = [t for t in tokenize(chunk) if t not in SPEC_STOPWORDS]
                if not tokens:
                    continue
                pid = f"{sid}@p{p_idx}" if len(windows) == 1 else f"{sid}@p{p_idx}w{w_idx}"
                anomaly = scan_insider_markers(chunk)
                passages.append(
                    Passage(
                        sid=sid, pid=pid, text=chunk, char_start=start,
                        tf=dict(Counter(tokens)), length=len(tokens),
                        density=number_density(chunk),
                        shingle_set=shingles(chunk[:1200], k=3, stopwords=SPEC_STOPWORDS),
                        insider_prior=float(anomaly["prior"]),
                        insider_markers=list(anomaly["hits"]),
                        insider_languages=list(anomaly["languages"]),
                        insider_entropy=float(anomaly["entropy"]),
                    )
                )
    return passages


def _jaccard(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def rank_passages(
    sources: dict[str, str],
    queries: dict[str, str],
    top_k_per_query: int = 5,
    max_chars: int = 48_000,
    max_per_source: int = 3,
    number_density_boost: float = 0.35,
    syndication_threshold: float = 0.85,
    insider_prior_boost: float = INSIDER_PRIOR_BOOST,
) -> list[dict[str, Any]]:
    """Rank evidence passages globally with BM25 + polyglot + diversity controls.

    Returns the v9.0-compatible shape (``query_id``, ``locator``, ``sid``,
    ``score``, ``quote_span``) plus v10.0 provenance and v12.0 insider-prior
    diagnostics (``bm25_base_score``, ``insider_prior``, ``insider_markers``,
    ``insider_languages``, ``reserved_slot``).

    v12.0: a passage with a multilingual insider-witness marker gets a fixed
    3.0x prior on top of the number-density-adjusted BM25 score, is admitted
    even with zero query-term overlap (bounded floor), and one reserved slot
    per query guarantees it reaches the context pack.
    """
    passages = build_passages(sources)
    if not passages or not queries:
        return []

    df: dict[str, int] = {}
    for p in passages:
        for term in p.tf:
            df[term] = df.get(term, 0) + 1

    n_docs = len(passages)
    avgdl = sum(p.length for p in passages) / n_docs
    k1, b = 1.5, 0.75

    selected: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    chosen_shingles: list[set[tuple[str, ...]]] = []
    per_source: Counter[str] = Counter()
    chars_used = 0
    # Which queries a passage also matched (dedup would otherwise repeat text).
    extra_matches: dict[str, list[str]] = {}

    def emit(final_score: float, base_score: float, prior: float,
             p: Passage, qid: str, reserved: bool = False) -> bool:
        """Apply every v10 guard and append one result. Returns False on skip."""
        nonlocal chars_used
        fp = p.fingerprint
        if fp in seen_fingerprints:
            if qid not in extra_matches.get(fp, []):
                extra_matches.setdefault(fp, []).append(qid)
            return False
        if per_source[p.sid] >= max_per_source:
            return False
        if any(_jaccard(p.shingle_set, s) >= syndication_threshold for s in chosen_shingles):
            return False
        if chars_used + len(p.text) > max_chars and selected:
            return False
        seen_fingerprints.add(fp)
        chosen_shingles.append(p.shingle_set)
        per_source[p.sid] += 1
        chars_used += len(p.text)
        selected.append({
            "query_id": qid,
            "locator": p.pid,
            "sid": p.sid,
            "score": round(final_score, 2),
            "bm25_base_score": round(base_score, 4),
            "insider_prior": prior,
            "insider_markers": [h["marker"] for h in p.insider_markers],
            "insider_languages": list(p.insider_languages),
            "insider_entropy": p.insider_entropy,
            "reserved_slot": reserved,
            "quote_span": p.text,
            "number_density": round(p.density, 3),
            "char_start": p.char_start,
            "sha256": p.fingerprint,
            "also_matches": extra_matches.get(fp, []),
        })
        return True

    for qid, qtext in queries.items():
        q_terms = list(dict.fromkeys(
            t for t in tokenize(str(qtext)) if t not in SPEC_STOPWORDS
        ))[:32]
        if not q_terms:
            continue

        # (final_score, base_score, prior, passage)
        scored: list[tuple[float, float, float, Passage]] = []
        for p in passages:
            bm25 = 0.0
            for qt in q_terms:
                f = p.tf.get(qt, 0)
                if not f:
                    continue
                idf = math.log(1.0 + (n_docs - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5))
                bm25 += idf * (f * (k1 + 1.0)) / (f + k1 * (1.0 - b + b * (p.length / avgdl)))
            prior = float(insider_prior_boost) if p.is_insider else 1.0
            if bm25 <= 0:
                if not p.is_insider:
                    continue
                # Prior-only candidate: no lexical overlap, but a genuine
                # insider disclosure must not be discarded by BM25's zero.
                bm25 = INSIDER_FLOOR_SCORE
            # Number-dense passages (tables, fee schedules, measured benchmarks)
            # carry disproportionate decision weight in due diligence.
            base = bm25 * (1.0 + number_density_boost * p.density)
            scored.append((base * prior, base, prior, p))

        scored.sort(key=lambda x: x[0], reverse=True)

        added = 0
        insider_added = False
        for final_score, base_score, prior, p in scored:
            if added >= top_k_per_query:
                break
            if emit(final_score, base_score, prior, p, qid):
                added += 1
                insider_added = insider_added or p.is_insider

        # Golden Nugget reserved slot: if a high-entropy insider passage exists
        # but BM25/diversity suppressed it, surface the best one anyway. This
        # is the mechanical guarantee behind "obscure comments bubble to the
        # top of the context pack".
        if not insider_added:
            for final_score, base_score, prior, p in scored:
                if not p.is_insider:
                    continue
                if emit(final_score, base_score, prior, p, qid, reserved=True):
                    break

    return selected


def _selftest() -> int:
    # Long paragraph: v9.0 truncated at 800 chars, discarding the tail.
    long_para = (
        "Introductory commentary on the microstructure of the instrument. " * 12
        + "\n\n"
        + "CRITICAL TABLE ROW: execution friction 3.0 bps and net alpha 5.4 bps in 2026."
    )
    zh_para = "生产环境实际测试滑点回测失效踩坑 实测滑点 3.2 bp 手续费 1.1 bp 合计 4.3 bp 净 alpha 为负" * 4
    sources = {"S001": long_para, "S002": zh_para}
    queries = {"SQ1": "execution friction net alpha bps", "SQ2": "生产环境 滑点 实测", "K1": "execution friction"}

    passages = build_passages(sources)
    assert len(passages) >= 3, f"expected overlapping windows, got {len(passages)}"
    assert any("CRITICAL TABLE ROW" in p.text for p in passages), "tail paragraph lost"

    ranked = rank_passages(sources, queries, top_k_per_query=3)
    assert ranked, "no passages ranked"
    # CJK query must retrieve the Chinese source (impossible under the v9.0 tokenizer).
    assert any(r["sid"] == "S002" for r in ranked), f"CJK source never retrieved: {[r['sid'] for r in ranked]}"
    # Cross-query dedup: no identical span emitted twice.
    locators = [r["locator"] for r in ranked]
    assert len(locators) == len(set(locators)), "duplicate passage emitted across queries"
    # Per-source diversity cap.
    from collections import Counter as _C
    counts = _C(r["sid"] for r in ranked)
    assert max(counts.values()) <= 3

    budgeted = rank_passages(sources, queries, top_k_per_query=3, max_chars=500)
    assert sum(len(r["quote_span"]) for r in budgeted) <= 500 + 900, "char budget ignored"

    # Syndication suppression: identical text on two hosts counts once.
    dup = rank_passages(
        {"S001": long_para * 3, "S002": long_para * 3},
        {"SQ1": "execution friction"},
        top_k_per_query=5,
    )
    assert len(dup) <= 1 or all(r["sid"] == "S001" for r in dup)

    # v12.0: the insider comment receives exactly 3.0x the BM25 base score.
    insider_sources = {
        "S010": (
            "I was there when the lift was judged; the real number was 511 kg, "
            "not 510 kg, at the Birmingham deadlift world record event."
        ),
        "S011": (
            "The federation published the official entry list and confirmed the "
            "510 kg deadlift world record for the 2026 season."
        ),
    }
    boosted = rank_passages(
        insider_sources, {"SQ1": "deadlift world record 510 kg federation"},
        top_k_per_query=2,
    )
    gold = [r for r in boosted if r["insider_prior"] == INSIDER_PRIOR_BOOST]
    assert gold, f"insider passage never surfaced: {boosted}"
    assert gold[0]["insider_markers"] and gold[0]["insider_languages"] == ["en"]
    assert abs(gold[0]["score"] - 3.0 * gold[0]["bm25_base_score"]) < 0.02, (
        gold[0]["score"], gold[0]["bm25_base_score"])
    plain = [r for r in boosted if r["insider_prior"] == 1.0]
    assert plain and abs(plain[0]["score"] - plain[0]["bm25_base_score"]) < 0.02

    # Zero lexical overlap: a Chinese-only insider disclosure must still reach
    # the context pack via the reserved slot (prior-only floor).
    zh_only = "内部消息：实际跑分实测翻车，世界纪录被打破，现场看到 511 公斤。" * 3
    zero = rank_passages(
        {"S020": zh_only}, {"SQ9": "deadlift world record 510 kg federation"},
        top_k_per_query=2,
    )
    assert any(r["insider_prior"] == 3.0 for r in zero), zero
    assert any("内部消息" in r["insider_markers"] for r in zero)
    # With only one slot, a high-BM25 press release would crowd the nugget
    # out. The reserved slot must still surface it.
    mixed = {"S020": zh_only, "S021": insider_sources["S011"]}
    forced = rank_passages(
        mixed, {"SQ9": "deadlift world record 510 kg federation"},
        top_k_per_query=1,
    )
    assert any(r["reserved_slot"] and r["insider_prior"] == 3.0 for r in forced), forced

    # Generic text is never boosted (no false-positive prior inflation).
    assert all(r["insider_prior"] == 1.0 for r in ranked)

    print("[SELFTEST PASS] context_ranker v12.0 (windows/polyglot/dedup/diversity/budget/"
          "insider prior x3.0/reserved slot) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
