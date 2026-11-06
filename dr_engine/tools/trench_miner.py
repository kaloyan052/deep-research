#!/usr/bin/env python3
"""Deep Research Engine v12.0 — Polyglot Deep Trench & Golden Nugget Miner.

v12.0 Frontier 2 additions:

  * **Insider Anomaly Scorer.** Every mined practitioner comment is scanned for
    "insider witness" phrases in 8 languages (EN/RU/ZH/ES/DE/KO/JA/FR, plus
    BG). A hit sets ``insider_prior = 3.0`` and is carried into the snapshot
    block so ``context_ranker`` can apply the mandated 3.0x BM25 prior boost.
    Obscure three-sentence disclosures are no longer diluted by generic prose.
  * **Active Dethroning mining.** :func:`mine_dethroning_vectors` executes
    recency-anchored adversarial vectors designed to break an identified
    leader; :func:`mine_all_trenches` spawns them automatically whenever the
    prompt contains a superlative claim.

v10.0 base (unchanged behaviour):

Hunts high-alpha, ground-truth practitioner evidence across 8 languages
(EN, RU, ZH, JA, KO, DE, FR, ES) + BG:

  * Hacker News Algolia comments (production postmortems, failure reports)
  * StackExchange / Quant.SE (LaTeX-preserving technical breakdowns)
  * GitHub Issues & PR discussions (real bugs, off-by-one, latency spikes)
  * Habr RSS (RU engineering), Qiita API v2 (JA), Heise Atom (DE)
  * Generic RSS/Atom feeds (Lobsters, dev.to, Reddit search)

v10.0 hardening (audit findings A4):

  * **No silent failures.** v9.0 used ``except Exception: pass`` in all seven
    collectors, so a total network blackout was indistinguishable from "no
    evidence exists". Every attempt now writes a :class:`CollectorOutcome`
    into a thread-safe :class:`CollectorLedger` (status, via, bot_wall, error,
    elapsed time), exposed to the CLI and to ``auto_spec``.
  * **Resilient transport.** All reads go through ``http_resilience``: charset
    detection (cp1251 / Shift_JIS / GB18030), gzip, bounded retry with
    Retry-After, bot-wall detection, byte caps, opt-in reader fallback.
  * **Honest dates.** v9.0 fabricated ``"2026-01-01"`` when a date was missing,
    which silently passed the B9 recency gate. Missing dates are now
    ``"unknown"`` with ``date_known=False`` and are excluded from recency.
  * **Comparable ranking.** v9.0 sorted raw engagement scores across platforms
    (HN points vs GitHub comment counts vs hardcoded 10/15). v10.0 normalises
    engagement to a 0-100 platform-relative :attr:`signal_score`.
  * **Syndication dedup.** Identical bodies at different URLs are collapsed by
    SHA-256, so cross-posts cannot inflate the independence count (N_eff).
  * **English prompts work.** v9.0's polyglot dictionary was reachable only
    through a Bulgarian concept map; an English prompt produced no translation
    at all. English concept triggers are now first-class.
  * **GitHub rate-limit discipline.** Six concurrent unauthenticated GitHub
    search calls reliably return 403/429; a module-level gate serialises them.

Pure Python 3.10+ stdlib. Zero paid API keys. Windows cp1252-safe.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
import re
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Allow both `python dr_engine/tools/trench_miner.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.dethrone import (  # noqa: E402
    DethroningVector, build_dethroning_vectors, detect_superlative_claims,
    extract_leader_value,
)
from dr_engine.tools.http_resilience import (  # noqa: E402
    benchmark_fallback_coverage, fetch_json, fetch_with_fallbacks, fetch_xml,
    resilient_fetch,
)
from dr_engine.tools.insider_anomaly import (  # noqa: E402
    INSIDER_PRIOR_BOOST, render_anomaly_tag, scan_insider_markers,
)
from dr_engine.tools.polyglot_text import tokenize  # noqa: E402

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (DR-PolyglotTrench/10.0)"
)

# High-signal disconfirmation triggers indicating ground-truth operational reality.
TRENCH_ALPHA_PATTERNS = re.compile(
    r"\b("
    r"in\s+production|our\s+fund|we\s+tested|actually\s+failed|doesn't\s+work|does\s+not\s+work|"
    r"off[- ]by[- ]one|bug\s+in|latency\s+spike|undisclosed\s+fee|capacity\s+decay|slippage\s+ate|"
    r"hallucinated|rate\s+limit|hidden\s+cost|postmortem|reproducib|flaw\s+in|breakdown\s+at|"
    r"в\s+проде|на\s+практике|слив\s+депо|проскальзывание|сбой|баг|убыток|ликвидация|"
    r"生产环境|实际测试|滑点|实盘|回测失效|财务造假|踩坑|幻觉|爆仓|实测|"
    r"本番環境|実運用|スリッページ|障害|バグ|ハルシネーション|精度低下|"
    r"실서버|운영환경|실전매매|슬리피지|버그|장애|환각|오류발생|체결오차|"
    r"in\s+Produktion|Produktivbetrieb|Ausfall|Fehler|Slippage|Latenz|Schwachstelle|Totalverlust|"
    r"en\s+production|défaillance|latence|écart\s+d'exécution|bogue|plantage|perte|"
    r"en\s+producción|fallo|deslizamiento|latencia|error\s+grave|pérdida|liquidación"
    r")\b",
    re.I,
)

# Polyglot expansion dictionary across 8 practitioner languages.
POLYGLOT_DICTIONARY: dict[str, dict[str, str]] = {
    "en": {
        "model": "model LLM",
        "best": "best top leading benchmark",
        "finance": "finance quantitative trading accounting",
        "stock": "stocks equities",
        "trading": "trading execution",
        "slippage": "slippage spread friction",
        "bug": "bug issue defect failure",
        "accounting": "accounting balance sheet 10-K audit",
    },
    "ru": {
        "model": "нейросеть LLM модель",
        "best": "лучшая бенчмарк сравнение",
        "finance": "финансы алготрейдинг трейдинг",
        "stock": "акции биржа",
        "trading": "трейдинг исполнение",
        "slippage": "проскальзывание спред комиссии",
        "bug": "ошибка баг сбой проблема",
        "accounting": "бухгалтерия отчетность 10-K баланс",
    },
    "zh": {
        "model": "大模型 LLM",
        "best": "最佳 评测 榜单 排名",
        "finance": "金融 量化 交易 财报",
        "stock": "股票 证券 投资",
        "trading": "量化交易 策略 执行",
        "slippage": "滑点 费率 摩擦成本",
        "bug": "缺陷 漏洞 踩坑 错误",
        "accounting": "财务报表 审计 财报",
    },
    "ja": {
        "model": "大規模言語モデル LLM",
        "best": "比較 ベンチマーク 性能",
        "finance": "金融 クオンツ 会計",
        "stock": "株式 証券",
        "trading": "アルゴリズム取引 執行",
        "slippage": "スリッページ 手数料",
        "bug": "バグ 不具合 課題",
        "accounting": "財務諸表 決算書 監査",
    },
    "ko": {
        "model": "거대언어모델 LLM 인공지능",
        "best": "최고 벤치마크 성능 비교",
        "finance": "금융 퀀트 트레이딩 회계",
        "stock": "주식 증권 시장",
        "trading": "알고리즘 트레이딩 매매",
        "slippage": "슬리피지 수수료 체결오차",
        "bug": "버그 오류 장애 결함",
        "accounting": "재무제표 결산 감사 회계",
    },
    "de": {
        "model": "Sprachmodell LLM KI",
        "best": "beste Benchmark Vergleich Rangliste",
        "finance": "Finanzen quantitativ Trading Buchhaltung",
        "stock": "Aktien Börse Wertpapiere",
        "trading": "Handel Orderausführung Trading",
        "slippage": "Slippage Spreads Transaktionskosten",
        "bug": "Fehler Bug Ausfall Latenz",
        "accounting": "Buchhaltung Bilanz Jahresabschluss Prüfung",
    },
    "fr": {
        "model": "modèle LLM intelligence artificielle",
        "best": "meilleur benchmark comparatif classement",
        "finance": "finance quantitative trading comptabilité",
        "stock": "actions bourse marchés",
        "trading": "trading exécution passage ordres",
        "slippage": "glissement slippage frais spread",
        "bug": "bogue défaillance erreur latence",
        "accounting": "comptabilité bilan audit états financiers",
    },
    "es": {
        "model": "modelo LLM inteligencia artificial",
        "best": "mejor benchmark comparativa ranking",
        "finance": "finanzas trading cuantitativo contabilidad",
        "stock": "acciones bolsa renta variable",
        "trading": "trading ejecución de órdenes",
        "slippage": "deslizamiento slippage comisiones spread",
        "bug": "error fallo bug latencia problema",
        "accounting": "contabilidad balance auditoría estados financieros",
    },
}

# Bulgarian term mapping to cross-lingual concepts.
BG_CONCEPT_MAP = {
    "най-добър": "best", "най-добрия": "best", "най-добрият": "best", "най-добрите": "best",
    "модел": "model", "модели": "model",
    "финанси": "finance", "счетоводство": "accounting",
    "акции": "stock", "търговия": "trading",
    "слипидж": "slippage", "триене": "slippage",
    "бъг": "bug", "грешка": "bug", "данъци": "finance",
}

# v10.0: English prompts previously matched ZERO concepts, so the entire
# polyglot dictionary was dead code for English input. These triggers map
# common English research vocabulary to the same canonical concepts.
EN_CONCEPT_MAP = {
    "model": "model", "models": "model", "llm": "model", "llms": "model",
    "best": "best", "sota": "best", "leaderboard": "best", "benchmark": "best",
    "finance": "finance", "financial": "finance", "quant": "finance", "trading": "trading",
    "stock": "stock", "stocks": "stock", "equities": "stock",
    "slippage": "slippage", "spread": "slippage", "friction": "slippage",
    "bug": "bug", "bugs": "bug", "crash": "bug", "latency": "bug", "outage": "bug",
    "failure": "bug", "accounting": "accounting", "audit": "accounting",
}

# Additional keyless RSS/Atom trenches (no API keys, no scraping of HTML).
RSS_TRENCH_FEEDS: tuple[tuple[str, str, str], ...] = (
    ("Lobsters", "en", "https://lobste.rs/t/ai.rss"),
    ("dev.to", "en", "https://dev.to/feed/tag/llm"),
    ("RedditRSS", "en", "https://www.reddit.com/search.rss?q={query}&sort=new&t=month"),
)

# Platform-relative engagement scales (used to make scores comparable).
_PLATFORM_SCORE_SCALE = {
    "HackerNews": 60.0, "StackExchange": 25.0, "GitHub": 12.0,
    "Habr": 15.0, "Qiita": 25.0, "Heise": 15.0, "RSS": 12.0,
}

# GitHub search API allows ~10 unauthenticated requests/minute. v9.0 fired six
# concurrent searches and reliably got 403/429. Serialise with a small gap.
_GITHUB_LOCK = threading.Lock()
_GITHUB_LAST_CALL = 0.0
_GITHUB_MIN_INTERVAL = 0.35


@dataclass
class CollectorOutcome:
    """Structured, fail-loud telemetry for one trench collector attempt."""

    name: str
    url: str
    ok: bool
    items: int
    status: int | None
    via: str
    error: str
    bot_wall: bool
    elapsed_ms: float


@dataclass
class CollectorLedger:
    """Thread-safe aggregate of all collector outcomes for one mining run."""

    outcomes: list[CollectorOutcome] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, outcome: CollectorOutcome) -> None:
        with self._lock:
            self.outcomes.append(outcome)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self.outcomes)
        ok = sum(1 for r in rows if r.ok)
        blocked = sum(1 for r in rows if r.bot_wall)
        return {
            "collectors": len(rows),
            "succeeded": ok,
            "failed": len(rows) - ok,
            "bot_walled": blocked,
            "items": sum(r.items for r in rows),
            "coverage_pct": round(100.0 * ok / len(rows), 1) if rows else 0.0,
            "mirror_coverage": coverage_from_ledger(self),
            "failures": [
                {"name": r.name, "status": r.status, "error": r.error}
                for r in rows if not r.ok
            ],
        }


LAST_LEDGER: CollectorLedger | None = None


@dataclass
class TrenchEvidenceItem:
    platform: str
    channel: str
    author: str
    title: str
    url: str
    date: str
    score: int
    content: str
    alpha_flag: bool = False
    lang: str = "en"
    kind: str = "practitioner_lead"
    proves: str = "operational_reality"
    # v10.0 additions (all defaulted -> existing positional construction works).
    signal_score: float = 0.0
    content_sha256: str = ""
    date_known: bool = True
    fetch_via: str = ""
    bot_wall: bool = False
    # v11.0: mirror-recovered items are SECONDARY transcriptions, never T1.
    evidence_class: str = "primary_fetched"
    source_url: str = ""
    # v12.0: Insider Anomaly Scorer. Defaults preserve every positional
    # construction in the pre-v12 test suite and downstream callers.
    insider_prior: float = 1.0
    insider_markers: list[str] = field(default_factory=list)
    insider_languages: list[str] = field(default_factory=list)
    dethroning_vector_id: str = ""

    @property
    def is_primary(self) -> bool:
        return self.evidence_class == "primary_fetched"

    @property
    def is_golden_nugget(self) -> bool:
        return self.insider_prior >= INSIDER_PRIOR_BOOST

    def __post_init__(self) -> None:
        # Coerce malformed collector output before any hashing / regex work.
        self.content = str(self.content or "")
        self.url = str(self.url or "")
        if not self.content_sha256:
            self.content_sha256 = hashlib.sha256(
                re.sub(r"\s+", " ", self.content).strip().encode("utf-8")
            ).hexdigest()
        anomaly = scan_insider_markers(self.content)
        if anomaly["is_insider"]:
            self.insider_prior = INSIDER_PRIOR_BOOST
            self.insider_markers = [h["marker"] for h in anomaly["hits"]]
            self.insider_languages = list(anomaly["languages"])
            # An insider witness is by definition high-alpha trench evidence.
            self.alpha_flag = True
        if not self.signal_score:
            self.signal_score = compute_signal_score(self)

    def render_snapshot_block(self) -> str:
        """Immutable, paragraph-aligned passage for BM25 and verbatim quotes.

        The v12.0 anomaly tag is *inline in the snapshot*, so the 3.0x BM25
        prior survives into ``context_pack.md`` even if the item is re-parsed
        from text rather than reconstructed as a dataclass.
        """
        tag = "[HIGH-SIGNAL TRENCH ALPHA]" if self.alpha_flag else "[PRACTITIONER COMMENT]"
        if self.is_golden_nugget:
            tag = "[GOLDEN NUGGET / INSIDER ANOMALY] " + tag
        clean_body = re.sub(r"\s+", " ", self.content).strip()
        date_field = self.date if self.date_known else "unknown (not asserted)"
        anomaly_line = render_anomaly_tag(self.content)
        return (
            f"=== TRENCH SNAPSHOT: {self.platform} ({self.channel}) [{self.lang.upper()}] ===\n"
            f"Author: {self.author} | Score: {self.score} | Signal: {self.signal_score:.1f}/100 | "
            f"Date: {date_field} | URL: {self.url}\n"
            f"Provenance: sha256={self.content_sha256[:16]} | via={self.fetch_via or 'api'} | "
            f"date_known={'yes' if self.date_known else 'no'} | class={self.evidence_class} | "
            f"bm25_prior=x{self.insider_prior:.1f}"
            + (f" | vector={self.dethroning_vector_id}" if self.dethroning_vector_id else "")
            + "\n"
            + (f"{anomaly_line}\n" if anomaly_line else "")
            + f"{tag} \"{clean_body}\"\n"
        )


def compute_signal_score(item: TrenchEvidenceItem) -> float:
    """Normalise engagement to a comparable 0-100 platform-relative signal.

    v9.0 sorted on the raw ``score`` field, which mixed HN points, GitHub
    comment counts, Qiita likes and hardcoded constants (Habr=10, Heise=15).
    Here engagement is log-saturated per platform, then combined with the
    alpha flag and a recency term that is EXCLUDED when the date is unknown.
    """
    scale = _PLATFORM_SCORE_SCALE.get(item.platform.split("(")[0].split("[")[0], 12.0)
    raw = max(0.0, float(item.score or 0))
    engagement = min(1.0, math.log1p(raw) / math.log1p(scale * 8.0 + 1.0))
    alpha = 1.0 if item.alpha_flag else 0.0
    if item.date_known:
        try:
            year = int(str(item.date)[:4])
            age_years = max(0, dt.date.today().year - year)
            recency = max(0.0, 1.0 - age_years / 5.0)
        except (ValueError, TypeError):
            recency = 0.0
    else:
        recency = 0.0  # unknown dates must not be rewarded as fresh
    base = 100.0 * (0.55 * engagement + 0.30 * alpha + 0.15 * recency)
    # v12.0: an insider witness is a distinct epistemic class, not merely
    # "more engagement". Additive, bounded bonus so the pre-v12 ordering is
    # preserved for every non-insider item.
    nugget = 15.0 if getattr(item, "is_golden_nugget", False) else 0.0
    return round(min(100.0, base + nugget), 2)


def _safe_date(raw: Any) -> tuple[str, bool]:
    """Parse a date honestly; never fabricate a current-year fallback."""
    if raw is None or raw == "":
        return "unknown", False
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", True
        except ValueError:
            return "unknown", False
    try:
        parsed = email.utils.parsedate_to_datetime(s)
        return parsed.date().isoformat(), True
    except (TypeError, ValueError, IndexError):
        pass
    return "unknown", False


def _strip_html_fragment(raw: str) -> str:
    """Normalise an HTML/API fragment into a single quotable line."""
    text = html.unescape(str(raw or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _record(
    ledger: CollectorLedger | None, name: str, url: str,
    result: Any, items: int, t0: float,
) -> None:
    """Write one fail-loud outcome; ``result`` is a FetchResult-like object."""
    if ledger is None:
        return
    ledger.record(CollectorOutcome(
        name=name, url=url, ok=bool(getattr(result, "ok", False)), items=items,
        status=getattr(result, "status", None), via=getattr(result, "via", "none"),
        error=str(getattr(result, "error", "") or "")[:200],
        bot_wall=bool(getattr(result, "bot_wall", False)),
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
    ))


def _record_failure(
    ledger: CollectorLedger | None, name: str, url: str, error: str, t0: float,
) -> None:
    """Structured, fail-loud outcome for a malformed collector input."""
    if ledger is None:
        return
    ledger.record(CollectorOutcome(
        name=name, url=str(url or ""), ok=False, items=0, status=None,
        via="none", error=str(error)[:200], bot_wall=False,
        elapsed_ms=(time.perf_counter() - t0) * 1000.0,
    ))


def _github_gate() -> None:
    """Serialise GitHub API calls to stay under the unauthenticated quota."""
    global _GITHUB_LAST_CALL
    with _GITHUB_LOCK:
        gap = time.perf_counter() - _GITHUB_LAST_CALL
        if gap < _GITHUB_MIN_INTERVAL:
            time.sleep(_GITHUB_MIN_INTERVAL - gap)
        _GITHUB_LAST_CALL = time.perf_counter()


# Generic expansion terms are useful for HN/StackExchange search but poison
# GitHub issue search: GitHub ANDs every bare term, so a 20-token polyglot
# query returns near-random repositories. Keep only entity anchors + a failure
# qualifier, and use GitHub's `is:issue` filter.
_GITHUB_GENERIC_TERMS = frozenset({
    "best", "top", "leading", "benchmark", "finance", "quantitative", "trading",
    "accounting", "model", "llm", "stocks", "equities", "execution", "spread",
    "friction", "bug", "issue", "defect", "failure", "production", "ratings",
    "comparison", "ranking", "金融", "量化", "交易", "財報", "大模型", "最佳", "评测",
    "нейросеть", "модель", "финансы", "алготрейдинг", "лучшая", "бенчмарк",
})


def github_query(poly_query: str, lang: str = "en") -> str:
    """Reduce a long polyglot query to GitHub-search-friendly entity anchors.

    Live testing showed that passing the full polyglot expansion into
    ``/search/issues?q=`` returns unrelated repositories because GitHub ANDs
    every bare term. This keeps at most 4 distinctive anchors and one failure
    qualifier, then restricts to issues.
    """
    tokens = re.findall(r"[^\s]{2,}", str(poly_query or ""))
    anchors: list[str] = []
    for tok in tokens:
        clean = tok.strip(".,;:!?()[]{}\"'")
        if not clean or clean.lower() in _GITHUB_GENERIC_TERMS:
            continue
        if clean.lower() in {a.lower() for a in anchors}:
            continue
        anchors.append(clean)
        if len(anchors) >= 4:
            break
    qualifier = {
        "en": "bug", "ru": "ошибка", "zh": "缺陷", "ja": "不具合",
        "ko": "오류", "de": "Fehler", "fr": "erreur", "es": "error",
    }.get(lang, "bug")
    core = " ".join(anchors) if anchors else (poly_query or "llm")[:60]
    return f"{core} {qualifier} is:issue"


def build_polyglot_queries(prompt: str) -> dict[str, list[str]]:
    """Generate distinct high-signal queries across 8 languages + BG.

    v10.0: concept detection covers both Bulgarian and English prompts. v9.0
    only checked ``BG_CONCEPT_MAP``, so an English mission briefing produced
    eight copies of the raw English anchor with zero translation.
    """
    # Malformed collector output (None / bytes / numeric) must not kill a
    # 12-language mining run: coerce once, then use the safe string.
    prompt = prompt.decode("utf-8", errors="replace") if isinstance(prompt, bytes) else str(prompt or "")
    low = prompt.lower()
    matched_concepts: set[str] = set()
    for bg_word, concept in BG_CONCEPT_MAP.items():
        if bg_word in low:
            matched_concepts.add(concept)
    for en_word, concept in EN_CONCEPT_MAP.items():
        if re.search(r"\b" + re.escape(en_word) + r"\b", low):
            matched_concepts.add(concept)

    # Keep short, high-signal acronyms (AI, ML, FX) that v9.0's {2,} dropped.
    eng_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,}", prompt)
    core_anchor = " ".join(dict.fromkeys(eng_tokens))

    poly_queries: dict[str, list[str]] = {}
    for lang in ("en", "ru", "zh", "ja", "ko", "de", "fr", "es"):
        lang_dict = POLYGLOT_DICTIONARY[lang]
        terms = [lang_dict[c] for c in sorted(matched_concepts) if c in lang_dict]

        q_list: list[str] = []
        if core_anchor and terms:
            q_list.append(f"{core_anchor} {' '.join(terms)}".strip())
        elif terms:
            q_list.append(" ".join(terms))
        elif core_anchor:
            q_list.append(core_anchor)

        failure_suffixes = {
            "en": "bug issue failure production",
            "ru": "алготрейдинг сбой ошибка",
            "zh": "金融大模型 评测 缺陷",
            "ja": "金融 LLM 不具合 課題",
            "ko": "금융 LLM 오류 장애",
            "de": "Finanzen LLM Fehler Ausfall",
            "fr": "finance LLM défaillance erreur",
            "es": "finanzas LLM fallo error",
        }
        q_list.append(f"{core_anchor} {failure_suffixes[lang]}".strip())
        poly_queries[lang] = [q for q in dict.fromkeys(q_list) if q]

    poly_queries["bg"] = [prompt.strip()]
    return poly_queries


# ---------------------------------------------------------------------------
# Polyglot Keyless Trench Collectors
# ---------------------------------------------------------------------------

def mine_hacker_news_comments(
    query: str, max_hits: int = 4, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Mine deep nested Hacker News comments via the keyless Algolia API."""
    t0 = time.perf_counter()
    url = ("https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote_plus(query)
           + f"&tags=comment&hitsPerPage={max_hits}")
    result, data = fetch_json(url, timeout=timeout, retries=2)
    items: list[TrenchEvidenceItem] = []
    if result.ok and isinstance(data, dict):
        for h in data.get("hits", []):
            clean = _strip_html_fragment(h.get("comment_text") or "")
            if len(clean) < 40:
                continue
            story_id = h.get("story_id") or h.get("objectID")
            date_str, date_known = _safe_date(h.get("created_at"))
            items.append(TrenchEvidenceItem(
                platform="HackerNews", channel=f"Story#{story_id}",
                author=h.get("author") or "anonymous",
                title=h.get("story_title") or f"HN Discussion #{story_id}",
                url=f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                date=date_str, score=int(h.get("points") or 0),
                content=clean[:1200], alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(clean)),
                lang="en", date_known=date_known, fetch_via=result.via,
            ))
    _record(ledger, "hacker_news", url, result, len(items), t0)
    return items


def mine_quant_stackexchange(
    query: str, site: str = "quant", max_hits: int = 4, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Mine technical Q&A with LaTeX-preserving bodies from StackExchange API."""
    t0 = time.perf_counter()
    url = ("https://api.stackexchange.com/2.3/search/advanced?site=" + site
           + "&q=" + urllib.parse.quote_plus(query) + f"&filter=withbody&pagesize={max_hits}")
    result, data = fetch_json(url, timeout=timeout, retries=2)
    items: list[TrenchEvidenceItem] = []
    if result.ok and isinstance(data, dict):
        for it in data.get("items", []):
            clean = _strip_html_fragment(it.get("body") or "")
            if len(clean) < 60:
                continue
            created = it.get("creation_date")
            try:
                raw_date = dt.datetime.fromtimestamp(int(created), tz=dt.timezone.utc).date().isoformat() if created else None
            except (ValueError, TypeError, OSError, OverflowError):
                raw_date = None
            date_str, date_known = _safe_date(raw_date)
            items.append(TrenchEvidenceItem(
                platform=f"StackExchange({site})", channel=site,
                author=(it.get("owner") or {}).get("display_name") or "practitioner",
                title=it.get("title") or "Technical Discussion",
                url=it.get("link") or f"https://{site}.stackexchange.com/q/{it.get('question_id')}",
                date=date_str, score=int(it.get("score") or 0),
                content=clean[:1500], alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(clean)),
                lang="en", date_known=date_known, fetch_via=result.via,
            ))
    _record(ledger, f"stackexchange_{site}", url, result, len(items), t0)
    return items


def mine_github_issues(
    query: str, lang: str = "en", max_hits: int = 4, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Mine GitHub issues/PRs (rate-limited; optional GITHUB_TOKEN raises quota)."""
    t0 = time.perf_counter()
    url = ("https://api.github.com/search/issues?q=" + urllib.parse.quote_plus(query)
           + f"&per_page={max_hits}")
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    _github_gate()
    result, data = fetch_json(url, timeout=timeout, retries=2, headers=headers)
    items: list[TrenchEvidenceItem] = []
    if result.ok and isinstance(data, dict):
        for it in data.get("items", []):
            body = re.sub(r"<!--[\s\S]*?-->", "", str(it.get("body") or ""))
            clean = re.sub(r"\s+", " ", body).strip()
            if len(clean) < 50:
                continue
            date_str, date_known = _safe_date(it.get("created_at"))
            items.append(TrenchEvidenceItem(
                platform=f"GitHub[{lang.upper()}]",
                channel=str(it.get("repository_url", "")).split("/")[-1] or "issues",
                author=(it.get("user") or {}).get("login") or "developer",
                title=it.get("title") or "Issue Report",
                url=it.get("html_url") or "", date=date_str,
                score=int(it.get("comments") or 0),
                content=f"Title: {it.get('title')}. Body: {clean[:1200]}",
                alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(clean)), lang=lang,
                date_known=date_known, fetch_via=result.via,
                bot_wall=result.bot_wall,
            ))
    _record(ledger, f"github_{lang}", url, result, len(items), t0)
    return items


def mine_habr_articles(
    query: str, max_hits: int = 4, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Mine Russian engineering / quant postmortems from Habr RSS search."""
    t0 = time.perf_counter()
    url = "https://habr.com/ru/rss/search/?q=" + urllib.parse.quote_plus(query) + "&target_type=posts"
    result, root = fetch_xml(url, timeout=timeout, retries=2)
    items: list[TrenchEvidenceItem] = []
    if result.ok and root is not None:
        for node in root.findall(".//item")[:max_hits]:
            title = _strip_html_fragment(node.findtext("title") or "")
            link = (node.findtext("link") or "").strip()
            clean = _strip_html_fragment(node.findtext("description") or "") or title
            date_str, date_known = _safe_date(node.findtext("pubDate"))
            items.append(TrenchEvidenceItem(
                platform="Habr", channel="RU_Engineering", author="habr_engineer",
                title=title, url=link, date=date_str, score=10,
                content=f"Title: {title}. Excerpt: {clean[:1200]}",
                alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(f"{title} {clean}")),
                lang="ru", date_known=date_known, fetch_via=result.via,
                bot_wall=result.bot_wall,
            ))
    _record(ledger, "habr_ru", url, result, len(items), t0)
    return items


def mine_qiita_articles(
    query: str, max_hits: int = 4, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Mine Japanese engineering articles / LLM benchmarks from Qiita API v2."""
    t0 = time.perf_counter()
    url = "https://qiita.com/api/v2/items?query=" + urllib.parse.quote_plus(query) + f"&per_page={max_hits}"
    result, data = fetch_json(url, timeout=timeout, retries=2)
    items: list[TrenchEvidenceItem] = []
    if result.ok and isinstance(data, list):
        for it in data:
            title = str(it.get("title") or "")
            body = re.sub(r"```[\s\S]*?```", " ", str(it.get("body") or ""))
            clean = _strip_html_fragment(body)
            date_str, date_known = _safe_date(it.get("created_at"))
            items.append(TrenchEvidenceItem(
                platform="Qiita", channel="JA_Tech",
                author=(it.get("user") or {}).get("id") or "qiita_user",
                title=title, url=it.get("url") or "", date=date_str,
                score=int(it.get("likes_count") or 0),
                content=f"Title: {title}. Excerpt: {clean[:1200]}",
                alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(f"{title} {clean}")),
                lang="ja", date_known=date_known, fetch_via=result.via,
                bot_wall=result.bot_wall,
            ))
    _record(ledger, "qiita_ja", url, result, len(items), t0)
    return items


def mine_rss_feed(
    feed_url: str, query: str, platform: str = "RSS", lang: str = "en",
    max_hits: int = 3, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Generic RSS/Atom trench collector with relevance filtering.

    v9.0's Heise collector used ``or len(items) < 1`` to force at least one
    item regardless of relevance, injecting off-topic text into the evidence
    stream. v10.0 returns nothing when nothing matches.
    """
    t0 = time.perf_counter()
    # v12.0 Frontier 4: a malformed feed template ("{q}", "{0}", unmatched
    # brace) must produce a structured failure, not an uncaught KeyError that
    # silently removes the whole collector from the swarm.
    feed_url = str(feed_url or "")
    try:
        url = (feed_url.format(query=urllib.parse.quote_plus(str(query or "")))
               if "{query}" in feed_url else feed_url)
    except (KeyError, IndexError, ValueError, AttributeError) as exc:
        _record_failure(ledger, f"rss_{platform}", feed_url,
                        f"malformed feed template: {exc}", t0)
        return []
    if not url:
        _record_failure(ledger, f"rss_{platform}", feed_url, "empty feed URL", t0)
        return []
    result, root = fetch_xml(url, timeout=timeout, retries=2)
    items: list[TrenchEvidenceItem] = []
    if not (result.ok and root is not None):
        _record(ledger, f"rss_{platform}", url, result, 0, t0)
        return items

    q_words = [w for w in tokenize(query) if len(w) >= 3][:12]
    atom = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(f".//{atom}entry")
    for node in nodes[: max_hits * 4]:
        def txt(*names: str) -> str:
            for name in names:
                el = node.find(name)
                if el is not None:
                    return _strip_html_fragment("".join(el.itertext()) or el.text or "")
            return ""
        title = txt("title", f"{atom}title")
        summary = txt("description", "summary", f"{atom}summary", f"{atom}content")
        link = txt("link", f"{atom}link")
        if not link:
            lel = node.find(f"{atom}link")
            if lel is not None:
                link = lel.attrib.get("href", "")
        haystack = f"{title} {summary}".lower()
        relevance = sum(1 for w in q_words if w in haystack) / max(1, len(q_words))
        if q_words and relevance < 0.25:
            continue
        date_str, date_known = _safe_date(txt("pubDate", f"{atom}updated", f"{atom}published", "pubDate"))
        combined = f"Title: {title}. Excerpt: {summary[:1200]}"
        items.append(TrenchEvidenceItem(
            platform=platform, channel="RSS_Atom", author=f"{platform}_community",
            title=title, url=link, date=date_str, score=8,
            content=combined, alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(combined)),
            lang=lang, date_known=date_known, fetch_via=result.via,
            bot_wall=result.bot_wall,
        ))
        if len(items) >= max_hits:
            break
    _record(ledger, f"rss_{platform}", url, result, len(items), t0)
    return items


def mine_heise_articles(
    query: str, max_hits: int = 3, timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
) -> list[TrenchEvidenceItem]:
    """Mine German DACH engineering discussion from the Heise Atom feed."""
    return mine_rss_feed(
        "https://www.heise.de/rss/heise-atom.xml", query,
        platform="Heise", lang="de", max_hits=max_hits, timeout=timeout, ledger=ledger,
    )


# ---------------------------------------------------------------------------
# v12.0 Frontier 1 & 2 — Active Dethroning trenches + Golden Nugget mining
# ---------------------------------------------------------------------------

def _vector_fields(vector: Any) -> dict[str, Any]:
    """Accept both DethroningVector and a JSON dict from study_spec.json."""
    if isinstance(vector, DethroningVector):
        return {
            "vector_id": vector.vector_id, "lang": vector.lang,
            "query": vector.query, "window_days": vector.window_days,
            "since": vector.since, "until": vector.until,
        }
    if isinstance(vector, dict):
        return {
            "vector_id": str(vector.get("vector_id") or "DTH-UNKNOWN"),
            "lang": str(vector.get("lang") or "en"),
            "query": str(vector.get("query") or ""),
            "window_days": int(vector.get("window_days") or 90)
            if str(vector.get("window_days") or "").isdigit() else 90,
            "since": str(vector.get("since") or ""),
            "until": str(vector.get("until") or ""),
        }
    return {"vector_id": "DTH-MALFORMED", "lang": "en", "query": "",
            "window_days": 90, "since": "", "until": ""}


def _short_dethrone_query(full_query: str, limit: int = 6) -> str:
    """Reduce a long OR-vector to the entity anchors an API can actually match.

    GitHub / Algolia / RSS search AND bare terms, so a full 20-token OR
    expression returns noise. Keep the distinctive quoted anchors, drop the
    boolean glue and the date operators.
    """
    parts = re.findall(r'"([^"]{2,80})"', str(full_query or ""))
    if not parts:
        parts = [str(full_query or "")]
    words: list[str] = []
    for p in parts:
        for w in re.findall(r"[^\s]{2,}", p):
            low = w.lower().strip(".,;:()")
            if low in {"or", "and", "after", "before", "new", "record", "by", "the", "a"}:
                continue
            if re.match(r"^\d{4}-\d{2}-\d{2}$", low):
                continue
            if low and low not in {x.lower() for x in words}:
                words.append(w.strip(".,;:()"))
            if len(words) >= limit:
                return " ".join(words)
    return " ".join(words) or "new record"


def build_dethroning_trench_queries(
    prompt: str, as_of: dt.date | str | None = None,
) -> list[DethroningVector]:
    """Convenience: spawn O_dethrone vectors for a superlative prompt."""
    claims = detect_superlative_claims(prompt)
    if not claims:
        return []
    info = extract_leader_value(prompt)
    tokens = re.findall(r"[A-Za-zА-Яа-я][\w'.-]{2,}", str(prompt or ""))
    leader = " ".join(tokens[:2]) or "the current leader"
    return build_dethroning_vectors(leader, str(info["metric"]), as_of=as_of)


def mine_dethroning_vectors(
    vectors: list[Any],
    timeout: float = 6.0,
    max_items: int = 4,
    ledger: CollectorLedger | None = None,
    max_vectors: int = 6,
) -> list[TrenchEvidenceItem]:
    """Execute adversarial dethroning vectors against practitioner trenches.

    Prefer the 30-day (zero-lag) band, one vector per language, then fill with
    the 90-day band. Every collector attempt writes a ``CollectorOutcome`` so a
    blackout is visible; results carry ``dethroning_vector_id`` and are tagged
    with the Insider Anomaly Scorer automatically by ``TrenchEvidenceItem``.

    Never raises on malformed vectors (dicts, None, bad window_days).
    """
    own_ledger = ledger or CollectorLedger()
    normalised = [_vector_fields(v) for v in (vectors or []) if v is not None]
    normalised = [v for v in normalised if v["query"]]
    # 30-day band first: zero-lag beats breadth. One vector per language.
    normalised.sort(key=lambda v: (v["window_days"], v["lang"]))
    picked: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, int]] = set()
    for v in normalised:
        key = (v["lang"], v["window_days"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        picked.append(v)
        if len(picked) >= max_vectors:
            break

    results: list[TrenchEvidenceItem] = []
    seen_urls: set[str] = set()
    for v in picked:
        short = _short_dethrone_query(v["query"])
        batch: list[TrenchEvidenceItem] = []
        try:
            if v["lang"] == "en":
                batch.extend(mine_hacker_news_comments(short, 2, timeout, own_ledger))
            batch.extend(mine_rss_feed(
                "https://www.reddit.com/search.rss?q={query}&sort=new&t=month",
                short, platform=f"Dethrone[{v['lang'].upper()}]",
                lang=v["lang"], max_hits=2, timeout=timeout, ledger=own_ledger,
            ))
        except Exception as exc:  # fail-loud
            own_ledger.record(CollectorOutcome(
                name=f"dethrone_{v['lang']}", url=short, ok=False, items=0,
                status=None, via="none",
                error=f"{type(exc).__name__}: {exc}"[:200],
                bot_wall=False, elapsed_ms=0.0,
            ))
        for it in batch:
            if not it.url or it.url in seen_urls:
                continue
            seen_urls.add(it.url)
            it.dethroning_vector_id = v["vector_id"]
            it.channel = f"O_dethrone:{v['vector_id']}"
            it.kind = "dethroning_vector"
            it.proves = "leader_supersession"
            it.title = f"[O_dethrone {v['vector_id']} {v['window_days']}d] {it.title}"
            results.append(it)
            if len(results) >= max_items:
                return results
    return results


# ---------------------------------------------------------------------------
# Omniscient Orchestrator: Multi-Language Trench Swarm
# ---------------------------------------------------------------------------

def mine_all_trenches(
    prompt: str,
    domain: str = "general",
    max_total_items: int = 12,
    timeout: float = 8.0,
    ledger: CollectorLedger | None = None,
    extra_feeds: bool = True,
    enable_mirrors: bool = True,
    max_rescues: int = 8,
    enable_dethroning: bool = True,
) -> list[TrenchEvidenceItem]:
    """Orchestrate parallel mining with per-collector telemetry.

    ``ledger`` receives one :class:`CollectorOutcome` per attempted endpoint,
    so a blocked or rate-limited trench is visible rather than silent.

    v11.0: ``enable_mirrors`` activates the deterministic keyless fallback
    rescue for every blocked endpoint (Wayback / syndication / search cache).
    Rescued bodies are marked ``evidence_class != primary_fetched`` so they can
    never be mistaken for primary T1 evidence.
    """
    global LAST_LEDGER
    own_ledger = ledger or CollectorLedger()
    LAST_LEDGER = own_ledger

    poly = build_polyglot_queries(prompt)
    def q(lang: str) -> str:
        vals = poly.get(lang) or []
        return vals[0] if vals else ""

    q_en, q_ru, q_zh = q("en"), q("ru"), q("zh")
    q_ja, q_ko, q_de = q("ja"), q("ko"), q("de")
    q_fr, q_es = q("fr"), q("es")

    results: list[TrenchEvidenceItem] = []
    jobs: list[tuple[Any, tuple[Any, ...]]] = [
        (mine_hacker_news_comments, (q_en or prompt, 4, timeout, own_ledger)),
        (mine_quant_stackexchange, (q_en or prompt, "quant" if domain in ("quant", "finance") else "datascience", 4, timeout, own_ledger)),
        (mine_github_issues, (github_query(q_en or prompt, "en"), "en", 4, timeout, own_ledger)),
    ]
    if q_ru:
        jobs.append((mine_habr_articles, (q_ru, 3, timeout, own_ledger)))
    if q_ja:
        jobs.append((mine_qiita_articles, (q_ja, 3, timeout, own_ledger)))
    if q_zh:
        jobs.append((mine_github_issues, (github_query(q_zh, "zh"), "zh", 3, timeout, own_ledger)))
    if q_ko:
        jobs.append((mine_github_issues, (github_query(q_ko, "ko"), "ko", 3, timeout, own_ledger)))
    if q_de:
        jobs.append((mine_heise_articles, (q_de, 2, timeout, own_ledger)))
        jobs.append((mine_github_issues, (github_query(q_de, "de"), "de", 2, timeout, own_ledger)))
    if q_fr:
        jobs.append((mine_github_issues, (github_query(q_fr, "fr"), "fr", 2, timeout, own_ledger)))
    if q_es:
        jobs.append((mine_github_issues, (github_query(q_es, "es"), "es", 2, timeout, own_ledger)))
    if extra_feeds:
        for platform, lang, feed in RSS_TRENCH_FEEDS:
            jobs.append((mine_rss_feed, (feed, q_en or prompt, platform, lang, 2, timeout, own_ledger)))

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(fn, *args) for fn, args in jobs]
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.extend(fut.result() or [])
            except Exception as exc:  # fail-loud: log, never silently drop
                own_ledger.record(CollectorOutcome(
                    name="orchestrator", url="", ok=False, items=0, status=None,
                    via="none", error=f"{type(exc).__name__}: {exc}"[:200],
                    bot_wall=False, elapsed_ms=0.0,
                ))

    # ------------------------------------------------------------------
    # v11.0 Frontier 1: rescue blocked endpoints through keyless mirrors.
    # Only failed collectors are retried, and every rescue is recorded as a
    # distinct ledger outcome so coverage is measurable, not assumed.
    # ------------------------------------------------------------------
    if enable_mirrors:
        blocked_urls = list(dict.fromkeys(
            o.url for o in own_ledger.outcomes if not o.ok and o.url
        ))[:max_rescues]
        for blocked_url in blocked_urls:
            t_rescue = time.perf_counter()
            try:
                rescued = fetch_with_fallbacks(
                    blocked_url, timeout=min(timeout, 5.0), max_bytes=500_000,
                )
            except Exception as exc:  # fail-loud
                own_ledger.record(CollectorOutcome(
                    name="mirror_error", url=blocked_url, ok=False, items=0,
                    status=None, via="none",
                    error=f"{type(exc).__name__}: {exc}"[:200],
                    bot_wall=False, elapsed_ms=0.0,
                ))
                continue
            own_ledger.record(CollectorOutcome(
                name=f"mirror:{rescued.via}", url=blocked_url, ok=bool(rescued.ok),
                items=1 if rescued.ok else 0, status=rescued.status,
                via=rescued.via, error=rescued.error[:200],
                bot_wall=rescued.bot_wall,
                elapsed_ms=(time.perf_counter() - t_rescue) * 1000.0,
            ))
            if not rescued.ok:
                continue
            body = rescued.text.strip()
            results.append(TrenchEvidenceItem(
                platform="MirrorRescue", channel=rescued.via,
                author="archival_mirror", title=f"Recovered: {blocked_url[:90]}",
                url=blocked_url, date="unknown", score=6,
                content=body[:1200],
                alpha_flag=bool(TRENCH_ALPHA_PATTERNS.search(body)),
                lang="en", date_known=False, fetch_via=rescued.via,
                evidence_class=rescued.evidence_class,
                source_url=rescued.source_url,
            ))

    # ------------------------------------------------------------------
    # v12.0 Frontier 1: a superlative prompt MUST trigger O_dethrone. The
    # engine actively searches for evidence that breaks the identified leader
    # rather than stopping at the first high-SEO authoritative answer.
    # ------------------------------------------------------------------
    if enable_dethroning:
        try:
            d_vectors = build_dethroning_trench_queries(prompt)
            if d_vectors:
                results.extend(mine_dethroning_vectors(
                    d_vectors, timeout=min(timeout, 6.0), max_items=3,
                    ledger=own_ledger,
                ))
        except Exception as exc:  # fail-loud: never silently skip the protocol
            own_ledger.record(CollectorOutcome(
                name="dethroning_protocol", url="", ok=False, items=0,
                status=None, via="none",
                error=f"{type(exc).__name__}: {exc}"[:200],
                bot_wall=False, elapsed_ms=0.0,
            ))

    # Comparable, platform-normalised ranking (v9.0 mixed raw scores).
    results.sort(key=lambda x: (x.signal_score, x.alpha_flag, x.insider_prior), reverse=True)

    # Dedup by URL *and* content hash: cross-posts must not inflate N_eff.
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    unique: list[TrenchEvidenceItem] = []
    for r in results:
        if not r.url or r.url in seen_urls or r.content_sha256 in seen_hashes:
            continue
        seen_urls.add(r.url)
        seen_hashes.add(r.content_sha256)
        unique.append(r)
        if len(unique) >= max_total_items:
            break
    return unique


def build_trench_snapshot_dict(
    prompt: str, domain: str = "general", max_items: int = 6,
) -> dict[str, str]:
    """Return ``{url: snapshot_text}`` ready for ``study_spec.inline_sources``."""
    items = mine_all_trenches(prompt, domain=domain, max_total_items=max_items)
    return {it.url: it.render_snapshot_block() for it in items}


def get_last_ledger_summary() -> dict[str, Any]:
    """Provenance summary of the most recent mining run (for ``auto_spec``)."""
    return (LAST_LEDGER.summary() if LAST_LEDGER is not None else {"collectors": 0})


def coverage_from_ledger(ledger: CollectorLedger) -> dict[str, Any]:
    """v11.0: measured endpoint coverage from collector outcomes.

    A collector counts as *covered* when it succeeded directly OR a mirror
    rescue for the same URL succeeded. This is a measurement over attempts,
    not an estimate.
    """
    outcomes = list(ledger.outcomes)
    if not outcomes:
        return {"attempted": 0, "covered": 0, "coverage_pct": 0.0,
                "primary_coverage_pct": 0.0, "meets_95pct_target": False}
    direct = [o for o in outcomes if not o.name.startswith("mirror:")]
    rescue_by_url: dict[str, str] = {}
    for o in outcomes:
        if o.name.startswith("mirror:") and o.ok and o.url:
            rescue_by_url[o.url] = o.name.split(":", 1)[-1]
    covered = 0
    primary = 0
    secondary = 0
    for o in direct:
        if o.ok:
            covered += 1
            primary += 1
        elif o.url in rescue_by_url:
            covered += 1
            secondary += 1
    # A search-cache hit yields LEADS ONLY, never primary evidence. Reporting
    # this separately prevents "100% coverage" from being misread as "100%
    # primary-source coverage" -- an epistemic distinction, not a detail.
    lead_only = sum(
        1 for url, via in rescue_by_url.items()
        if via.startswith("search_cache")
    )
    return {
        "attempted": len(direct),
        "covered": covered,
        "primary_recoveries": primary,
        "secondary_recoveries": secondary,
        "lead_only_recoveries": lead_only,
        "mirror_rescues": len(rescue_by_url),
        "coverage_pct": round(100.0 * covered / len(direct), 1),
        "primary_coverage_pct": round(100.0 * primary / len(direct), 1),
        "meets_95pct_target": (covered / len(direct)) >= 0.95,
    }


# ---------------------------------------------------------------------------
# CLI & Self-Test
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Deep Research Polyglot Trench Miner v10.0 CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_mine = sub.add_parser("mine", help="Mine global trenches for a topic")
    p_mine.add_argument("query", help="Topic or query prompt")
    p_mine.add_argument("--domain", default="general", help="quant, finance, saas, ai")
    p_mine.add_argument("--limit", type=int, default=6, help="Max results")
    p_mine.add_argument("--no-mirrors", action="store_true",
                        help="Disable Wayback/syndication/search-cache rescue")
    p_mine.add_argument("--json", action="store_true", help="Emit JSON with collector telemetry")

    p_poly = sub.add_parser("polyglot", help="Show polyglot expanded query matrix")
    p_poly.add_argument("query", help="Raw prompt")

    sub.add_parser("selftest", help="Run self-test suite")
    args = parser.parse_args()

    if args.cmd == "polyglot":
        for lang, ql in build_polyglot_queries(args.query).items():
            print(f"[{lang.upper()}]: {ql}")
        return 0

    if args.cmd == "mine":
        ledger = CollectorLedger()
        items = mine_all_trenches(args.query, domain=args.domain,
                                 max_total_items=args.limit, ledger=ledger,
                                 enable_mirrors=not args.no_mirrors)
        if args.json:
            print(json.dumps({
                "items": [asdict(i) for i in items],
                "collector_ledger": ledger.summary(),
                "mirror_coverage": coverage_from_ledger(ledger),
            }, ensure_ascii=False, indent=2))
            return 0
        cov = coverage_from_ledger(ledger)
        print(f"[POLYGLOT TRENCH MINER v11.0] {len(items)} practitioner items | "
              f"{cov['coverage_pct']}% endpoint coverage (target >=95%, "
              f"mirror rescues={cov['mirror_rescues']}) | "
              f"{cov['primary_coverage_pct']}% PRIMARY-source coverage | "
              f"{cov['lead_only_recoveries']} lead-only cache recoveries")
        for i, it in enumerate(items, 1):
            flag = "[ALPHA]" if it.alpha_flag else ""
            print(f" {i}. [{it.lang.upper()}] {it.platform} signal={it.signal_score:.1f} date={it.date} {flag}")
            print(f"    {it.url}\n    {it.title[:120]}")
        for f in ledger.summary()["failures"]:
            print(f"  [COLLECTOR FAIL] {f['name']}: HTTP {f['status']} {f['error'][:100]}")
        return 0

    if args.cmd == "selftest" or len(sys.argv) == 1:
        poly = build_polyglot_queries("Кой е най-добрият AI модел за финанси")
        for expected_lang in ("en", "ru", "zh", "ja", "ko", "de", "fr", "es"):
            assert expected_lang in poly, f"Missing {expected_lang} in polyglot queries"
        assert any("model" in x.lower() or "llm" in x.lower() for x in poly["en"])
        assert any("финансы" in x.lower() or "алготрейдинг" in x.lower() for x in poly["ru"])
        assert any("金融" in x or "大模型" in x for x in poly["zh"])
        assert any("거대언어모델" in x or "금융" in x for x in poly["ko"])
        assert any("Sprachmodell" in x or "Finanzen" in x for x in poly["de"])
        assert any("finance" in x.lower() or "modèle" in x.lower() for x in poly["fr"])
        assert any("finanzas" in x.lower() or "modelo" in x.lower() for x in poly["es"])

        # v10.0: an English prompt must actually translate concepts.
        en_poly = build_polyglot_queries("best LLM for finance slippage bugs")
        assert any("финансы" in x or "алготрейдинг" in x for x in en_poly["ru"])
        assert any("金融" in x or "量化" in x for x in en_poly["zh"])

        # Unknown dates are not fabricated as current-year recency.
        assert _safe_date(None) == ("unknown", False)
        assert _safe_date("Wed, 05 Nov 2026 10:00:00 GMT") == ("2026-11-05", True)
        assert _safe_date("not-a-date") == ("unknown", False)

        # GitHub queries must be short entity anchors, not 20-token AND soup.
        gq = github_query(
            "Gemini GPT-6 best top leading benchmark finance quantitative trading accounting",
            "en",
        )
        assert "is:issue" in gq and len(gq.split()) <= 6 and "quantitative" not in gq

        dummy = TrenchEvidenceItem(
            platform="Habr", channel="RU_Engineering", author="quant_engineer",
            title="Knight Capital Analysis", url="https://habr.com/ru/articles/890142/",
            date="2026-11-01", score=45,
            content="Сбой в алгоритме исполнения привел к убытку в 440 миллионов за 45 минут.",
            alpha_flag=True, lang="ru",
        )
        snap = dummy.render_snapshot_block()
        assert "=== TRENCH SNAPSHOT: Habr (RU_Engineering) [RU] ===" in snap
        assert "[HIGH-SIGNAL TRENCH ALPHA]" in snap
        assert "440 миллионов" in snap
        assert "sha256=" in snap and dummy.content_sha256[:16] in snap

        # Signal is bounded, alpha-bearing, and never rewards an unknown date.
        hn = TrenchEvidenceItem("HackerNews", "Story#1", "a", "t", "https://hn/1",
                                "2026-11-01", 2, "x" * 60)
        hn_alpha = TrenchEvidenceItem("HackerNews", "Story#2", "a", "t", "https://hn/2",
                                      "2026-11-01", 2, "x" * 60, alpha_flag=True)
        habr_known = TrenchEvidenceItem("Habr", "RU", "a", "t", "https://habr/1",
                                        "2026-11-01", 10, "y" * 60)
        habr_unknown = TrenchEvidenceItem("Habr", "RU", "a", "t", "https://habr/2",
                                          "unknown", 10, "y" * 60, date_known=False)
        assert hn_alpha.signal_score > hn.signal_score, "alpha signal ignored"
        assert habr_known.signal_score > habr_unknown.signal_score, "unknown date rewarded as fresh"
        assert all(0.0 <= x.signal_score <= 100.0 for x in (hn, hn_alpha, habr_known, habr_unknown))

        led = CollectorLedger()
        led.record(CollectorOutcome("test", "https://x", False, 0, 403, "direct", "blocked", True, 1.0))
        assert led.summary()["bot_walled"] == 1 and led.summary()["failed"] == 1

        # v11.0: a mirror rescue for the same URL raises measured coverage.
        led.record(CollectorOutcome("mirror:wayback_cdx", "https://x", True, 1,
                                    200, "wayback_cdx", "", False, 2.0))
        cov = coverage_from_ledger(led)
        assert cov["attempted"] == 1 and cov["covered"] == 1
        assert cov["coverage_pct"] == 100.0 and cov["meets_95pct_target"]
        assert cov["mirror_rescues"] == 1
        assert led.summary()["mirror_coverage"]["meets_95pct_target"]

        # Mirror-rescued items are explicitly downgraded, never primary T1.
        mirror_item = TrenchEvidenceItem(
            "MirrorRescue", "wayback_cdx", "archive", "Recovered thread",
            "https://reddit.com/r/x/comments/abc", "unknown", 5,
            "In production the spread widened to 4.2 bps and the edge died.",
            date_known=False, fetch_via="wayback_cdx",
            evidence_class="archival_copy",
        )
        assert not mirror_item.is_primary
        assert "class=archival_copy" in mirror_item.render_snapshot_block()

        # v12.0 Frontier 2: insider witness markers across all 8 trench
        # languages must set the exact 3.0x BM25 prior and survive into the
        # immutable snapshot block (so context_ranker can boost them later).
        samples = {
            "en": "I was there; the real number was 511 kg, not 510 kg.",
            "ru": "На самом деле вчера на помосте слили в закрытый чат результат.",
            "zh": "内部消息：实际跑分实测翻车，纪录被打破。",
            "es": "En vivo vimos que superó a Björnsson: nuevo récord de 511 kg.",
            "de": "Tatsächlich geschlagen: neuer Rekord im Produktivbetrieb gescheitert.",
            "ko": "실제로는 어제 대회에서 신기록 달성, 실서버 장애.",
            "ja": "実際の測定値では新記録達成、本番で発覚した不具合。",
            "fr": "Sur place nous avons vu un nouveau record: en réalité c'était 511 kg.",
        }
        for lang, sample in samples.items():
            nug = TrenchEvidenceItem(
                "NicheForum", lang, "insider", "Eyewitness",
                f"https://forum.test/{lang}/1", "2026-11-05", 1, sample,
                lang=lang,
            )
            assert nug.is_golden_nugget, f"insider marker missed in {lang}"
            assert nug.insider_prior == INSIDER_PRIOR_BOOST
            assert lang in nug.insider_languages, (lang, nug.insider_languages)
            snap = nug.render_snapshot_block()
            assert "[GOLDEN NUGGET / INSIDER ANOMALY]" in snap
            assert "bm25_prior=x3.0" in snap
        generic = TrenchEvidenceItem(
            "PressRelease", "PR", "vendor", "Announcement",
            "https://vendor.test/news", "2026-11-05", 500,
            "The vendor announced a new benchmark result for its platform.",
        )
        assert not generic.is_golden_nugget and generic.insider_prior == 1.0

        # v12.0 Frontier 1: O_dethrone vectors for a superlative prompt.
        dvecs = build_dethroning_trench_queries(
            "Who holds the deadlift world record of 510 kg and is still #1?")
        assert len(dvecs) >= 16 and {v.window_days for v in dvecs} == {30, 90}
        assert not build_dethroning_trench_queries("Estimate execution friction in bps.")
        assert _short_dethrone_query(dvecs[0].query)

        # v12.0 Frontier 4: malformed inputs never raise.
        assert "en" in build_polyglot_queries(None)
        assert "is:issue" in github_query(None, "en")
        malformed_ledger = CollectorLedger()
        assert mine_rss_feed("https://feed.test/{query}/{bad}", "record",
                             ledger=malformed_ledger) == []
        assert any("malformed feed template" in r.error
                   for r in malformed_ledger.outcomes)
        assert scan_insider_markers(None)["prior"] == 1.0

        print("[SELFTEST PASS] trench_miner v12.0 (O_dethrone / 8-language insider prior x3.0 / "
              "telemetry / mirrors / malformed inputs) verified.")
        return 0

    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
