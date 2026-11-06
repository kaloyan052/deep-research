#!/usr/bin/env python3
"""Deep Research Engine v12.0 — Insider Anomaly Scorer (Golden Nugget Miner).

Frontier 2. The single decisive fact in a due-diligence investigation is almost
never in a press release or a Wikipedia lead. It is a three-sentence comment by
an engineer, a lifter, a competitor or an event attendee, written in whatever
language the practitioner actually uses. Generic search stops at high-SEO
pages; this module finds the disclosure that contradicts them.

Design constraints (mechanical, not heuristic-by-LLM):

  * Markers are **exact phrases**, declared per language, not vague keywords.
    A corpus-wide "in production" is not an insider witness; "in production we
    saw" is. This keeps false positives out of the BM25 prior.
  * Matching is NFKC-normalised, Latin-diacritic-folded, case-insensitive and
    whitespace-flexible (via ``polyglot_text.fold_text``), so ``nuevo récord``
    matches ``nuevo record`` and full-width CJK/ASCII forms match too.
  * Every hit is returned with its language and marker. ``context_ranker``
    applies a single, fixed **3.0x BM25 prior** and records it in the returned
    passage diagnostics. No tunable weights, no subjective scoring.
  * A high-entropy diagnostic (Shannon entropy over tokens) is reported but
    does NOT gate the boost: a short three-sentence comment is exactly the
    golden nugget we must not discard.

Pure Python 3.10+ stdlib. Zero paid API keys. Windows cp1252-safe.
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Allow both `python dr_engine/tools/insider_anomaly.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.polyglot_text import fold_text, tokenize  # noqa: E402

__all__ = [
    "INSIDER_PRIOR_BOOST",
    "INSIDER_MARKERS",
    "SUPPORTED_LANGUAGES",
    "normalise_for_match",
    "shannon_entropy",
    "scan_insider_markers",
    "insider_prior",
    "render_anomaly_tag",
]

# The mandated, mechanical boost. Exposed as a constant so tests and the
# context ranker cannot drift into a "soft" 1.2x compromise.
INSIDER_PRIOR_BOOST = 3.0

# 8 languages covered by the polyglot trench (plus Bulgarian, which is the
# workspace's native research language, as a defensive extra).
INSIDER_MARKERS: dict[str, tuple[str, ...]] = {
    "en": (
        "i was there", "in production we saw", "the real number was",
        "actually pulled", "quietly deprecated", "leaked benchmark",
        "we measured it ourselves", "unannounced breaking change",
    ),
    "ru": (
        "на самом деле", "вчера на помосте", "слили в закрытый чат",
        "в проде отвалилось", "реальный результат был", "тихо убрали",
    ),
    "zh": (
        "实测翻车", "内部消息", "实际跑分", "被打破", "现场看到",
        "悄悄下线", "内测数据",
    ),
    "es": (
        "en realidad fue", "superó a", "en vivo vimos", "nuevo récord",
        "lo deprecaron sin avisar", "filtraron el benchmark",
    ),
    "de": (
        "tatsächlich geschlagen", "im Produktivbetrieb gescheitert",
        "neuer Rekord", "war selbst vor Ort", "stillschweigend entfernt",
        "echte Messwerte",
    ),
    "ko": (
        "실제로는", "신기록 달성", "어제 대회에서", "실서버 장애",
        "조용히 삭제됐다", "내부 벤치마크 유출",
    ),
    "ja": (
        "実際の測定値", "新記録達成", "本番で発覚", "現地で見た",
        "密かに廃止", "内部ベンチマーク流出",
    ),
    "fr": (
        "en réalité c'était", "a battu le record", "sur place nous avons vu",
        "nouveau record", "déprécié sans annonce", "benchmark divulgué",
    ),
    "bg": (
        "наистина беше", "вчера на състезанието", "тихо премахнаха",
        "реалният резултат беше",
    ),
}

SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "en", "ru", "zh", "es", "de", "ko", "ja", "fr",
)

_WS_RE = re.compile(r"\s+")


def normalise_for_match(text: Any) -> str:
    """Canonical, script-safe lowercase form used for marker matching.

    Malformed inputs (None, bytes, numbers, dicts) are coerced safely rather
    than raising: a scraper must never die because an API returned a null body.
    """
    if text is None:
        return ""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", errors="replace")
        except (AttributeError, UnicodeError):
            return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""
    folded = fold_text(text).lower()
    return _WS_RE.sub(" ", folded).strip()


# Precompile one whitespace-flexible regex per marker, once, at import time.
_COMPILED_MARKERS: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (lang, marker, re.compile(r"\s+".join(re.escape(w) for w in normalise_for_match(marker).split())))
    for lang, markers in INSIDER_MARKERS.items()
    for marker in markers
)


def shannon_entropy(text: Any) -> float:
    """Shannon entropy (bits) of the token distribution of ``text``.

    Diagnostic only. It lets the audit trail show that a boosted comment was a
    high-information disclosure, not a one-word spam hit.
    """
    tokens = tokenize(normalise_for_match(text))
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    n = len(tokens)
    return round(-sum((c / n) * math.log2(c / n) for c in counts.values()), 3)


def scan_insider_markers(text: Any) -> dict[str, Any]:
    """Return the complete, deterministic anomaly record for one passage.

    Shape::

        {"prior": 3.0 | 1.0, "boost": 3.0 | 1.0, "is_insider": bool,
         "hits": [{"lang", "marker"}], "languages": [...],
         "distinct_markers": int, "entropy": float, "high_entropy": bool}
    """
    haystack = normalise_for_match(text)
    hits: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if haystack:
        for lang, marker, rx in _COMPILED_MARKERS:
            if rx.search(haystack):
                key = (lang, marker)
                if key not in seen:
                    seen.add(key)
                    hits.append({"lang": lang, "marker": marker})
    is_insider = bool(hits)
    entropy = shannon_entropy(haystack) if is_insider else 0.0
    prior = INSIDER_PRIOR_BOOST if is_insider else 1.0
    return {
        "prior": prior,
        "boost": prior,
        "is_insider": is_insider,
        "hits": hits,
        "languages": sorted({h["lang"] for h in hits}),
        "distinct_markers": len(hits),
        "entropy": entropy,
        "high_entropy": entropy >= 2.0 and len(tokenize(haystack)) >= 8,
    }


def insider_prior(text: Any) -> float:
    """Return the BM25 prior multiplier for ``text`` (3.0 on any marker hit)."""
    return INSIDER_PRIOR_BOOST if scan_insider_markers(text)["is_insider"] else 1.0


def render_anomaly_tag(text: Any) -> str:
    """Compact provenance tag for trench snapshots (never raises)."""
    rec = scan_insider_markers(text)
    if not rec["is_insider"]:
        return ""
    langs = ",".join(rec["languages"])
    return (
        f"[INSIDER ANOMALY langs={langs} prior=x{rec['prior']:.1f} "
        f"markers={rec['distinct_markers']} entropy={rec['entropy']}]"
    )


def _selftest() -> int:
    samples = {
        "en": "I was there when the lift was judged; the real number was 511 kg.",
        "ru": "На самом деле вчера на помосте слили в закрытый чат новый результат.",
        "zh": "内部消息：实际跑分实测翻车，纪录被打破。",
        "es": "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg.",
        "de": "Tatsächlich geschlagen: neuer Rekord, im Produktivbetrieb gescheitert.",
        "ko": "실제로는 어제 대회에서 신기록 달성, 실서버 장애도 있었다.",
        "ja": "実際の測定値では新記録達成、本番で発覚した不具合。",
        "fr": "Sur place nous avons vu un nouveau record: en réalité c'était 511 kg.",
    }
    for lang, sample in samples.items():
        rec = scan_insider_markers(sample)
        assert rec["is_insider"], f"marker missed for {lang}"
        assert rec["prior"] == 3.0, f"prior drift for {lang}"
        assert lang in rec["languages"], f"language misattributed for {lang}: {rec['languages']}"
    assert not scan_insider_markers("The vendor announced a new benchmark result.")["is_insider"]
    assert scan_insider_markers(None)["prior"] == 1.0
    assert scan_insider_markers(12345)["prior"] == 1.0
    assert scan_insider_markers(b"I was there")["is_insider"]
    # Whitespace / diacritic / full-width robustness.
    assert scan_insider_markers("NUEVO   RECORD en vivo vimos")["is_insider"]
    assert scan_insider_markers("I   was\tthere")["is_insider"]
    print(f"[SELFTEST PASS] insider_anomaly v12.0 ({len(SUPPORTED_LANGUAGES)} languages, "
          f"prior x{INSIDER_PRIOR_BOOST:.1f}) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
