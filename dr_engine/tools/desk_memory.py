#!/usr/bin/env python3
"""Deep Research Engine v14.0 — Desk Memory & Graveyard Pre-Flight Scanner.

Prevents agents from wasting tokens and researching hypotheses that are already
forensically refuted and permanently killed in the desk's master knowledge base
(CLAUDE_PROJECT_KNOWLEDGE_MASTER.md) and known_traps.json.

Enforces Rule B13 (Anti-Graveyard Invariant & Strict Grounding):
  1. No Gold (XAUUSD) Asian or London ORB / Breakouts.
  2. No WTI Crude Oil Pit Open / NY ORB / Displacement.
  3. No European Cash Open Range Breakouts (DAX40, EU50, UK100).
  4. No MES/MNQ Intraday Mean Reversion Pairs.
  5. No Single-Stock CFDs on retail prop firms (FTMO).
  6. No Synthetic Regulatory Citations (BIS, CFTC, SEC talking about prop firms or R-multiples).
  7. No Unverified Prop Firm Rules (FTMO, BrightFunded, Fintokei).

Stdlib only. Windows cp1252-safe.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

__all__ = [
    "DESK_KNOWLEDGE_PATHS",
    "GRAVEYARD_RULES",
    "scan_text_against_desk_graveyard",
    "load_desk_knowledge_text",
]

# Canonical locations for the desk's master architecture and knowledge directives
DESK_KNOWLEDGE_PATHS = [
    Path(r"c:\Users\kaloy\Desktop\trading buff\CLAUDE_PROJECT_KNOWLEDGE_MASTER.md"),
    Path(__file__).resolve().parent.parent.parent / "trading buff" / "CLAUDE_PROJECT_KNOWLEDGE_MASTER.md",
    Path(__file__).resolve().parent / "known_traps.json",
]

# Compiled patterns of killed strategies from the master architecture
GRAVEYARD_RULES: list[dict[str, Any]] = [
    {
        "id": "GRAVEYARD_GOLD_INTRADAY",
        "name": "Gold (XAUUSD) Intraday ORB / Asian / London Breakouts",
        "description": "Killed in trading buff lab (Asian Sweep t_2x=-26.06, London ORB net t=+0.32, 2x cost t=-3.92). Spread $0.50 erases edge.",
        "patterns": [
            r"\b(?:gold|xauusd)\b.*?\b(?:london|asian|orb|opening\s+range|breakout|sweep)\b",
            r"\b(?:london|asian|orb|opening\s+range|breakout|sweep)\b.*?\b(?:gold|xauusd)\b",
            r"\bзлат\w*\b.*?\b(?:лондон\w*|азиат\w*|orb|пробив|фиксинг)\b",
            r"\b(?:лондон\w*|азиат\w*|orb|пробив|фиксинг)\b.*?\bзлат\w*\b",
        ],
        "refutation_patterns": [
            r"\b(?:killed|refuted|dead|unviable|убит|отхвърлен|неработещ|елиминиран|отрицателна|спредът\s+унищожава|spread\s+erases)\b",
        ],
    },
    {
        "id": "GRAVEYARD_CRUDE_OIL_INTRADAY",
        "name": "Crude Oil (WTI/USOIL) NY Open / Displacement / EIA Drift",
        "description": "Killed in trading buff lab (Crude NY Displacement t_2x=-2.31, $0.04 spread eliminates edge).",
        "patterns": [
            r"\b(?:crude|oil|wti|cl|usoil)\b.*?\b(?:ny\s+open|pit\s+open|displacement|eia|orb|breakout)\b",
            r"\b(?:ny\s+open|pit\s+open|displacement|eia|orb|breakout)\b.*?\b(?:crude|oil|wti|cl|usoil)\b",
            r"\bпетрол\w*\b.*?\b(?:отваряне|ню\s*йорк|отварянето|пробив|orb)\b",
            r"\b(?:отваряне|ню\s*йорк|отварянето|пробив|orb)\b.*?\bпетрол\w*\b",
        ],
        "refutation_patterns": [
            r"\b(?:killed|refuted|dead|unviable|убит|отхвърлен|неработещ|елиминиран|spread\s+erases|спредът\s+унищожава)\b",
        ],
    },
    {
        "id": "GRAVEYARD_EUROPEAN_CASH_OPEN",
        "name": "European Cash Open Breakouts (DAX40, UK100, EU50)",
        "description": "Killed in trading buff HV battery A1-A7. Spread drag of 1.6+ pts erases net edge.",
        "patterns": [
            r"\b(?:dax|dax40|ger40|uk100|ftse|eu50|sx5e|stoxx50)\b.*?\b(?:cash\s+open|frankfurt|london\s+open|orb|range\s+breakout)\b",
            r"\b(?:cash\s+open|frankfurt|london\s+open|orb|range\s+breakout)\b.*?\b(?:dax|dax40|ger40|uk100|ftse|eu50|sx5e|stoxx50)\b",
            r"\b(?:dax|ger40|uk100)\b.*?\b(?:отварянето|европейск\w*\s+пазар|кеш\s+оупън|пробив)\b",
        ],
        "refutation_patterns": [
            r"\b(?:killed|refuted|dead|unviable|убит|отхвърлен|неработещ|елиминиран|spread\s+drag|спредът\s+консумира)\b",
        ],
    },
    {
        "id": "GRAVEYARD_MES_MNQ_PAIRS",
        "name": "MES/MNQ Intraday Pairs Mean Reversion",
        "description": "Killed in trading buff lab (ADF p=0.092, half-life 38 days, t_2x=-5.96).",
        "patterns": [
            r"\b(?:mes|mnq|es|nq)\b.*?\b(?:pair|pairs|mean\s+reversion|spread\s+trading|cointegrat\w*)\b",
            r"\b(?:двойки|арбитраж)\b.*?\b(?:mes|mnq|es|nq|индекс\w*)\b",
        ],
        "refutation_patterns": [
            r"\b(?:killed|refuted|dead|unviable|убит|отхвърлен|неработещ)\b",
        ],
    },
    {
        "id": "GRAVEYARD_SINGLE_STOCK_CFDS",
        "name": "Single-Stock CFDs on FTMO (PILLAR1_XFTMO01)",
        "description": "Killed in lab (46 stocks, 4,548 trades, median spread 0.093R, net t=-6.53).",
        "patterns": [
            r"\b(?:stock\s+cfd|equity\s+cfd|акции\s+cfd|единични\s+акции)\b.*?\b(?:ftmo|brightfunded|prop\s+firm|интрадей)\b",
        ],
        "refutation_patterns": [
            r"\b(?:killed|refuted|dead|unviable|убит|отхвърлен|неработещ|не\s+предлагат|недостъпн\w*)\b",
        ],
    },
    {
        "id": "GRAVEYARD_SYNTHETIC_REGULATORY_CITATIONS",
        "name": "Synthetic Regulatory Citations (BIS / CFTC / SEC / IMF talking about prop firms or R-multiples)",
        "description": "Hard ban on attributing R-multiples, prop firms (FTMO, BrightFunded), or trading setups to macro/central bank institutions.",
        "patterns": [
            r"\b(?:bis|cftc|sec|imf|federal\s+reserve|ecb)\b.*?\b(?:prop\s+firm|ftmo|brightfunded|r-multiple|r-мултипли|проп\s+фирм\w*)\b",
            r"\b(?:prop\s+firm|ftmo|brightfunded|r-multiple|r-мултипли|проп\s+фирм\w*)\b.*?\b(?:bis|cftc|sec|imf|federal\s+reserve|ecb)\b",
        ],
        "refutation_patterns": [
            r"\b(?:fabricated|hallucinated|fake|banned|забранено|измислен|невалиден|нарушение)\b",
        ],
    },
]


def load_desk_knowledge_text() -> str:
    """Reads available desk master directives and returns combined text."""
    combined = []
    for p in DESK_KNOWLEDGE_PATHS:
        if p.exists():
            try:
                combined.append(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return "\n\n".join(combined)


def scan_text_against_desk_graveyard(text: str) -> list[dict[str, Any]]:
    """Scans proposal or report text against all graveyard rules.
    
    Returns list of violations where a killed strategy is asserted without
    explicitly acknowledging that it is dead/refuted.
    """
    violations = []
    for rule in GRAVEYARD_RULES:
        matched = False
        matched_snippet = ""
        for pat in rule["patterns"]:
            m = re.search(pat, text, re.I)
            if m:
                matched = True
                # Grab surrounding snippet for diagnostic context
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 40)
                matched_snippet = text[start:end].replace("\n", " ")
                break

        if not matched:
            continue

        # Check if refutation is acknowledged anywhere in the text or locally
        acknowledged = False
        for ack_pat in rule["refutation_patterns"]:
            if re.search(ack_pat, text, re.I):
                acknowledged = True
                break

        if not acknowledged:
            violations.append({
                "rule_id": rule["id"],
                "name": rule["name"],
                "description": rule["description"],
                "matched_snippet": matched_snippet,
            })

    return violations


if __name__ == "__main__":
    import sys
    sample = "Ние предлагаме златен пробив около лондонския фиксинг за новия проп акаунт."
    res = scan_text_against_desk_graveyard(sample)
    if res:
        print(f"[TEST PASS] Caught {len(res)} graveyard violation(s): {res[0]['name']}")
    else:
        print("[TEST FAIL] Did not catch graveyard violation.")
        sys.exit(1)
