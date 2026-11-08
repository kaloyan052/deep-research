#!/usr/bin/env python3
"""Deep Research Engine v14.1 — Desk Memory & Graveyard Pre-Flight Scanner.

Rule B13. Rules are declared as (a) optional regex patterns and (b) concept
groups: a hit requires >= min_groups distinct concept groups inside the SAME
sentence/paragraph. Refutation must be local to that same unit (never global),
per AGENTS.md v10 "Disclaimers are local". Text is NFKC-normalised, stripped of
zero-width characters and folded against Latin homoglyphs before matching.

Stdlib only. Windows UTF-8-safe.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

__all__ = ["DESK_KNOWLEDGE_PATHS", "GRAVEYARD_RULES",
           "scan_text_against_desk_graveyard", "load_desk_knowledge_text"]

_HERE = Path(__file__).resolve()
DESK_KNOWLEDGE_PATHS = [
    _HERE.parents[3] / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
    _HERE.parents[2] / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
    _HERE.parent / "known_traps.json",
    Path.home() / "Desktop" / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
]

_ACK = [r"\b(?:killed|refuted|dead|unviable|rejected|forensic\w*\s+killed|"
        r"убит\w*|отхвърлен\w*|неработещ\w*|елиминиран\w*|"
        r"не\s+препоръчва\w*|spread\s+(?:erases|drag))\b"]
_DENIAL = [r"\b(?:does\s+not|do\s+not|never|no\s+such|not\s+discussed|"
           r"fabricated|hallucinated|banned|забранено|не\s+съществува|"
           r"не\s+споменава|няма\s+так\w+|измислен)\b"]

GRAVEYARD_RULES: list[dict[str, Any]] = [
    {"id": "GRAVEYARD_GOLD_INTRADAY",
     "name": "Gold / XAUUSD intraday ORB, Asian/London/LBMA breakouts",
     "description": "Killed: Asian Sweep t_2x=-26.06, London ORB net t=+0.32, 2x cost t=-3.92.",
     "concept_groups": [
         ["gold", "xauusd", "xau/usd", "злат", "lbma", "спот злато"],
         ["london", "asian", "орб", "orb", "opening range", "breakout", "sweep",
          "fixing", "фиксинг", "лондон", "азиат", "пробив", "intraday"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_CRUDE_OIL_INTRADAY",
     "name": "WTI / Crude Oil NY open, pit open, displacement, EIA drift",
     "description": "Killed: Crude NY Displacement t_2x=-2.31; $0.04 spread eliminates the edge.",
     "concept_groups": [
         ["wti", "crude", "usoil", "oil", "cl", "петрол", "нефт"],
         ["ny open", "pit open", "displacement", "eia", "orb", "breakout",
          "отваряне", "ню йорк", "пробив", "intraday"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_EUROPEAN_CASH_OPEN",
     "name": "European cash-open / ORB breakouts (DAX, UK100, EU50, EURUSD, German index)",
     "description": "Killed: HV battery A1-A7, honest clocks; 1.6+ pts spread drag erases net edge.",
     "concept_groups": [
         ["dax", "dax40", "ger40", "de40", "de30", "uk100", "ftse", "eu50",
          "sx5e", "stoxx", "eurusd", "german index", "frankfurt", "европейск",
          "германск", "dax40/uk100"],
         ["cash open", "кеш оупън", "08:00", "09:00", "opening range", "orb", "пробив", "отварянето"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_ORB30_MULTI_ASSET",
     "name": "ORB30 / opening-range breakouts on NAS, SPX, US30, US2000, gold",
     "description": "Killed: HV battery A1-A7 (2026-10-06); all ORB30 variants FAIL.",
     "concept_groups": [
         ["orb30", "opening range 30", "30-minute opening range", "orb"],
         ["nas", "nas100", "spx", "spx500", "us30", "us2000", "gold", "dax"],
         ["breakout", "range", "sweep"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_MES_MNQ_PAIRS",
     "name": "MES/MNQ intraday pairs mean reversion",
     "description": "Killed: ADF p=0.092, half-life 38 days, t_2x=-5.96.",
     "concept_groups": [
         ["mes", "mnq", "es", "nq", "micro futures"],
         ["pair", "pairs", "mean reversion", "spread trading", "cointegrat",
          "двойки", "арбитраж"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_OVERNIGHT_CFD_SWAP",
     "name": "Overnight / swing holding on CFDs (swap & financing drag)",
     "description": "Killed: master directive §2.C.4 — CFD swap/financing drag kills holds.",
     "concept_groups": [
         ["overnight", "swing", "multi-day", "hold", "нощ", "суинг"],
         ["cfd", "swap", "financing", "carry", "rollover", "финансиране"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_TRAILING_STOP_PLACEBO",
     "name": "Trailing stop (TRAIL01), EMA5, break-even placebo variants",
     "description": "Killed: prereg 2026-10-07; Pillar 1 stays 1:1 with the audit.",
     "concept_groups": [
         ["trail01", "trailing stop", "плаващ стоп", "трейлинг", "breakeven stop", "break-even stop", "ema5 stop"],
         ["pillar 1", "pillar1", "3-bar displacement", "three-bar displacement", "placebo"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_DISPLACEMENT_TRANSPLANT",
     "name": "Displacement transplanted to US30/US2000/ES/DAX/NQ London/NQ 5m",
     "description": "Killed: master §2.A/§2.C.5 — ES t=-0.66, US30 -0.73, DAX +0.15, NQ London -3.41, NQ 5m net +1.72 < Bonferroni 2.58.",
     "concept_groups": [
         ["3-bar displacement", "three-bar displacement", "pillar 1 displacement", "pillar1 displacement", "transplanted displacement"],
         ["us30", "us2000", "es", "dax", "nq london", "nq 5m", "5m timeframe", "5-minute timeframe", "london session"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_SINGLE_STOCK_CFDS",
     "name": "FTMO Single-Stock CFDs (PILLAR1_XFTMO01)",
     "description": "Killed: 46 stocks, 4,548 trades, gross t=+0.36, median spread 0.093R, net t=-6.53.",
     "concept_groups": [
         ["single-stock cfd", "stock cfd", "equity cfd", "акции cfd", "xftmo01", "pillar1_xftmo01"],
         ["ftmo", "prop firm", "brightfunded", "fintokei", "retail prop", "проп фирма"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_REDDIT_LEADERBOARD",
     "name": "Reddit leaderboard scraping + LLM cut-limits",
     "description": "Killed: survivorship bias, overfitted ex-post cut-limits, FTMO ban on public EAs.",
     "concept_groups": [
         ["reddit leaderboard", "leaderboard scraping", "scrape leaderboard"],
         ["llm", "cut-limit", "cut limit", "public ea", "prop firm", "ftmo"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_REVELIO_10Y",
     "name": "Revelio 10-year linear regression channel",
     "description": "Killed: no stop-loss, 20-40% drawdowns, 4-12 month holds burn CFD swaps.",
     "concept_groups": [
         ["revelio"],
         ["regression channel", "linear regression channel", "10-year regression", "10y regression", "linear channel"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_PILLAR2_OUT6",
     "name": "Pillar 2 OUT6_10D / RUT10 / OUT6-21D CME micro-FX reversal",
     "description": "Killed: E7 de-mean bias, RAW t < 2.0, CFD overnight swap drag.",
     "concept_groups": [
         ["out6_10d", "out6-10d", "out6", "out6-21d", "rut10"],
         ["micro-fx", "10-day reversal", "reversal", "cme", "overnight"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_INTRADAY_EXHAUSTION",
     "name": "New intraday edge on the exhausted free-data universe (P1-P102)",
     "description": "Killed: 102 intraday programs + 10-test HV battery; zero passed. New edge needs new data or a new instrument class.",
     "concept_groups": [
         ["p1-p102", "102 intraday", "intraday research program", "free-data universe"],
         ["new edge", "new intraday", "another strategy", "novel setup"],
     ], "min_groups": 2, "refutation_patterns": _ACK},

    {"id": "GRAVEYARD_NONCANONICAL_CLOCKS",
     "name": "Research scripts with mis-localized clocks",
     "description": "Advisory: 17 scripts used local clocks; all kills re-confirmed with honest clocks 2026-10-06. Use lab_utc.load_canonical_utc.",
     "concept_groups": [
         ["local clock", "server clock", "mis-localized", "timezone", "夏令时"],
         ["backtest", "session", "bar", "intraday"],
     ], "min_groups": 2, "refutation_patterns": _ACK + ["canonical utc", "lab_utc"]},

    {"id": "GRAVEYARD_SYNTHETIC_REGULATORY_CITATIONS",
     "name": "Synthetic regulatory / central-bank citations about prop firms or R-multiples",
     "description": "Hard ban: BIS/CFTC/SEC/IMF/Fed/ECB never discuss prop firms, FTMO or R-multiples.",
     "scope": "document",
     "concept_groups": [
         ["bis", "cftc", "sec", "imf", "federal reserve", "ecb", "central bank",
          "банк за международни разплащания"],
         ["prop firm", "ftmo", "brightfunded", "fintokei", "r-multiple",
          "r-multiples", "r multiples", "проп фирм", "р-мултипл"],
     ], "min_groups": 2, "refutation_patterns": _DENIAL},
]


_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad]")
_HOMOGLYPHS = str.maketrans({
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
    "\u0455": "s", "\u04bb": "h", "\u0391": "A", "\u0395": "E",
    "\u039f": "O", "\u03a1": "P", "\u039a": "K",
})


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text))
    t = _ZERO_WIDTH.sub("", t)
    t = (t.replace("\u2212", "-").replace("\u2013", "-")
          .replace("\u2014", "-").replace("\u00a0", " "))
    return t.casefold()


def _latin_fold(text: str) -> str:
    return _fold(text).translate(_HOMOGLYPHS)


def _units(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        out.extend(s for s in re.split(r"(?<=[.!?;])\s+|\n+", para) if s.strip())
    return out or [text]


def _alias_in(unit: str, aliases: list[str]) -> bool:
    for a in aliases:
        a = a.casefold()
        pat = (r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])"
               if re.fullmatch(r"[a-z0-9]+", a) else re.escape(a))
        if re.search(pat, unit):
            return True
    return False


def load_desk_knowledge_text() -> str:
    combined = []
    for p in DESK_KNOWLEDGE_PATHS:
        if p.exists():
            try:
                combined.append(p.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:                       # never silent
                combined.append(f"[DESK KNOWLEDGE READ ERROR: {p}: {e}]")
    return "\n\n".join(combined)


def scan_text_against_desk_graveyard(text: str) -> list[dict[str, Any]]:
    """Return violations for killed strategies asserted WITHOUT a local refutation.

    Matching is performed on the original folded text AND a Latin-homoglyph-folded
    variant of the SAME unit, so zero-width/homoglyph obfuscation cannot hide a
    killed idea. Refutation must appear in that same unit (never in an unrelated
    appendix). Document-scoped rules (synthetic citations) match across the whole
    document and can only be disarmed by an explicit denial.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    original = _fold(text)
    violations: list[dict[str, Any]] = []

    for rule in GRAVEYARD_RULES:
        scope = rule.get("scope", "local")
        acks = rule.get("refutation_patterns", [])
        patterns = rule.get("patterns", [])
        groups = rule.get("concept_groups", [])
        min_groups = rule.get("min_groups", 2)
        hit: str | None = None

        if scope == "document":
            pairs = [(original, _latin_fold(original))]
        else:
            pairs = [(u, _latin_fold(u)) for u in _units(original)]

        for orig_unit, latin_unit in pairs:
            matched = False
            for variant in (orig_unit, latin_unit):
                if any(re.search(p, variant, re.I | re.S) for p in patterns):
                    matched = True
                    break
                if groups and sum(1 for g in groups if _alias_in(variant, g)) >= min_groups:
                    matched = True
                    break
            if not matched:
                continue
            if any(re.search(a, orig_unit, re.I) or re.search(a, latin_unit, re.I)
                   for a in acks):
                continue
            hit = orig_unit.strip()[:180]
            break

        if hit:
            violations.append({
                "rule_id": rule["id"],
                "name": rule["name"],
                "description": rule["description"],
                "matched_snippet": hit,
            })
    return violations
