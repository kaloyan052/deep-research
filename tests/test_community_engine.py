#!/usr/bin/env python3
"""Tests for Deep Research Engine v9.0 Keyless Community & Practitioner Subsystem."""

import unittest
from dr_engine.tools.community_engine import (
    detect_community_platform,
    classify_and_score_text,
    parse_reddit_json_payload,
    parse_x_syndication_payload,
    parse_hn_algolia_payload,
    parse_stackexchange_payload,
    format_thread_to_snapshot,
)


class TestCommunityEngine(unittest.TestCase):
    def test_platform_detection(self):
        self.assertEqual(
            detect_community_platform("https://www.reddit.com/r/algotrading/comments/xyz/slug"),
            "reddit",
        )
        self.assertEqual(
            detect_community_platform("https://x.com/derivs_micro/status/192001234567890"),
            "x",
        )
        self.assertEqual(
            detect_community_platform("https://twitter.com/user/status/12345"),
            "x",
        )
        self.assertEqual(
            detect_community_platform("https://news.ycombinator.com/item?id=41234567"),
            "hn",
        )
        self.assertEqual(
            detect_community_platform("https://quant.stackexchange.com/questions/88901/ou-bias"),
            "stackexchange",
        )
        self.assertEqual(
            detect_community_platform("https://stackoverflow.com/questions/1234567/sample"),
            "stackexchange",
        )
        self.assertIsNone(
            detect_community_platform("https://en.wikipedia.org/wiki/Algorithmic_trading")
        )
        self.assertIsNone(
            detect_community_platform("https://arxiv.org/abs/2301.00001")
        )

    def test_noise_filtering_and_karma_gates(self):
        reddit_payload = [
            {
                "data": {
                    "children": [
                        {
                            "kind": "t3",
                            "data": {
                                "subreddit_name_prefixed": "r/algotrading",
                                "title": "Microstructure Execution Slippage",
                                "selftext": "Top of book spreads widen to 3.5 bps during FOMC events.",
                                "author": "op_trader",
                                "score": 80,
                                "created_utc": 1778371200,
                            },
                        }
                    ]
                }
            },
            {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "id": "c1",
                                "author": "good_trader",
                                "score": 25,
                                "created_utc": 1778372000,
                                "body": "We measured 2.1 bps fill slippage and switched to midpoint pegs.",
                                "replies": "",
                            },
                        },
                        {
                            "kind": "t1",
                            "data": {
                                "id": "c2",
                                "author": "spam_bot",
                                "score": 50,
                                "created_utc": 1778373000,
                                "body": "Join my Telegram VIP group for guaranteed 50% daily signals! https://t.me/free",
                                "replies": "",
                            },
                        },
                        {
                            "kind": "t1",
                            "data": {
                                "id": "c3",
                                "author": "downvoted",
                                "score": -5,
                                "created_utc": 1778374000,
                                "body": "Just buy calls on everything, market always goes up.",
                                "replies": "",
                            },
                        },
                    ]
                }
            },
        ]
        thread = parse_reddit_json_payload(
            reddit_payload,
            source_url="https://www.reddit.com/r/algotrading/comments/xyz/microstructure",
            min_score=2,
        )
        self.assertEqual(len(thread.comments), 1)
        self.assertEqual(thread.comments[0].comment_id, "c1")
        self.assertEqual(thread.filtered_noise_count, 2)

    def test_b5_rule_compliance_classification(self):
        # SaaS review pain complaint
        pain_text = (
            "Our legacy vendor had a 15% billing error rate and quota lock-in; "
            "switching to a deterministic preflight diff resolved support tickets."
        )
        kind, proves, score, pain_h, tech_h = classify_and_score_text(pain_text, 20)
        self.assertEqual(kind, "review_pain")
        self.assertEqual(proves, "incumbent_weakness")

        # Microstructure technical workaround
        tech_text = (
            "The deterministic workaround is pegging midpoint limit orders when "
            "net dealer GEX drops below -2.5 billion USD, cutting p99 fill slippage to 0.4 bps."
        )
        kind_t, proves_t, score_t, pain_ht, tech_ht = classify_and_score_text(tech_text, 40)
        self.assertEqual(kind_t, "technical_lead")
        self.assertEqual(proves_t, "architectural_workaround")

    def test_snapshot_formatting_bm25_alignment(self):
        hn_payload = {
            "id": 999123,
            "title": "Deterministic Parsing with WASM",
            "author": "dev1",
            "points": 120,
            "created_at_i": 1778371200,
            "text": "<p>A simple preflight check stops errors at boundary.</p>",
            "children": [
                {
                    "id": 999124,
                    "author": "engineer_a",
                    "points": 35,
                    "created_at_i": 1778372000,
                    "text": "<p>We had constant vendor lock-in issues until switching to local schemas.</p>",
                    "children": [],
                }
            ],
        }
        thread = parse_hn_algolia_payload(
            hn_payload,
            source_url="https://news.ycombinator.com/item?id=999123",
        )
        snap = format_thread_to_snapshot(thread)
        self.assertIn("--- High-Signal Comments ---", snap)
        self.assertIn("[Comment by engineer_a (Score: 35", snap)
        # Check paragraph separation for BM25 indexing
        paragraphs = snap.split("\n\n")
        self.assertGreaterEqual(len(paragraphs), 3)


if __name__ == "__main__":
    unittest.main()
