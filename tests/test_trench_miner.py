#!/usr/bin/env python3
"""Unit tests for dr_engine/tools/trench_miner.py (Deep Research v9.0)."""

from __future__ import annotations

import unittest
from dr_engine.tools.trench_miner import (
    TrenchEvidenceItem,
    build_polyglot_queries,
    mine_hacker_news_comments,
)


class TestTrenchMiner(unittest.TestCase):
    def test_polyglot_expansion(self):
        """Verifies that Bulgarian technical words expand into 8 languages (EN, RU, ZH, JA, KO, DE, FR, ES)."""
        poly = build_polyglot_queries("Кой е най-добрият AI модел за финанси")
        for lang in ("en", "ru", "zh", "ja", "ko", "de", "fr", "es"):
            self.assertIn(lang, poly)
        self.assertTrue(any("model" in q.lower() or "llm" in q.lower() for q in poly["en"]))
        self.assertTrue(any("финансы" in q.lower() or "алготрейдинг" in q.lower() for q in poly["ru"]))
        self.assertTrue(any("金融" in q or "大模型" in q for q in poly["zh"]))
        self.assertTrue(any("거대언어모델" in q or "금융" in q for q in poly["ko"]))
        self.assertTrue(any("Sprachmodell" in q or "Finanzen" in q for q in poly["de"]))

    def test_render_snapshot_block(self):
        """Verifies that TrenchEvidenceItem generates deterministic paragraph-aligned passages."""
        item = TrenchEvidenceItem(
            platform="Habr",
            channel="RU_Engineering",
            author="algotrader99",
            title="Production Execution Gotchas",
            url="https://habr.com/ru/articles/890142/",
            date="2026-11-05",
            score=55,
            content="Сбой в алгоритме исполнения привел к убытку в 440 миллионов за 45 минут.",
            alpha_flag=True,
            lang="ru",
        )
        snap = item.render_snapshot_block()
        self.assertIn("=== TRENCH SNAPSHOT: Habr (RU_Engineering) [RU] ===", snap)
        self.assertIn("[HIGH-SIGNAL TRENCH ALPHA]", snap)
        self.assertIn('"Сбой в алгоритме исполнения привел к убытку в 440 миллионов за 45 минут."', snap)


if __name__ == "__main__":
    unittest.main()
