#!/usr/bin/env python3
"""Deep Research Engine v10.0 — Script-Aware Polyglot Text Layer.

The v9.0 BM25 tokenizer used ``[a-zа-я0-9]{3,}``. That expression silently
discards every CJK ideograph, every Hangul syllable, and splits accented Latin
words ("für" -> "f", "r"; "défaillance" -> "d", "faillance"). The engine mined
eight languages and then made six of them invisible at ranking time.

This module provides a deterministic, dependency-free tokenizer that:

  * applies Unicode NFKC + diacritic folding (so ``für`` -> ``fur``,
    ``pérdida`` -> ``perdida``, ``ＡＩ`` -> ``ai``);
  * segments Latin / Cyrillic / Hangul / numeric runs into words;
  * segments Han and Kana runs (which have no spaces) into *characters plus
    adjacent bigrams*, the standard IR treatment for Chinese and Japanese;
  * exposes number density and shingle helpers used by the context ranker.

Pure Python 3.10+ standard library. Windows cp1252-safe. No third-party deps,
no language models, no network access.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

__all__ = [
    "script_of",
    "fold_text",
    "tokenize",
    "shingles",
    "detect_scripts",
    "number_density",
    "is_cjk_heavy",
]

# Script buckets used by the segmenter. Everything else is a delimiter.
_LATIN = "latin"
_CYRILLIC = "cyrillic"
_HAN = "han"
_KANA = "kana"
_HANGUL = "hangul"
_DIGIT = "digit"
_OTHER = "other"

_CJK_BIGRAM_MAX_RUN = 24  # guard against pathological unbroken runs


def script_of(ch: str) -> str:
    """Classify a single Unicode codepoint into an IR script bucket.

    Uses Unicode character *names* rather than fragile ``[a-z]`` ranges, so
    accented Latin, Greek, Cyrillic, Hangul, Kana and Han are all recognised.
    """
    if ch.isdigit():
        return _DIGIT
    name = unicodedata.name(ch, "")
    if "CJK UNIFIED IDEOGRAPH" in name or "CJK COMPATIBILITY IDEOGRAPH" in name:
        return _HAN
    if "HIRAGANA" in name or "KATAKANA" in name:
        return _KANA
    if "HANGUL" in name:
        return _HANGUL
    if "CYRILLIC" in name:
        return _CYRILLIC
    if ch.isalpha():
        # Latin (including diacritics), Greek, etc. Diacritics were folded away
        # by fold_text(), so anything alphabetic left is treated as a word run.
        return _LATIN
    return _OTHER


def fold_text(text: str) -> str:
    """NFKC normalise and strip *Latin* diacritics, preserving other scripts.

    ``NFKC`` maps full-width forms (``ＡＩ``) and compatibility ligatures to
    their canonical equivalents. NFD + removal of combining marks maps
    ``défaillance`` -> ``defaillance`` and ``für`` -> ``fur`` without losing
    the word as a token (which is what a naive ``[a-z]+`` regex does).

    The decomposition is deliberately **script-selective**. A global NFD pass
    would decompose Cyrillic ``й`` into ``и`` (corrupting Russian keywords) and
    Hangul syllables into Jamo. Only Latin-script codepoints are folded.
    """
    if not text:
        return ""
    normalised = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for ch in normalised:
        name = unicodedata.name(ch, "")
        if "LATIN" in name:
            base = "".join(
                c for c in unicodedata.normalize("NFD", ch)
                if not unicodedata.category(c).startswith("M")
            )
            out.append(base or ch)
        else:
            out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def _emit_run(run: str, bucket: str, out: list[str], min_len: int) -> None:
    """Emit tokens for one maximal same-script run."""
    run = run.strip()
    if not run:
        return
    if bucket in (_HAN, _KANA):
        chars = list(run)[:_CJK_BIGRAM_MAX_RUN]
        if len(chars) >= 2:
            # Bigrams are the recall-bearing units for unspaced scripts.
            out.extend("".join(chars[i : i + 2]) for i in range(len(chars) - 1))
        else:
            out.extend(chars)
        # Keep the whole run too: exact-phrase queries in CJK then still match.
        if 2 <= len(chars) <= 8:
            out.append("".join(chars))
        return
    if len(run) >= min_len:
        out.append(run.lower())


def tokenize(text: str, min_len: int = 2) -> list[str]:
    """Tokenise polyglot text into lower-cased, script-aware IR terms.

    Args:
        text: Raw snapshot or query text in any mix of scripts.
        min_len: Minimum length for spaced-script words (default 2). The v9.0
            ``{3,}`` convention silently dropped high-signal two-letter
            acronyms such as ``AI``, ``ML`` and ``FX``; the ranker now removes
            short function words with an explicit multilingual stopword set
            instead of destroying recall by length. CJK bigrams are always
            emitted.

    Returns:
        A list of tokens. Deterministic; no stemming, no model, no I/O.
    """
    folded = fold_text(text)
    if not folded:
        return []

    out: list[str] = []
    run: list[str] = []
    run_bucket = _OTHER

    for ch in folded:
        if not ch.isalnum():
            _emit_run("".join(run), run_bucket, out, min_len)
            run, run_bucket = [], _OTHER
            continue
        bucket = script_of(ch)
        # A digit adjacent to letters stays in the same run (0DTE, GLP1, M15).
        if bucket == _DIGIT and run and run_bucket == _LATIN:
            bucket = _LATIN
        if bucket == _LATIN and run and run_bucket == _DIGIT:
            # Re-classify a leading numeric run as Latin once letters arrive.
            run_bucket = _LATIN
            bucket = _LATIN
        if run and bucket != run_bucket:
            _emit_run("".join(run), run_bucket, out, min_len)
            run = []
        run.append(ch)
        run_bucket = bucket

    _emit_run("".join(run), run_bucket, out, min_len)
    return out


def shingles(text: str, k: int = 3, *, stopwords: Iterable[str] = ()) -> set[tuple[str, ...]]:
    """Return word-shingle set used for syndication / independence clustering."""
    stop = {w.lower() for w in stopwords}
    words = [w for w in tokenize(text) if w not in stop]
    if not words:
        return set()
    if len(words) < k:
        return {tuple(words)}
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def detect_scripts(text: str) -> dict[str, float]:
    """Return the share of alphabetic characters belonging to each script."""
    counts: dict[str, int] = {_LATIN: 0, _CYRILLIC: 0, _HAN: 0, _KANA: 0, _HANGUL: 0}
    total = 0
    for ch in fold_text(text):
        bucket = script_of(ch)
        if bucket in counts:
            counts[bucket] += 1
            total += 1
    if not total:
        return {}
    return {k: round(v / total, 4) for k, v in counts.items() if v}


def is_cjk_heavy(text: str, threshold: float = 0.20) -> bool:
    """True when Han/Kana/Hangul characters exceed ``threshold`` of letters."""
    scripts = detect_scripts(text)
    return sum(scripts.get(s, 0.0) for s in (_HAN, _KANA, _HANGUL)) >= threshold


_NUMERIC_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w.])")


def number_density(text: str) -> float:
    """Fraction of tokens that are numeric or contain a numeric literal.

    High-number-density passages (fee tables, benchmark rows, drawdown rules)
    are disproportionately load-bearing in due-diligence research; the context
    ranker uses this as a bounded additive prior, not as a replacement for BM25.
    """
    tokens = tokenize(text)
    if not tokens:
        return 0.0
    numeric_tokens = sum(1 for t in tokens if any(c.isdigit() for c in t))
    return min(1.0, numeric_tokens / len(tokens))


def _selftest() -> int:
    # Accented Latin must survive as whole words (v9.0 split them).
    de = tokenize("Im Produktivbetrieb verursachte ein Fehler Slippage und Latenz.")
    assert "produktivbetrieb" in de and "fehler" in de
    fr = tokenize("Une défaillance en production avec écart d'exécution.")
    assert "defaillance" in fr and "production" in fr
    es = tokenize("Pérdida por deslizamiento en producción.")
    assert "perdida" in es and "produccion" in es

    # Cyrillic is preserved.
    ru = tokenize("Сбой в алгоритме исполнения привел к убытку в 440 миллионов.")
    assert "сбой" in ru and "убытку" in ru and "440" in ru

    # CJK: no spaces, so bigrams must exist (v9.0 produced zero tokens).
    zh = tokenize("生产环境实际测试滑点回测失效踩坑")
    assert len(zh) >= 8, f"CJK segmentation produced too few tokens: {zh}"
    assert any(len(t) == 2 for t in zh), f"No CJK bigrams produced: {zh}"
    assert is_cjk_heavy("生产环境实际测试滑点回测失效踩坑")

    ja = tokenize("本番環境でスリッページが発生した")
    assert any(len(t) == 2 for t in ja), f"No Kana/Han bigrams produced: {ja}"
    ko = tokenize("실서버 슬리피지 버그 장애")
    assert "슬리피지" in ko and "실서버" in ko

    # Mixed-script and full-width forms.
    mixed = tokenize("ＡＩ LLM 大模型 GPT-6 0DTE")
    assert "ai" in mixed and "llm" in mixed and "0dte" in mixed

    assert detect_scripts("生产环境") .get("han") == 1.0
    assert number_density("Revenue 1234 USD in 2025") > 0
    assert shingles("alpha beta gamma delta", k=3) == {
        ("alpha", "beta", "gamma"), ("beta", "gamma", "delta")
    }
    print("[SELFTEST PASS] polyglot_text v10.0 (8 scripts + CJK bigrams) verified.")
    return 0


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_selftest())
