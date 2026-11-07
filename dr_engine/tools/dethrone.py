#!/usr/bin/env python3
"""Deep Research Engine v12.0 — Active Dethroning Protocol (Frontier 1).

"The Premature Search Termination Trap": a search agent asked for a world
record or the top model stops at the first high-SEO authoritative answer and
certifies it. The 510 kg answer is correct until the day a 511 kg lift happens
in Birmingham; the announced frontier model is current until a staged preview
appears. A superlative is a *perishable* claim and must be re-verified against
adversarial evidence before certification.

Operator O_dethrone:

  1. Detect any superlative / leader claim L on metric M in the prompt or the
     drafted report (mechanical phrase inventory, 9 languages).
  2. Spawn adversarial search vectors designed specifically to BREAK L:
     ``"<M> surpassed by" OR "beat <L>" OR "new record" OR "defeated by"
     OR "outperformed <L>"`` plus 8 translations, each anchored to a computed
     (never hardcoded) 30-day and 90-day recency window.
  3. Adjudicate the returned snapshots mechanically: a fresh supersession
     phrase plus a challenger or a higher measured value => L is DETHRONED.
     No evidence, stale evidence or too few vectors => UNVERIFIED, which is
     **fail-closed**: no superlative claim may be certified.
  4. Rule B11 gates ``verify_study``: a superlative claim in prose requires a
     corresponding, verified, in-window ``manifest.dethroning`` record.

Zero-lag invariant: every vector carries ``after:`` / ``before:`` ISO dates
derived from ``as_of`` and every verdict records ``checked_at``. A check older
than 30 days cannot certify a superlative.

Pure Python 3.10+ stdlib. Zero paid API keys. Windows cp1252-safe.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Allow both `python dr_engine/tools/dethrone.py` and package import.
_workspace_root = Path(__file__).resolve().parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from dr_engine.tools.insider_anomaly import normalise_for_match  # noqa: E402

__all__ = [
    "RECENCY_WINDOWS_DAYS", "MIN_DETHRONING_VECTORS", "MAX_CHECK_AGE_DAYS",
    "DETHRONING_LANGUAGES", "SUPERLATIVE_PATTERNS", "LeaderClaim",
    "DethroningVector", "DethroningVerdict", "detect_superlative_claims",
    "extract_leader_value", "build_dethroning_vectors", "detect_supersession",
    "adjudicate_dethroning", "run_b11_dethroning_filter",
]

# Two overlapping bands: 30 days (zero-lag) and 90 days (no gap in coverage).
RECENCY_WINDOWS_DAYS: tuple[int, ...] = (30, 90)
MIN_DETHRONING_VECTORS = 8
MAX_CHECK_AGE_DAYS = 30

DETHRONING_LANGUAGES: tuple[str, ...] = (
    "en", "ru", "zh", "es", "de", "ko", "ja", "fr",
)

# Superlative claim inventory. Deliberately phrase-based: a bare "best" in
# "best practice" is not a leader claim, but "best model" is.
SUPERLATIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(rx, re.I))
    for kind, rx in (
        ("world_record", r"\b(?:world|all[- ]time|guinness)\s+(?:record|best)\b|\bworld\s*record\b"),
        ("record_holder", r"\b(?:record\s*holder|reigning\s+champion|title\s*holder|unbeaten)\b"),
        ("number_one", r"#\s*1\b|\bnumber\s+one\b|\branked\s+(?:first|#?1)\b|\btop[- ]ranked\b"),
        ("leading_model", r"\b(?:leading|frontier|top|best|sota|state[- ]of[- ]the[- ]art)\s+"
                          r"(?:ai\s+)?(?:model|llm|system|provider|vendor)\b"),
        ("best_model", r"\b(?:best|fastest|cheapest|strongest|largest|highest|most\s+accurate)\s+"
                       r"(?:model|llm|engine|chip|exchange|broker|record|lift|result|score)\b"),
        ("current_leader", r"\b(?:current|reigning|undisputed)\s+(?:leader|champion|record\s*holder)\b"),
        ("consensus", r"\b(?:standard\s+consensus|widely\s+accepted|universally\s+accepted)\b"),
        ("sota", r"\bSOTA\b|\bcurrent\s+SOTA\b"),
        ("new_record", r"\b(?:new|fresh)\s+(?:world\s+)?record\b"),
        ("ru_record", r"\b(?:мировой\s+рекорд|новый\s+рекорд|лучшая\s+модель)\b"),
        ("zh_record", r"(?:世界纪录|新纪录|最新排名|最佳模型|被打破)"),
        ("ja_record", r"(?:世界記録|新記録|最高性能)"),
        ("ko_record", r"(?:세계기록|신기록|최고\s*성능)"),
        ("de_record", r"\b(?:Weltrekord|neuer\s+Rekord|beste\s+Modell)\b"),
        ("es_record", r"\b(?:récord\s+mundial|nuevo\s+récord|mejor\s+modelo)\b"),
    )
)

# Measured-value extraction (kg, bps, ms, %, tokens/s, points, USD...).
_VALUE_UNIT_RE = re.compile(
    r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)\s*"
    r"(kg|kilograms?|lbs?|pounds?|bps|bp|ms|seconds?|s\b|%|percent|"
    r"tokens?/s|tok/s|points?|usd|eur|bn|million|m\b)",
    re.I,
)
_METRIC_WORDS = (
    "deadlift", "squat", "bench", "lift", "record", "benchmark", "score",
    "latency", "throughput", "price", "cost", "accuracy", "speed", "context",
    "рекорд", "жим", "тяга", "纪录", "記錄", "기록", "Rekord", "récord",
)

# Supersession / upset vocabulary. A hit is necessary but not sufficient:
# adjudication also requires a challenger name or a higher measured value.
_SUPERSESSION_PHRASES: dict[str, tuple[str, ...]] = {
    "en": ("surpassed by", "surpassed", "beat", "beaten", "defeated by", "defeated",
           "outperformed", "new record", "record broken", "broke the record",
           "dethroned", "superseded", "eclipsed", "toppled", "no longer holds"),
    "ru": ("побил", "побит", "превзошёл", "превзойден", "новый рекорд", "сверг", "победил"),
    "zh": ("被打破", "刷新纪录", "超越", "新纪录", "被超越", "击败"),
    "es": ("superó a", "superó", "nuevo récord", "batido", "destronó", "derrotó", "superado"),
    "de": ("geschlagen", "neuer Rekord", "übertroffen", "gebrochen", "entthront"),
    "ko": ("신기록", "경신", "제쳤다", "깨졌다", "앞섰다"),
    "ja": ("新記録", "更新", "破った", "上回った", "抜いた"),
    "fr": ("battu", "nouveau record", "dépassé", "surpassé", "détrôné"),
}
_COMPILED_SUPERSESSION: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (lang, phrase, re.compile(r"\s+".join(
        re.escape(w) for w in normalise_for_match(phrase).split()), re.I))
    for lang, phrases in _SUPERSESSION_PHRASES.items()
    for phrase in phrases
)

# Adversarial vector templates per language. {metric}/{leader} are substituted;
# {since}/{until} are real ISO dates. The English vector is the literal
# mandated OR-expression so its wording is auditable.
_VECTOR_TEMPLATES: dict[str, str] = {
    "en": '"{metric} surpassed by" OR "beat {leader}" OR "new record" OR "defeated by" OR "outperformed {leader}" after:{since} before:{until}',
    "ru": '"{metric} побит" OR "побил {leader}" OR "новый рекорд" OR "превзошёл {leader}" после:{since} до:{until}',
    "zh": '"{metric} 被打破" OR "击败 {leader}" OR "新纪录" OR "超越 {leader}" {since}..{until}',
    "es": '"{metric} superado" OR "superó a {leader}" OR "nuevo récord" OR "destronó a {leader}" after:{since} before:{until}',
    "de": '"{metric} übertroffen" OR "{leader} geschlagen" OR "neuer Rekord" nach:{since} vor:{until}',
    "ko": '"{metric} 신기록" OR "{leader} 제쳤다" OR "경신" OR "신기록 달성" {since}..{until}',
    "ja": '"{metric} 更新" OR "{leader} を破った" OR "新記録" OR "上回った" {since}..{until}',
    "fr": '"{metric} surpassé" OR "battu {leader}" OR "nouveau record" après:{since} avant:{until}',
}

# Case-sensitive on purpose: a capitalised name is the disambiguator. A
# case-insensitive `[A-Z]` would match "the" / "a" and fabricate challengers.
_NAME = r"([A-ZА-ЯЁ][\w'’.\-]+(?:\s+[A-ZА-ЯЁ][\w'’.\-]+){0,2})"
_CHALLENGER_RE = re.compile(
    r"\b(?:by|from|set\s+by|lifted\s+by|achieved\s+by|por|par|von|de)\s+" + _NAME
)
_CHALLENGER_VERB_RE = re.compile(
    r"\b(?:beat|beats|defeated|surpassed|outperformed|dethroned|toppled|"
    r"superó|побил|превзошёл|击败|超越|besiegte|geschlagen)\s+" + _NAME
)
_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|unratified|did\s+not|was\s+not|has\s+not|"
    r"is\s+not|remains\s+unbroken|не\s+был|没有被|未|아직|いまだ)\b\s*"
    r"(?:new\s+|world\s+|a\s+|the\s+){0,3}$",
    re.I,
)


@dataclass
class LeaderClaim:
    """One detected superlative claim that must be dethroning-verified."""
    kind: str
    text: str
    position: int
    leader: str = ""
    metric: str = ""
    value: float | None = None
    unit: str = ""


@dataclass
class DethroningVector:
    """One adversarial, recency-anchored search vector."""
    vector_id: str
    lang: str
    query: str
    window_days: int
    since: str
    until: str
    purpose: str = "disconfirm_leader"


@dataclass
class DethroningVerdict:
    """Mechanical result of O_dethrone for one (leader, metric) pair."""
    leader: str
    metric: str
    status: str  # dethroned | intact | unverified | insufficient_evidence
    certifiable: bool
    challenger: str = ""
    challenger_value: float | None = None
    leader_value: float | None = None
    evidence_ids: list[str] = field(default_factory=list)
    fresh_checks: int = 0
    vectors_run: int = 0
    window_days: int = 90
    checked_at: str = ""
    supersession_phrases: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_date(value: Any) -> dt.date | None:
    """Honest date coercion: unknown values are never guessed as 'today'."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        s = value.strip()[:10]
        try:
            return dt.date.fromisoformat(s)
        except ValueError:
            return None
    return None


def detect_superlative_claims(text: Any) -> list[LeaderClaim]:
    """Return every perishable superlative claim in ``text`` (deduped by kind)."""
    raw = text if isinstance(text, str) else str(text or "")
    if not raw:
        return []
    # Mask Markdown ATX section prefixes (`## 1. Heading`) with equal-length
    # spaces so `## 1.` does not false-trigger `#\s*1\b` (`number_one`) while
    # preserving exact character positions for genuine `#1` claims.
    scan_text = re.sub(r"(?m)^#{1,6}[ \t]+", lambda m: " " * len(m.group(0)), raw)
    claims: list[LeaderClaim] = []
    seen: set[str] = set()
    for kind, rx in SUPERLATIVE_PATTERNS:
        m = rx.search(scan_text)
        if not m or kind in seen:
            continue
        seen.add(kind)
        claims.append(LeaderClaim(kind=kind, text=m.group(0), position=m.start()))
    return claims


def extract_leader_value(text: Any) -> dict[str, Any]:
    """Extract (value, unit, metric) for a leader claim from a sentence.

    Returns the *largest* measured value with a declared unit, because a
    superlative sentence about a record normally states the record number.
    Unknown values are ``None``, never a fabricated default.
    """
    raw = text if isinstance(text, str) else str(text or "")
    values: list[tuple[float, str]] = []
    for m in _VALUE_UNIT_RE.finditer(raw):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        values.append((v, m.group(2).lower()))
    low = raw.lower()
    metric = next((w for w in _METRIC_WORDS if w.lower() in low), "record")
    if values:
        value, unit = max(values, key=lambda t: t[0])
        return {"value": value, "unit": unit, "metric": metric}
    return {"value": None, "unit": "", "metric": metric}


def build_dethroning_vectors(
    leader: str,
    metric: str,
    *,
    as_of: dt.date | str | None = None,
    windows: tuple[int, ...] | list[int] = RECENCY_WINDOWS_DAYS,
    languages: tuple[str, ...] | list[str] = DETHRONING_LANGUAGES,
) -> list[DethroningVector]:
    """Spawn adversarial, recency-anchored vectors intended to BREAK ``leader``.

    Dates are computed from ``as_of`` (default: today). No calendar year is
    hardcoded, so a study run in 2027 cannot accidentally re-search 2026.
    """
    today = _as_date(as_of) or dt.date.today()
    leader_s = str(leader or "the current leader").strip()[:80]
    metric_s = str(metric or "record").strip()[:80]
    out: list[DethroningVector] = []
    for days in windows:
        days_i = int(days)
        if days_i <= 0:
            continue
        since = (today - dt.timedelta(days=days_i)).isoformat()
        until = today.isoformat()
        for lang in languages:
            tpl = _VECTOR_TEMPLATES.get(lang, _VECTOR_TEMPLATES["en"])
            try:
                query = tpl.format(
                    metric=metric_s, leader=leader_s, since=since, until=until,
                )
            except (KeyError, IndexError, ValueError):
                continue
            out.append(DethroningVector(
                vector_id=f"DTH-{lang.upper()}-D{days_i}", lang=str(lang),
                query=query, window_days=days_i, since=since, until=until,
            ))
    return out


def detect_supersession(text: Any) -> dict[str, Any]:
    """Find upset language, a challenger name and any higher measured value."""
    raw = normalise_for_match(text)
    phrases: list[str] = []
    langs: set[str] = set()
    if raw:
        for lang, phrase, rx in _COMPILED_SUPERSESSION:
            m = rx.search(raw)
            if not m:
                continue
            # "no new record was ratified" is a NEGATED upset. Accepting it
            # would falsely dethrone a leader on a sentence that says the
            # opposite, and would also pollute the intact-check evidence.
            if _NEGATION_RE.search(raw[max(0, m.start() - 28):m.start()]):
                continue
            phrases.append(phrase)
            langs.add(lang)
    original = text if isinstance(text, str) else str(text or "")
    ch_match = _CHALLENGER_RE.search(original) or _CHALLENGER_VERB_RE.search(original)
    challenger = (ch_match.group(1).strip() if ch_match else "")
    nums: list[float] = []
    for m in _VALUE_UNIT_RE.finditer(original):
        try:
            nums.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return {
        "phrases": sorted(set(phrases)),
        "languages": sorted(langs),
        "has_upset_language": bool(phrases),
        "challenger": challenger,
        "values": sorted(set(nums), reverse=True),
        "max_value": max(nums) if nums else None,
    }


def adjudicate_dethroning(
    leader: str,
    metric: str,
    evidence: list[dict[str, Any]] | None = None,
    *,
    leader_value: float | None = None,
    as_of: dt.date | str | None = None,
    window_days: int = 90,
    vectors_run: int = 0,
    min_vectors: int = MIN_DETHRONING_VECTORS,
) -> DethroningVerdict:
    """Mechanically decide whether ``leader`` has been superseded.

    ``evidence`` rows: ``{"text": str, "date": ISO|None, "evidence_id": str}``.
    A row counts as a *fresh check* only when its date lies inside
    ``[as_of - window_days, as_of]``; unknown dates never count (fail-closed).

    Status semantics:
      * ``dethroned`` — a fresh upset phrase plus challenger / higher value;
      * ``intact`` — enough fresh dethroning vectors found no upset;
      * ``unverified`` / ``insufficient_evidence`` — NOT certifiable.
    """
    today = _as_date(as_of) or dt.date.today()
    since = today - dt.timedelta(days=int(window_days))
    v = DethroningVerdict(
        leader=str(leader or ""), metric=str(metric or ""), status="insufficient_evidence",
        certifiable=False, leader_value=leader_value, vectors_run=int(vectors_run),
        window_days=int(window_days), checked_at=today.isoformat(),
    )
    fresh_checks = 0
    for row in evidence or []:
        if not isinstance(row, dict):
            continue
        when = _as_date(row.get("date"))
        fresh = bool(when and since <= when <= today)
        sig = detect_supersession(row.get("text"))
        eid = str(row.get("evidence_id") or row.get("id") or "").strip()
        if not fresh:
            # A stale upset can still be recorded, but cannot dethrone or
            # certify: zero-lag means an old article proves nothing about now.
            continue
        fresh_checks += 1
        if eid and eid not in v.evidence_ids:
            v.evidence_ids.append(eid)
        if not sig["has_upset_language"]:
            continue
        higher = (
            sig["max_value"] is not None
            and leader_value is not None
            and sig["max_value"] > float(leader_value)
        )
        named = bool(sig["challenger"]) and sig["challenger"].lower() not in str(leader).lower()
        if higher or named:
            v.status = "dethroned"
            v.challenger = sig["challenger"]
            v.challenger_value = sig["max_value"]
            v.supersession_phrases = sig["phrases"]
            break
        v.supersession_phrases = sorted(set(v.supersession_phrases + sig["phrases"]))

    v.fresh_checks = fresh_checks
    if v.status == "dethroned":
        v.certifiable = False
        return v
    if fresh_checks > 0 and v.vectors_run >= int(min_vectors):
        v.status = "intact"
        v.certifiable = True
    elif (evidence or []) and fresh_checks > 0:
        v.status = "unverified"
    else:
        v.status = "unverified" if evidence else "insufficient_evidence"
    return v


def run_b11_dethroning_filter(
    prose_text: str,
    manifest: dict[str, Any],
    verified_evidence_ids: set[str] | None = None,
    *,
    as_of: dt.date | str | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Rule B11: no superlative claim without a fresh, verified O_dethrone pass.

    Returns ``(failures, warnings, diagnostics)``. Every failure is hard; a
    missing or stale check is never downgraded to a warning (Rule B0).
    """
    today = _as_date(as_of) or dt.date.today()
    claims = detect_superlative_claims(prose_text)
    diag: dict[str, Any] = {
        "claims_detected": len(claims),
        "claim_kinds": [c.kind for c in claims],
        "records": 0,
        "certifiable": not claims,
        "checked_at": today.isoformat(),
    }
    if not claims:
        return [], [], diag

    records = manifest.get("dethroning", []) if isinstance(manifest, dict) else []
    if not isinstance(records, list):
        records = []
    diag["records"] = len(records)
    failures: list[str] = []
    warnings: list[str] = []
    if not records:
        failures.append(
            "B11 (Premature Search Termination): report asserts a superlative "
            f"({', '.join(diag['claim_kinds'])}) but manifest declares no "
            "`dethroning` record. Run O_dethrone: spawn 30/90-day adversarial "
            "vectors, snapshot the results, and verify `L` was not superseded."
        )
        return failures, warnings, diag

    for i, rec in enumerate(records, 1):
        if not isinstance(rec, dict):
            failures.append(f"B11 (Malformed Dethroning Record #{i}): expected a JSON object")
            continue
        status = str(rec.get("status", "")).strip().lower()
        rid = f"#{i} {rec.get('leader', '?')}/{rec.get('metric', '?')}"
        if status == "dethroned":
            challenger = str(rec.get("superseded_by") or rec.get("challenger") or "").strip()
            if not challenger:
                failures.append(
                    f"B11 (Leader Superseded) {rid}: O_dethrone found an upset, but the "
                    "record declares no `superseded_by` challenger. The report must name "
                    "the new leader before any superlative can be certified."
                )
            elif challenger.lower() not in str(prose_text).lower():
                failures.append(
                    f"B11 (Leader Superseded) {rid}: challenger {challenger!r} is not "
                    "named in the report prose; the stale leader is still being presented "
                    "as current."
                )
            else:
                warnings.append(
                    f"W_B11_UPSET: {rid} was dethroned by {challenger}; the EAD section "
                    "must record this as trench ground-truth."
                )
            continue
        if status != "intact":
            failures.append(
                f"B11 (Unverified Superlative) {rid}: status={status!r} is not "
                "`intact`; only a fully executed dethroning pass may certify a "
                "world record / leading model claim."
            )
            continue
        vectors = rec.get("vectors_run", rec.get("vectors", 0))
        try:
            vectors_i = int(vectors)
        except (TypeError, ValueError):
            vectors_i = 0
        if vectors_i < MIN_DETHRONING_VECTORS:
            failures.append(
                f"B11 (Insufficient Dethroning Coverage) {rid}: {vectors_i} vectors run, "
                f"need >= {MIN_DETHRONING_VECTORS} (8 languages x 30/90-day bands)."
            )
        window = rec.get("window_days", 0)
        try:
            window_i = int(window)
        except (TypeError, ValueError):
            window_i = 0
        if window_i not in RECENCY_WINDOWS_DAYS:
            failures.append(
                f"B11 (Zero-Lag Window Violation) {rid}: window_days={window!r}; "
                f"must be one of {RECENCY_WINDOWS_DAYS} (most recent 30-90 days)."
            )
        checked = _as_date(rec.get("checked_at"))
        if checked is None or (today - checked).days > MAX_CHECK_AGE_DAYS:
            failures.append(
                f"B11 (Stale Dethroning Check) {rid}: checked_at={rec.get('checked_at')!r} "
                f"is missing or older than {MAX_CHECK_AGE_DAYS} days of {today.isoformat()}."
            )
        if not rec.get("recency_verified"):
            failures.append(
                f"B11 (Recency Unverified) {rid}: `recency_verified` must be true and "
                "backed by dated snapshots inside the declared window."
            )
        eids = [str(x) for x in (rec.get("evidence_ids") or [])]
        if not eids:
            failures.append(
                f"B11 (No Dethroning Evidence) {rid}: `evidence_ids` is empty; a "
                "dethroning pass with zero snapshot-verified results cannot certify."
            )
        elif verified_evidence_ids is not None:
            missing = [e for e in eids if e not in verified_evidence_ids]
            if missing:
                failures.append(
                    f"B11 (Unverified Dethroning Evidence) {rid}: {missing} are not "
                    "verbatim snapshot-verified evidence IDs."
                )

    if not failures:
        diag["certifiable"] = True
    if len(records) < len(set(diag["claim_kinds"])):
        warnings.append(
            "W_B11_PARTIAL_COVERAGE: fewer dethroning records than distinct "
            "superlative claim kinds; confirm every leader/metric pair was checked."
        )
    return failures, warnings, diag


def _selftest() -> int:
    claims = detect_superlative_claims(
        "Hafthor Bjornsson holds the deadlift world record of 510 kg and is the "
        "current leader on the all-time list."
    )
    kinds = {c.kind for c in claims}
    assert "world_record" in kinds and "current_leader" in kinds, kinds
    assert not detect_superlative_claims("A best practice is to log the effective spread.")
    info = extract_leader_value("The world record was 510 kg in 2025 and 511 kg today.")
    assert info["value"] == 511.0 and info["unit"] == "kg"

    vectors = build_dethroning_vectors(
        "Hafthor Bjornsson", "deadlift world record",
        as_of=dt.date(2026, 11, 6),
    )
    assert len(vectors) >= 16
    assert any("surpassed by" in v.query and "beat Hafthor" in v.query for v in vectors)
    assert all("2026-11-06" in v.query or "2026-11-06" == v.until for v in vectors)
    assert any(v.window_days == 30 for v in vectors) and any(v.window_days == 90 for v in vectors)
    assert any(v.since == "2026-10-07" for v in vectors)  # 30-day band
    assert any(v.since == "2026-08-08" for v in vectors)  # 90-day band

    upset = {
        "text": "Raúl Flores beat Hafthor Bjornsson with a new record of 511 kg in Birmingham.",
        "date": "2026-11-05", "evidence_id": "E007",
    }
    v = adjudicate_dethroning(
        "Hafthor Bjornsson", "deadlift world record", [upset],
        leader_value=510.0, as_of=dt.date(2026, 11, 6), vectors_run=16,
    )
    assert v.status == "dethroned" and v.challenger_value == 511.0 and not v.certifiable
    assert not detect_supersession("No new record was ratified by the federation.")["has_upset_language"]
    assert detect_supersession("The 511 kg lift was set by Raúl Flores, surpassing 510 kg.")["challenger"]

    clean = {"text": "The federation published the 2026 entry list; no new record was ratified.",
             "date": "2026-11-04", "evidence_id": "E008"}
    intact = adjudicate_dethroning(
        "Hafthor Bjornsson", "deadlift world record", [clean],
        leader_value=510.0, as_of=dt.date(2026, 11, 6), vectors_run=16,
    )
    assert intact.status == "intact" and intact.certifiable
    stale = adjudicate_dethroning("L", "M", [dict(clean, date="2025-01-01")],
                                  as_of=dt.date(2026, 11, 6), vectors_run=16)
    assert stale.status == "unverified" and not stale.certifiable
    assert adjudicate_dethroning("L", "M", []).status == "insufficient_evidence"

    manifest = {"dethroning": [{
        "leader": "Hafthor Bjornsson", "metric": "deadlift world record",
        "status": "intact", "vectors_run": 16, "window_days": 30,
        "checked_at": "2026-11-06", "recency_verified": True,
        "evidence_ids": ["E008"],
    }]}
    fails, _, diag = run_b11_dethroning_filter(
        "The deadlift world record is 510 kg.", manifest,
        verified_evidence_ids={"E008"}, as_of=dt.date(2026, 11, 6),
    )
    assert not fails and diag["certifiable"], fails
    bad, _, _ = run_b11_dethroning_filter(
        "The deadlift world record is 510 kg.", {}, as_of=dt.date(2026, 11, 6))
    assert any("B11 (Premature Search Termination)" in f for f in bad)

    print("[SELFTEST PASS] dethrone v12.0 (O_dethrone / 30-90d / B11 fail-closed) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
