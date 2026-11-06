#!/usr/bin/env python3

"""Deep Research Engine v9.0 — Keyless Practitioner & Community Ingestion Engine.



Extracts, filters, classifies, and formats practitioner discussions from:

  1. Reddit Native JSON (`*.reddit.com/r/.../comments/...json` & Search JSON)

  2. X / Twitter Syndication (`api.fxtwitter.com`, `api.vxtwitter.com`, `cdn.syndication.twimg.com`)

  3. Hacker News Algolia REST API (`hn.algolia.com/api/v1/items/<id>` & Search API)

  4. StackExchange / Quant.StackExchange API v2.3 (gzip-aware, LaTeX-preserving `withbody`)

  5. Modern Discourse Forums (`<domain>/t/<slug>/<id>.json`)

  6. GitHub Issues & Discussions (`api.github.com/repos/<owner>/<repo>/issues/<id>`)

  7. Generic Forum Thread Extractor (XenForo, vBulletin, phpBB, Forex Factory, Elite Trader,

     Wilmott, HealthUnlocked, Inspire)



Produces deterministic, immutable text snapshots compatible with `lean_engine.py`

(`rank_bm25_passages` and `quote_matches_snapshot`) and `v9_bullshit_filters.py` (Rule B5).



Pure Python 3.10+ stdlib. Zero paid API keys. Windows cp1252-safe.

"""



from __future__ import annotations



import argparse

import datetime as dt

import gzip

import hashlib

import html

import json

import re

import sys

import time

import urllib.error

import urllib.parse

import urllib.request

import zlib

from dataclasses import asdict, dataclass, field

from pathlib import Path

from typing import Any



# ---------------------------------------------------------------------------

# Constants, Headers & Epistemic Lexicons

# ---------------------------------------------------------------------------

REDDIT_USER_AGENT = "python:dr_engine.community:v9.0 (by /u/dr_epistemic_architect)"

BROWSER_USER_AGENT = (

    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "

    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

)



STACKEXCHANGE_BUILTIN_WITHBODY_FILTER = "withbody"



# Promotional, affiliate, referral, and low-signal retail noise patterns

AFFILIATE_URL_RE = re.compile(

    r"https?://\S*(?:"

    r"utm_source=|utm_medium=|utm_campaign=|ref=|aff=|affiliate|partner_id="

    r"|amzn\.to/|bit\.ly/|tinyurl\.com/|linktr\.ee/|t\.me/\+|discord\.gg/"

    r")\S*",

    re.I,

)



SHILL_NOISE_RE = re.compile(

    r"\b(?:"

    r"use\s+my\s+(?:referral|promo|discount)\s+code|dm\s+me\s+for\s+(?:signals|access)"

    r"|join\s+my\s+(?:telegram|discord|vip\s+group)|guaranteed\s+\d+%\s+(?:daily|weekly|monthly)"

    r"|check\s+out\s+my\s+bio|100x\s+gem|to\s+the\s+moon\s*🚀|free\s+airdrop"

    r")\b",

    re.I,

)



LOW_EFFORT_COMMENT_RE = re.compile(

    r"^(?:\+1|this!?|following|bump|agreed|same\s+here|lol|lmao|thanks!?|thank\s+you!?|"

    r"remindme!.*|!remindme.*|\[deleted\]|\[removed\])$",

    re.I,

)



# Epistemic Classifier Lexicons:

# 1. Voice of Customer / Operational & Execution Pain (`review_pain`)

REVIEW_PAIN_PATTERNS: tuple[re.Pattern[str], ...] = (

    re.compile(

        r"\b(?:slippage|spread\s+widening|requote|stop\s+hunt|margin\s+call|execution\s+delay|"

        r"latency\s+spike|reject(?:ed)?\s+order|fill\s+quality|adverse\s+selection|swap\s+fee|"

        r"commission\s+trap|hidden\s+fee|withdraw(?:al)?\s+hold)\b",

        re.I,

    ),

    re.compile(

        r"\b(?:churn(?:ed)?|cancel(?:led|ing)?\s+subscription|billing\s+(?:issue|error(?:\s+rate)?)|overcharg(?:ed|ing)|"

        r"price\s+hike|(?:[a-z0-9_-]+\s+)?lock[- ]in|support\s+(?:ghosted|tickets?)|broken\s+sync|rate\s+limit|"

        r"api\s+quota|downtime|outage|data\s+loss|undocumented\s+limit|enterprise\s+upsell)\b",

        re.I,

    ),

    re.compile(

        r"\b(?:side\s+effect|adverse\s+event|discontinu(?:ed|ation)|non[- ]adherence|"

        r"brain\s+fog|nausea|insomnia|withdrawal\s+symptom|prior\s+authorization|"

        r"insurance\s+denied|off[- ]label|tolerability|titration\s+failure)\b",

        re.I,

    ),

    re.compile(

        r"\b(?:audit\s+trigger|penalty\s+assessment|statutory\s+ambiguity|compliance\s+burden|"

        r"safe\s+harbor\s+trap|retroactive\s+tax|nexus\s+exposure|reclassification\s+risk|"

        r"filing\s+rejection|schema\s+validation\s+error)\b",

        re.I,

    ),

)



# 2. Practitioner Alpha / Technical Solutions & Microstructure Physics (`technical_lead`)

TECHNICAL_LEAD_PATTERNS: tuple[re.Pattern[str], ...] = (

    re.compile(

        r"\b(?:workaround|root\s+cause|patch(?:ed)?|fix(?:ed)?\s+by|config(?:uration)?|"

        r"benchmark|p95|p99|throughput|memory\s+leak|deadlock|race\s+condition|"

        r"idempoten(?:t|cy)|preflight|read[- ]only|deterministic|ast|xsd|wasm|schema)\b",

        re.I,

    ),

    re.compile(

        r"\b(?:gamma\s+exposure|gex|vanna|charm|0dte|dealer\s+hedging|moc\s+imbalance|"

        r"limit\s+order\s+book|lob|queue\s+position|maker\s+rebate|basis\s+points|bps|"

        r"sharpe|kelly|cointegration|ornstein[- ]uhlenbeck|volatility\s+surface|skew)\b",

        re.I,

    ),

    re.compile(

        r"\b(?:pharmacokinetics|half[- ]life|bioavailability|cyp\d\w+|receptor\s+affinity|"

        r"mechanism\s+of\s+action|cohort|hazard\s+ratio|confidence\s+interval|"

        r"irc\s+§?\s*\d+|treas\.?\s+reg|rev\.?\s+proc|article\s+\d+|directive\s+20\d\d)\b",

        re.I,

    ),

    re.compile(r"(`[^`]{4,}`|\$[^$]{3,}\$|https?://github\.com/[\w.-]+/[\w.-]+)", re.I),

)



QUANTITATIVE_SIGNAL_RE = re.compile(

    r"\b\d+(?:\.\d+)?\s*(?:%|bps\b|bp\b|ms\b|s\b|usd\b|\$|€|£|x\b|mg\b|mcg\b|k\b|m\b|bn\b)",

    re.I,

)





# ---------------------------------------------------------------------------

# Data Structures

# ---------------------------------------------------------------------------

@dataclass

class CommunityComment:

    comment_id: str

    author: str

    score: int

    created_date: str

    body: str

    depth: int = 0

    kind: str = "general"          # "review_pain" | "technical_lead" | "general"

    proves: str = "context"        # "incumbent_weakness" | "architectural_workaround" | "context"

    signal_score: float = 0.0

    pain_hits: int = 0

    tech_hits: int = 0





@dataclass

class CommunityThread:

    platform: str

    channel: str

    url: str

    title: str

    author: str

    score: int

    created_date: str

    op_body: str

    op_kind: str = "general"

    op_proves: str = "context"

    comments: list[CommunityComment] = field(default_factory=list)

    raw_comment_count: int = 0

    filtered_noise_count: int = 0

    metadata: dict[str, Any] = field(default_factory=dict)





# ---------------------------------------------------------------------------

# Utility & Text Normalization Helpers

# ---------------------------------------------------------------------------

def _utc_iso_date(ts: int | float | str | None) -> str:

    """Normalizes Unix timestamps or ISO date strings into YYYY-MM-DD."""

    if ts is None or ts == "":

        return dt.date.today().isoformat()

    if isinstance(ts, (int, float)):

        try:

            return dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc).strftime("%Y-%m-%d")

        except (ValueError, OSError, OverflowError):

            return dt.date.today().isoformat()

    s = str(ts).strip()

    if re.fullmatch(r"\d{9,10}(?:\.\d+)?", s):

        return _utc_iso_date(float(s))

    m = re.search(r"((?:19|20)\d{2}-\d{2}-\d{2})", s)

    if m:

        return m.group(1)

    # Parse RFC-2822 / Twitter style dates e.g. "Wed May 10 14:22:01 +0000 2026"

    m_tw = re.search(

        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+[\d:]+\s+[+-]\d{4}\s+((?:19|20)\d{2})\b",

        s,

        re.I,

    )

    if m_tw:

        months = {

            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,

            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,

        }

        mon = months.get(m_tw.group(1).lower(), 1)

        day = int(m_tw.group(2))

        yr = int(m_tw.group(3))

        return f"{yr:04d}-{mon:02d}-{day:02d}"

    return dt.date.today().isoformat()





def _clean_html_preserve_math_and_code(raw_html: str) -> str:

    """Strips HTML tags while preserving inline/block code and LaTeX expressions."""

    if not raw_html:

        return ""

    text = raw_html

    # Convert <code> and <pre> blocks into backtick-fenced inline code

    text = re.sub(

        r"(?is)<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",

        lambda m: f" `{html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}` ",

        text,

    )

    text = re.sub(

        r"(?is)<code[^>]*>(.*?)</code>",

        lambda m: f"`{html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}`",

        text,

    )

    # Remove script, style, quote-header clutter, and signatures

    text = re.sub(r"(?is)<(script|style|noscript|svg|aside|footer|nav)[^>]*>.*?</\1>", " ", text)

    text = re.sub(r"(?is)<blockquote[^>]*>.*?</blockquote>", " [quoted context] ", text)

    text = re.sub(r"(?is)<(br|p|div|li|tr|h[1-6])[^>]*>", " ", text)

    text = re.sub(r"(?is)<[^>]+>", " ", text)

    text = html.unescape(text)

    return _normalise_verbatim_text(text)





def _normalise_verbatim_text(text: str) -> str:

    """Normalizes text for 100% compatibility with `lean_engine.py`'s `normalise_ws`."""

    if not text:

        return ""

    text = html.unescape(text)

    # Strip markdown links `[label](url)` -> `label`

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)

    # Strip affiliate/referral URLs completely

    text = AFFILIATE_URL_RE.sub("[affiliate-link-stripped]", text)

    # Normalize unicode dashes, quotes, and non-breaking spaces

    text = text.replace("\u00a0", " ").replace("−", "-").replace("–", "-").replace("—", "-")

    text = re.sub(r"['’‘]", "'", text)

    text = re.sub(r'[“”"]', "'", text)

    # Collapse whitespace into single spaces so every comment forms a single clean paragraph

    text = re.sub(r"\s+", " ", text).strip()

    return text





def _http_get_raw(

    url: str,

    headers: dict[str, str] | None = None,

    timeout: float = 15.0,

) -> tuple[int, dict[str, str], str]:

    """Executes a stdlib HTTP GET request with transparent gzip/deflate decompression."""

    req_headers = {

        "User-Agent": BROWSER_USER_AGENT,

        "Accept": "application/json, text/html, application/xhtml+xml, */*;q=0.8",

        "Accept-Language": "en-US,en;q=0.9",

        "Accept-Encoding": "gzip, deflate",

    }

    if headers:

        req_headers.update(headers)



    req = urllib.request.Request(url, headers=req_headers)

    with urllib.request.urlopen(req, timeout=timeout) as resp:

        raw_bytes = resp.read()

        resp_headers = {k.lower(): v for k, v in resp.headers.items()}

        encoding = resp_headers.get("content-encoding", "").lower()

        if "gzip" in encoding or raw_bytes[:2] == b"\x1f\x8b":

            try:

                raw_bytes = gzip.decompress(raw_bytes)

            except Exception:

                pass

        elif "deflate" in encoding:

            try:

                raw_bytes = zlib.decompress(raw_bytes)

            except Exception:

                try:

                    raw_bytes = zlib.decompress(raw_bytes, -zlib.MAX_WBITS)

                except Exception:

                    pass

        body = raw_bytes.decode("utf-8", errors="replace")

        return resp.status, resp_headers, body





def _http_get_json(

    url: str,

    headers: dict[str, str] | None = None,

    timeout: float = 15.0,

) -> Any:

    """Fetches and parses JSON from an endpoint using stdlib."""

    _, _, body = _http_get_raw(url, headers=headers, timeout=timeout)

    return json.loads(body)





# ---------------------------------------------------------------------------

# Epistemic Noise Filter & Anti-Goodhart Classifier

# ---------------------------------------------------------------------------

def classify_and_score_text(text: str, score: int = 1) -> tuple[str, str, float, int, int]:

    """Classifies practitioner content into `review_pain`, `technical_lead`, or `general`.



    Returns:

        (kind, proves, signal_score, pain_hits, tech_hits)

    Note on v9.0 Rule B5 compliance:

        - `review_pain` always maps to `proves="incumbent_weakness"` (never WTP).

        - `technical_lead` always maps to `proves="architectural_workaround"`.

    """

    pain_hits = sum(len(pat.findall(text)) for pat in REVIEW_PAIN_PATTERNS)

    tech_hits = sum(len(pat.findall(text)) for pat in TECHNICAL_LEAD_PATTERNS)

    quant_hits = len(QUANTITATIVE_SIGNAL_RE.findall(text))



    if pain_hits > 0 and pain_hits >= tech_hits:

        kind = "review_pain"

        proves = "incumbent_weakness"

    elif tech_hits > 0:

        kind = "technical_lead"

        proves = "architectural_workaround"

    else:

        kind = "general"

        proves = "context"



    # Compute composite epistemic signal score (log-damped upvotes + lexical density + quant grounding)

    upvote_weight = max(0.0, float(score)) ** 0.5

    lexical_bonus = (2.5 * pain_hits) + (2.8 * tech_hits) + (1.8 * min(4, quant_hits))

    length_bonus = min(3.0, len(text) / 180.0)

    signal_score = round(upvote_weight + lexical_bonus + length_bonus, 2)

    return kind, proves, signal_score, pain_hits, tech_hits





def is_epistemic_noise(

    text: str,

    score: int,

    min_score: int = 1,

    min_chars: int = 40,

    author: str = "",

) -> bool:

    """Strict Anti-Goodhart Noise Gate: drops negative/low-karma comments, bots, and shills."""

    if score < min_score:

        return True

    cleaned = text.strip()

    if len(cleaned) < min_chars:

        return True

    if LOW_EFFORT_COMMENT_RE.match(cleaned):

        return True

    if SHILL_NOISE_RE.search(cleaned):

        return True

    low_author = author.lower()

    if low_author in ("automoderator", "[deleted]", "deleted", "bot"):

        return True

    return False





def filter_and_rank_comments(

    comments: list[CommunityComment],

    min_score: int = 1,

    min_chars: int = 40,

    target_kind: str = "all",

    max_comments: int = 25,

) -> tuple[list[CommunityComment], int]:

    """Applies the Noise Gate, classifies comments, filters by `--kind`, and ranks by signal."""

    kept: list[CommunityComment] = []

    dropped = 0

    for c in comments:

        c.body = _normalise_verbatim_text(c.body)

        if is_epistemic_noise(c.body, c.score, min_score=min_score, min_chars=min_chars, author=c.author):

            dropped += 1

            continue

        kind, proves, sig, p_hits, t_hits = classify_and_score_text(c.body, c.score)

        c.kind = kind

        c.proves = proves

        c.signal_score = sig

        c.pain_hits = p_hits

        c.tech_hits = t_hits



        if target_kind == "review_pain" and c.kind != "review_pain":

            # Allow high-signal comments with at least 1 pain hit when explicitly filtering for review_pain

            if p_hits == 0:

                dropped += 1

                continue

            c.kind = "review_pain"

            c.proves = "incumbent_weakness"

        elif target_kind == "technical_lead" and c.kind != "technical_lead":

            if t_hits == 0:

                dropped += 1

                continue

            c.kind = "technical_lead"

            c.proves = "architectural_workaround"



        kept.append(c)



    kept.sort(key=lambda item: (item.signal_score, item.score, len(item.body)), reverse=True)

    return kept[:max_comments], dropped





# ---------------------------------------------------------------------------

# 1. Reddit Native JSON Parser

# ---------------------------------------------------------------------------

def _reddit_json_url(url: str) -> str:

    parsed = urllib.parse.urlparse(url)

    path = parsed.path.rstrip("/")

    if not path.endswith(".json"):

        path = f"{path}.json"

    netloc = parsed.netloc or "www.reddit.com"

    if netloc in ("reddit.com", "old.reddit.com", "np.reddit.com"):

        netloc = "www.reddit.com"

    return urllib.parse.urlunparse(("https", netloc, path, "", "raw_json=1&sort=top", ""))





def parse_reddit_json_payload(

    payload: Any,

    source_url: str,

    min_score: int = 2,

    target_kind: str = "all",

    max_comments: int = 25,

) -> CommunityThread:

    """Parses a native Reddit thread JSON payload (2-element list or search listing)."""

    if isinstance(payload, list) and len(payload) >= 1:

        post_listing = payload[0]

        comment_listing = payload[1] if len(payload) > 1 else {}

    elif isinstance(payload, dict):

        post_listing = payload

        comment_listing = {}

    else:

        raise ValueError("Invalid Reddit JSON payload structure")



    post_children = post_listing.get("data", {}).get("children", [])

    if not post_children:

        raise ValueError("Reddit JSON payload contains no OP post data")



    op_data = post_children[0].get("data", {})

    subreddit = op_data.get("subreddit_name_prefixed") or f"r/{op_data.get('subreddit', 'unknown')}"

    title = _normalise_verbatim_text(op_data.get("title", "Untitled Reddit Thread"))

    author = str(op_data.get("author", "unknown"))

    score = int(op_data.get("score", op_data.get("ups", 0)) or 0)

    created_date = _utc_iso_date(op_data.get("created_utc"))

    selftext = _normalise_verbatim_text(op_data.get("selftext", ""))

    op_body = f"{title}. {selftext}".strip() if selftext else title

    op_kind, op_proves, _, _, _ = classify_and_score_text(op_body, score)



    raw_comments: list[CommunityComment] = []



    def _walk_comment_tree(children: list[dict[str, Any]], depth: int = 0) -> None:

        for child in children:

            if not isinstance(child, dict) or child.get("kind") != "t1":

                continue

            cdata = child.get("data", {})

            c_body = cdata.get("body", "")

            if not c_body:

                continue

            c_score = int(cdata.get("score", cdata.get("ups", 0)) or 0)

            c_author = str(cdata.get("author", "unknown"))

            c_id = str(cdata.get("id", f"c{len(raw_comments)+1}"))

            c_date = _utc_iso_date(cdata.get("created_utc"))

            raw_comments.append(

                CommunityComment(

                    comment_id=c_id,

                    author=f"u/{c_author}" if not c_author.startswith("u/") else c_author,

                    score=c_score,

                    created_date=c_date,

                    body=c_body,

                    depth=depth,

                )

            )

            replies = cdata.get("replies")

            if isinstance(replies, dict):

                rep_children = replies.get("data", {}).get("children", [])

                _walk_comment_tree(rep_children, depth + 1)



    if isinstance(comment_listing, dict):

        _walk_comment_tree(comment_listing.get("data", {}).get("children", []), depth=0)



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )



    return CommunityThread(

        platform="Reddit",

        channel=subreddit,

        url=source_url,

        title=title,

        author=f"u/{author}" if not author.startswith("u/") else author,

        score=score,

        created_date=created_date,

        op_body=op_body,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

    )





def fetch_reddit_thread(

    url: str,

    min_score: int = 2,

    target_kind: str = "all",

    max_comments: int = 25,

    timeout: float = 15.0,

) -> CommunityThread:

    json_url = _reddit_json_url(url)

    payload = _http_get_json(json_url, headers={"User-Agent": REDDIT_USER_AGENT}, timeout=timeout)

    return parse_reddit_json_payload(

        payload,

        source_url=url,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )





# ---------------------------------------------------------------------------

# 2. X / Twitter Syndication & Proxy Parser (fxtwitter / vxtwitter / twimg)

# ---------------------------------------------------------------------------

def _extract_tweet_identity(url: str) -> tuple[str, str]:

    """Extracts (username, status_id) from any X/Twitter/fxtwitter/vxtwitter URL."""

    m = re.search(r"(?:twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com)/(?:([^/]+)/)?status(?:es)?/(\d+)", url, re.I)

    if not m:

        raise ValueError(f"Cannot extract X/Twitter status ID from URL: {url}")

    user = m.group(1) or "i"

    status_id = m.group(2)

    return user, status_id





def parse_x_syndication_payload(

    payload: dict[str, Any],

    source_url: str,

    min_score: int = 0,

    target_kind: str = "all",

) -> CommunityThread:

    """Parses fxtwitter, vxtwitter, or cdn.syndication.twimg.com JSON payloads."""

    # Case 1: api.fxtwitter.com format (`{"code": 200, "tweet": {...}}`)

    tweet_obj = payload.get("tweet") if isinstance(payload.get("tweet"), dict) else payload



    author_obj = tweet_obj.get("author") or tweet_obj.get("user") or {}

    if isinstance(author_obj, dict):

        screen_name = (

            author_obj.get("screen_name")

            or author_obj.get("username")

            or tweet_obj.get("user_screen_name")

            or "unknown"

        )

        display_name = author_obj.get("name") or tweet_obj.get("user_name") or screen_name

    else:

        screen_name = str(tweet_obj.get("user_screen_name", "unknown"))

        display_name = screen_name



    raw_text = (

        tweet_obj.get("text")

        or tweet_obj.get("full_text")

        or (tweet_obj.get("note_tweet", {}) or {}).get("text")

        or ""

    )

    clean_text = _normalise_verbatim_text(raw_text)

    likes = int(

        tweet_obj.get("likes")

        or tweet_obj.get("favorite_count")

        or tweet_obj.get("favourites")

        or 0

    )

    retweets = int(

        tweet_obj.get("retweets")

        or tweet_obj.get("retweet_count")

        or 0

    )

    replies_cnt = int(

        tweet_obj.get("replies")

        or tweet_obj.get("conversation_count")

        or tweet_obj.get("reply_count")

        or 0

    )

    score = likes + (2 * retweets)

    created_raw = (

        tweet_obj.get("created_timestamp")

        or tweet_obj.get("created_at")

        or tweet_obj.get("date_epoch")

        or tweet_obj.get("date")

    )

    created_date = _utc_iso_date(created_raw)



    op_kind, op_proves, _, _, _ = classify_and_score_text(clean_text, score)



    # Extract embedded quote tweet, parent tweet, or syndication thread replies as comments

    raw_comments: list[CommunityComment] = []



    quote_obj = tweet_obj.get("quote") or tweet_obj.get("quoted_tweet") or tweet_obj.get("qrt")

    if isinstance(quote_obj, dict) and (quote_obj.get("text") or quote_obj.get("full_text")):

        q_author = (

            (quote_obj.get("author") or {}).get("screen_name")

            or (quote_obj.get("user") or {}).get("screen_name")

            or quote_obj.get("user_screen_name")

            or "quoted_user"

        )

        q_text = _normalise_verbatim_text(quote_obj.get("text") or quote_obj.get("full_text") or "")

        q_likes = int(quote_obj.get("likes") or quote_obj.get("favorite_count") or score)

        q_date = _utc_iso_date(quote_obj.get("created_timestamp") or quote_obj.get("created_at") or created_date)

        raw_comments.append(

            CommunityComment(

                comment_id=str(quote_obj.get("id", "quote_1")),

                author=f"@{q_author.lstrip('@')}",

                score=q_likes,

                created_date=q_date,

                body=f"[Quoted Post] {q_text}",

                depth=0,

            )

        )



    parent_obj = tweet_obj.get("parent") or tweet_obj.get("replying_to_status")

    if isinstance(parent_obj, dict) and (parent_obj.get("text") or parent_obj.get("full_text")):

        p_author = (

            (parent_obj.get("author") or {}).get("screen_name")

            or (parent_obj.get("user") or {}).get("screen_name")

            or parent_obj.get("user_screen_name")

            or "parent_user"

        )

        p_text = _normalise_verbatim_text(parent_obj.get("text") or parent_obj.get("full_text") or "")

        p_likes = int(parent_obj.get("likes") or parent_obj.get("favorite_count") or score)

        p_date = _utc_iso_date(parent_obj.get("created_timestamp") or parent_obj.get("created_at") or created_date)

        raw_comments.append(

            CommunityComment(

                comment_id=str(parent_obj.get("id", "parent_1")),

                author=f"@{p_author.lstrip('@')}",

                score=p_likes,

                created_date=p_date,

                body=f"[Parent Thread Context] {p_text}",

                depth=0,

            )

        )



    # Support explicit `replies_list` or `thread` arrays if present

    for idx, rep in enumerate(tweet_obj.get("replies_list") or tweet_obj.get("thread") or [], 1):

        if isinstance(rep, dict) and (rep.get("text") or rep.get("full_text")):

            r_author = (

                (rep.get("author") or {}).get("screen_name")

                or rep.get("user_screen_name")

                or f"reply_{idx}"

            )

            r_score = int(rep.get("likes") or rep.get("favorite_count") or 1)

            r_date = _utc_iso_date(rep.get("created_timestamp") or rep.get("created_at") or created_date)

            raw_comments.append(

                CommunityComment(

                    comment_id=str(rep.get("id", f"rep_{idx}")),

                    author=f"@{str(r_author).lstrip('@')}",

                    score=r_score,

                    created_date=r_date,

                    body=str(rep.get("text") or rep.get("full_text")),

                    depth=1,

                )

            )



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        min_chars=25,

        target_kind=target_kind,

        max_comments=20,

    )



    title = f"X Post by @{screen_name.lstrip('@')} ({display_name})"

    return CommunityThread(

        platform="X/Twitter",

        channel=f"@{screen_name.lstrip('@')}",

        url=source_url,

        title=title,

        author=f"@{screen_name.lstrip('@')}",

        score=score,

        created_date=created_date,

        op_body=clean_text,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

        metadata={"likes": likes, "retweets": retweets, "replies": replies_cnt},

    )





def fetch_x_post(

    url: str,

    min_score: int = 0,

    target_kind: str = "all",

    timeout: float = 15.0,

) -> CommunityThread:

    user, status_id = _extract_tweet_identity(url)

    endpoints = [

        f"https://api.fxtwitter.com/{user}/status/{status_id}",

        f"https://api.vxtwitter.com/{user}/status/{status_id}",

        f"https://cdn.syndication.twimg.com/tweet-result?id={status_id}&lang=en&token=a",

    ]

    last_err = ""

    for ep in endpoints:

        try:

            payload = _http_get_json(ep, timeout=timeout)

            if isinstance(payload, dict) and (

                payload.get("tweet") or payload.get("text") or payload.get("full_text")

            ):

                return parse_x_syndication_payload(

                    payload,

                    source_url=url,

                    min_score=min_score,

                    target_kind=target_kind,

                )

        except Exception as e:

            last_err = str(e)

    raise RuntimeError(f"All X/Twitter syndication endpoints failed for {url}: {last_err}")





# ---------------------------------------------------------------------------

# 3. Hacker News (HN Algolia REST API) Parser

# ---------------------------------------------------------------------------

def _extract_hn_item_id(url: str) -> str:

    m = re.search(r"(?:id=|/items/)(\d+)", url)

    if not m:

        raise ValueError(f"Cannot extract Hacker News item ID from URL: {url}")

    return m.group(1)





def parse_hn_algolia_payload(

    payload: dict[str, Any],

    source_url: str,

    min_score: int = 1,

    target_kind: str = "all",

    max_comments: int = 25,

) -> CommunityThread:

    """Parses a Hacker News Algolia `/api/v1/items/<id>` nested discussion tree."""

    title = _normalise_verbatim_text(payload.get("title") or "Hacker News Discussion")

    author = str(payload.get("author") or "hn_user")

    points = int(payload.get("points") or 1)

    created_date = _utc_iso_date(payload.get("created_at_i") or payload.get("created_at"))

    story_text = _clean_html_preserve_math_and_code(payload.get("text") or "")

    story_url = payload.get("url") or ""

    op_body = f"{title}. {story_text}".strip() if story_text else title

    if story_url:

        op_body = f"{op_body} (External Link: {story_url})"



    op_kind, op_proves, _, _, _ = classify_and_score_text(op_body, points)



    raw_comments: list[CommunityComment] = []



    def _walk_hn_children(children: list[dict[str, Any]], depth: int = 0) -> None:

        for idx, child in enumerate(children):

            if not isinstance(child, dict):

                continue

            c_text_raw = child.get("text") or ""

            if c_text_raw:

                c_body = _clean_html_preserve_math_and_code(c_text_raw)

                c_author = str(child.get("author") or "anon")

                # HN Algolia often omits comment points (`None`); estimate structural floor by depth/position

                raw_pts = child.get("points")

                c_score = int(raw_pts) if isinstance(raw_pts, (int, float)) else max(1, 5 - depth - (idx // 4))

                c_date = _utc_iso_date(child.get("created_at_i") or child.get("created_at") or created_date)

                c_id = str(child.get("id") or f"hn_{len(raw_comments)+1}")

                raw_comments.append(

                    CommunityComment(

                        comment_id=c_id,

                        author=c_author,

                        score=c_score,

                        created_date=c_date,

                        body=c_body,

                        depth=depth,

                    )

                )

            sub_children = child.get("children") or []

            if isinstance(sub_children, list) and sub_children:

                _walk_hn_children(sub_children, depth + 1)



    _walk_hn_children(payload.get("children") or [], depth=0)



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )



    return CommunityThread(

        platform="HackerNews",

        channel="news.ycombinator.com",

        url=source_url,

        title=title,

        author=author,

        score=points,

        created_date=created_date,

        op_body=op_body,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

    )





def fetch_hn_thread(

    url: str,

    min_score: int = 1,

    target_kind: str = "all",

    max_comments: int = 25,

    timeout: float = 15.0,

) -> CommunityThread:

    item_id = _extract_hn_item_id(url)

    api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"

    payload = _http_get_json(api_url, timeout=timeout)

    return parse_hn_algolia_payload(

        payload,

        source_url=url,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )





# ---------------------------------------------------------------------------

# 4. StackExchange & Quant.StackExchange Native Keyless API v2.3 Parser

# ---------------------------------------------------------------------------

def _extract_stackexchange_target(url: str) -> tuple[str, str]:

    """Returns (site_parameter, question_id) from any StackExchange network URL."""

    parsed = urllib.parse.urlparse(url)

    host = (parsed.hostname or "stackoverflow.com").lower()

    if host.startswith("www."):

        host = host[4:]



    # Map host to StackExchange API `site` slug

    if host.endswith(".stackexchange.com"):

        site = host.split(".")[0]

    elif host in ("stackoverflow.com", "serverfault.com", "superuser.com", "askubuntu.com", "mathoverflow.net"):

        site = host.split(".")[0]

    else:

        site = "quant" if "quant" in host else "stackoverflow"



    m = re.search(r"/questions/(\d+)", parsed.path)

    if not m:

        m = re.search(r"/q/(\d+)", parsed.path)

    if not m:

        raise ValueError(f"Cannot extract StackExchange question ID from URL: {url}")

    return site, m.group(1)





def parse_stackexchange_payload(

    q_payload: dict[str, Any],

    a_payload: dict[str, Any] | None,

    site: str,

    source_url: str,

    min_score: int = 1,

    target_kind: str = "all",

    max_comments: int = 20,

) -> CommunityThread:

    """Parses StackExchange question + answers JSON while keeping LaTeX ($...$) intact."""

    items = q_payload.get("items") or []

    if not items:

        raise ValueError("StackExchange question payload contains no items")

    q_item = items[0]

    title = _normalise_verbatim_text(q_item.get("title") or "StackExchange Question")

    owner = q_item.get("owner") or {}

    author = str(owner.get("display_name") or "se_user")

    score = int(q_item.get("score") or 0)

    created_date = _utc_iso_date(q_item.get("creation_date"))

    q_body = _clean_html_preserve_math_and_code(q_item.get("body") or "")

    tags = q_item.get("tags") or []

    op_body = f"{title}. {q_body}".strip() if q_body else title

    if tags:

        op_body = f"[Tags: {', '.join(tags)}] {op_body}"



    op_kind, op_proves, _, _, _ = classify_and_score_text(op_body, score)



    raw_comments: list[CommunityComment] = []

    a_items = (a_payload or {}).get("items") or q_item.get("answers") or []

    for ans in a_items:

        if not isinstance(ans, dict):

            continue

        a_id = str(ans.get("answer_id") or f"ans_{len(raw_comments)+1}")

        a_owner = ans.get("owner") or {}

        a_author = str(a_owner.get("display_name") or "se_expert")

        a_score = int(ans.get("score") or 0)

        is_accepted = bool(ans.get("is_accepted"))

        effective_score = a_score + (15 if is_accepted else 0)

        a_date = _utc_iso_date(ans.get("creation_date") or created_date)

        a_body = _clean_html_preserve_math_and_code(ans.get("body") or "")

        if is_accepted:

            a_body = f"[Accepted Answer] {a_body}"

        raw_comments.append(

            CommunityComment(

                comment_id=a_id,

                author=a_author,

                score=effective_score,

                created_date=a_date,

                body=a_body,

                depth=0,

            )

        )



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )



    return CommunityThread(

        platform="StackExchange",

        channel=f"{site}.stackexchange",

        url=source_url,

        title=title,

        author=author,

        score=score,

        created_date=created_date,

        op_body=op_body,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

        metadata={"tags": tags},

    )





def fetch_stackexchange_thread(

    url: str,

    min_score: int = 1,

    target_kind: str = "all",

    max_comments: int = 20,

    timeout: float = 15.0,

) -> CommunityThread:

    site, qid = _extract_stackexchange_target(url)

    base = "https://api.stackexchange.com/2.3"

    q_url = f"{base}/questions/{qid}?order=desc&sort=activity&site={site}&filter={STACKEXCHANGE_BUILTIN_WITHBODY_FILTER}"

    a_url = f"{base}/questions/{qid}/answers?order=desc&sort=votes&site={site}&filter={STACKEXCHANGE_BUILTIN_WITHBODY_FILTER}"

    q_payload = _http_get_json(q_url, timeout=timeout)

    a_payload = _http_get_json(a_url, timeout=timeout)

    return parse_stackexchange_payload(

        q_payload,

        a_payload,

        site=site,

        source_url=url,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )





# ---------------------------------------------------------------------------

# 5. Modern Discourse Forum JSON Parser (`<domain>/t/<slug>/<id>.json`)

# ---------------------------------------------------------------------------

def _discourse_json_url(url: str) -> str:

    parsed = urllib.parse.urlparse(url)

    path = parsed.path.rstrip("/")

    # Strip trailing post index `/t/slug/123/4` -> `/t/slug/123.json`

    m = re.match(r"^(/t/[^/]+/\d+)(?:/\d+)?$", path)

    if m:

        path = m.group(1)

    if not path.endswith(".json"):

        path = f"{path}.json"

    return urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc, path, "", "", ""))





def parse_discourse_json_payload(

    payload: dict[str, Any],

    source_url: str,

    min_score: int = 0,

    target_kind: str = "all",

    max_comments: int = 25,

) -> CommunityThread:

    """Parses a Discourse `/t/<slug>/<id>.json` topic payload."""

    parsed_url = urllib.parse.urlparse(source_url)

    channel = parsed_url.hostname or "discourse.forum"

    title = _normalise_verbatim_text(payload.get("title") or payload.get("fancy_title") or "Discourse Topic")

    posts = (payload.get("post_stream") or {}).get("posts") or []

    if not posts:

        raise ValueError("Discourse JSON payload contains no posts in post_stream")



    op_post = posts[0]

    op_author = str(op_post.get("username") or op_post.get("name") or "op_user")

    op_likes = int(op_post.get("like_count") or payload.get("like_count") or 0)

    op_reads = int(op_post.get("reads") or 1)

    op_score = op_likes + max(1, int(op_post.get("score") or (op_reads // 10)))

    created_date = _utc_iso_date(op_post.get("created_at") or payload.get("created_at"))

    op_cooked = _clean_html_preserve_math_and_code(op_post.get("cooked") or "")

    op_body = f"{title}. {op_cooked}".strip() if op_cooked else title

    op_kind, op_proves, _, _, _ = classify_and_score_text(op_body, op_score)



    raw_comments: list[CommunityComment] = []

    for p in posts[1:]:

        if not isinstance(p, dict):

            continue

        c_cooked = _clean_html_preserve_math_and_code(p.get("cooked") or "")

        c_author = str(p.get("username") or "member")

        c_likes = int(p.get("like_count") or 0)

        c_reads = int(p.get("reads") or 1)

        c_score = c_likes + max(1, int(p.get("score") or (c_reads // 15)))

        c_date = _utc_iso_date(p.get("created_at") or created_date)

        c_id = str(p.get("id") or p.get("post_number") or len(raw_comments) + 1)

        raw_comments.append(

            CommunityComment(

                comment_id=c_id,

                author=c_author,

                score=c_score,

                created_date=c_date,

                body=c_cooked,

                depth=1 if p.get("reply_to_post_number") else 0,

            )

        )



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )



    return CommunityThread(

        platform="Discourse",

        channel=channel,

        url=source_url,

        title=title,

        author=op_author,

        score=op_score,

        created_date=created_date,

        op_body=op_body,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

    )





def fetch_discourse_thread(

    url: str,

    min_score: int = 0,

    target_kind: str = "all",

    max_comments: int = 25,

    timeout: float = 15.0,

) -> CommunityThread:

    json_url = _discourse_json_url(url)

    payload = _http_get_json(json_url, timeout=timeout)

    return parse_discourse_json_payload(

        payload,

        source_url=url,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )





# ---------------------------------------------------------------------------

# 6. GitHub Issues & Discussions Keyless REST Parser

# ---------------------------------------------------------------------------

def _extract_github_issue_target(url: str) -> tuple[str, str, str]:

    m = re.search(r"github\.com/([^/]+)/([^/]+)/(?:issues|pull|discussions)/(\d+)", url, re.I)

    if not m:

        raise ValueError(f"Cannot extract GitHub owner/repo/number from URL: {url}")

    return m.group(1), m.group(2), m.group(3)





def fetch_github_issue_thread(

    url: str,

    min_score: int = 0,

    target_kind: str = "all",

    max_comments: int = 25,

    timeout: float = 15.0,

) -> CommunityThread:

    owner, repo, num = _extract_github_issue_target(url)

    gh_headers = {"Accept": "application/vnd.github+json", "User-Agent": REDDIT_USER_AGENT}

    issue_api = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"

    comm_api = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}/comments?per_page=50"



    issue_data = _http_get_json(issue_api, headers=gh_headers, timeout=timeout)

    comm_data = _http_get_json(comm_api, headers=gh_headers, timeout=timeout)



    title = _normalise_verbatim_text(issue_data.get("title") or f"GitHub Issue #{num}")

    author = str((issue_data.get("user") or {}).get("login") or "gh_user")

    reactions = (issue_data.get("reactions") or {}).get("total_count") or 0

    score = int(reactions) + 1

    created_date = _utc_iso_date(issue_data.get("created_at"))

    body_text = _normalise_verbatim_text(issue_data.get("body") or "")

    op_body = f"{title}. {body_text}".strip() if body_text else title

    op_kind, op_proves, _, _, _ = classify_and_score_text(op_body, score)



    raw_comments: list[CommunityComment] = []

    if isinstance(comm_data, list):

        for idx, c in enumerate(comm_data, 1):

            if not isinstance(c, dict):

                continue

            c_author = str((c.get("user") or {}).get("login") or "contributor")

            c_react = int((c.get("reactions") or {}).get("total_count") or 0) + 1

            c_date = _utc_iso_date(c.get("created_at") or created_date)

            c_body = _normalise_verbatim_text(c.get("body") or "")

            raw_comments.append(

                CommunityComment(

                    comment_id=str(c.get("id") or f"gh_{idx}"),

                    author=f"@{c_author}",

                    score=c_react,

                    created_date=c_date,

                    body=c_body,

                    depth=0,

                )

            )



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )



    return CommunityThread(

        platform="GitHub",

        channel=f"{owner}/{repo}",

        url=url,

        title=title,

        author=f"@{author}",

        score=score,

        created_date=created_date,

        op_body=op_body,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

    )





# ---------------------------------------------------------------------------

# 7. Generic Forum Thread Extractor (XenForo, vBulletin, phpBB, Forex Factory,

#    Elite Trader, Wilmott, HealthUnlocked, Inspire)

# ---------------------------------------------------------------------------

def parse_generic_forum_html(

    raw_html: str,

    source_url: str,

    min_score: int = 0,

    target_kind: str = "all",

    max_comments: int = 25,

) -> CommunityThread:

    """Extracts thread title, OP post, and replies from XenForo, vBulletin, phpBB,

    Forex Factory, and patient/practitioner forums while stripping signatures and chrome."""

    parsed_url = urllib.parse.urlparse(source_url)

    channel = (parsed_url.hostname or "forum").removeprefix("www.")



    # Extract <title>

    m_title = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)

    title = _clean_html_preserve_math_and_code(m_title.group(1)) if m_title else f"Forum Thread ({channel})"



    # Strip signatures, avatars, user-info sidebars, blockquotes, and nav bars before post extraction

    cleaned_dom = re.sub(

        r'(?is)<(?:div|aside|section|footer)[^>]+(?:class|id)\s*=\s*["\'][^"\']*'

        r'(?:signature|sig\b|avatar|userbanner|postbit-userinfo|message-userDetails|'

        r'bbCodeBlock--quote|quotecontainer|nav| breadcrumb|sidebar|footer)[^"\']*["\'][^>]*>.*?</(?:div|aside|section|footer)>',

        " ",

        raw_html,

    )



    # Extract candidate post containers across XenForo, vBulletin, phpBB, Forex Factory, HealthUnlocked

    post_patterns = (

        # XenForo / Elite Trader / Futures.io (`<article class="message ...">`)

        re.compile(

            r'(?is)<article[^>]+(?:data-author\s*=\s*["\']([^"\']+)["\'])?[^>]*class\s*=\s*["\'][^"\']*message\b[^"\']*["\'][^>]*>(.*?)</article>'

        ),

        # vBulletin / Forex Factory (`<div id="post_message_..."` or `class="postbody"`)

        re.compile(

            r'(?is)<div[^>]+(?:data-username\s*=\s*["\']([^"\']+)["\'])?[^>]*'

            r'(?:id\s*=\s*["\']post_message_\d+["\']|class\s*=\s*["\'][^"\']*(?:postbody|post_message|messageContent|post-content|comment-body)[^"\']*["\'])[^>]*>(.*?)</div>'

        ),

        # phpBB (`<div class="content">`)

        re.compile(

            r'(?is)<div[^>]+(?:data-author\s*=\s*["\']([^"\']+)["\'])?[^>]*class\s*=\s*["\']content["\'][^>]*>(.*?)</div>'

        ),

    )



    extracted_posts: list[tuple[str, str, str]] = []

    for pat in post_patterns:

        matches = pat.findall(cleaned_dom)

        if matches:

            for idx, (auth_hint, inner_html) in enumerate(matches, 1):

                author = auth_hint.strip() if auth_hint else ""

                if not author:

                    m_auth = re.search(

                        r'(?is)(?:data-author|data-username|class\s*=\s*["\'][^"\']*(?:username|author)[^"\']*["\'][^>]*>)\s*["\']?([A-Za-z0-9_.-]{2,30})',

                        inner_html,

                    )

                    author = m_auth.group(1) if m_auth else f"practitioner_{idx}"

                m_time = re.search(r'((?:19|20)\d{2}-\d{2}-\d{2})', inner_html)

                p_date = m_time.group(1) if m_time else dt.date.today().isoformat()

                body_txt = _clean_html_preserve_math_and_code(inner_html)

                if len(body_txt) >= 40:

                    extracted_posts.append((author, p_date, body_txt))

            if extracted_posts:

                break



    # Fallback: extract substantive paragraphs if custom forum markup was used

    if not extracted_posts:

        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", cleaned_dom)

        for idx, p_html in enumerate(paras, 1):

            p_txt = _clean_html_preserve_math_and_code(p_html)

            if len(p_txt) >= 65:

                extracted_posts.append((f"member_{idx}", dt.date.today().isoformat(), p_txt))



    if not extracted_posts:

        stripped_all = _clean_html_preserve_math_and_code(cleaned_dom)

        extracted_posts.append(("forum_op", dt.date.today().isoformat(), stripped_all[:2000]))



    op_author, op_date, op_text = extracted_posts[0]

    op_body = f"{title}. {op_text}".strip() if op_text else title

    op_kind, op_proves, _, _, _ = classify_and_score_text(op_body, 5)



    raw_comments: list[CommunityComment] = []

    for idx, (c_auth, c_date, c_txt) in enumerate(extracted_posts[1:], 1):

        raw_comments.append(

            CommunityComment(

                comment_id=f"post_{idx+1}",

                author=c_auth,

                score=max(1, 10 - idx),

                created_date=c_date,

                body=c_txt,

                depth=0,

            )

        )



    kept_comments, dropped_count = filter_and_rank_comments(

        raw_comments,

        min_score=min_score,

        target_kind=target_kind,

        max_comments=max_comments,

    )



    return CommunityThread(

        platform="ForumThread",

        channel=channel,

        url=source_url,

        title=title,

        author=op_author,

        score=10,

        created_date=op_date,

        op_body=op_body,

        op_kind=op_kind,

        op_proves=op_proves,

        comments=kept_comments,

        raw_comment_count=len(raw_comments),

        filtered_noise_count=dropped_count,

    )





# ---------------------------------------------------------------------------

# Snapshot Formatter (100% Verbatim Grounding & BM25 Passage Compatible)

# ---------------------------------------------------------------------------

def format_thread_to_snapshot(thread: CommunityThread) -> str:

    """Formats a `CommunityThread` into a deterministic `sources/S###.txt` snapshot.



    Each comment is emitted as a standalone blank-line-separated paragraph (`>= 60` chars)

    so `lean_engine.py`'s `rank_bm25_passages` indexes every comment cleanly and

    `quote_matches_snapshot` verifies substrings verbatim without regex mismatch.

    """

    lines: list[str] = [

        "=== PRACTITIONER COMMUNITY SNAPSHOT ===",

        f"Source Platform: {thread.platform} | Channel: {thread.channel} | URL: {thread.url}",

        (

            f"Author: {thread.author} | Score: {thread.score} | Timestamp: {thread.created_date} | "

            f"Epistemic Kind: {thread.op_kind} (Proves: {thread.op_proves})"

        ),

        (

            f"Signal Filter Summary: Kept {len(thread.comments)} high-signal comments "

            f"(Dropped {thread.filtered_noise_count} low-score/shill noise items)"

        ),

        "",

        (

            f"[OP Post by {thread.author} (Score: {thread.score}, Date: {thread.created_date}, "

            f"Kind: {thread.op_kind}, Proves: {thread.op_proves})]"

        ),

        f'"{thread.op_body}"',

        "",

        "--- High-Signal Comments ---",

        "",

    ]



    for c in thread.comments:

        lines.append(

            f"[Comment by {c.author} (Score: {c.score}, Date: {c.created_date}, "

            f"Kind: {c.kind}, Proves: {c.proves}, Signal: {c.signal_score})]: "

            f'"{c.body}"'

        )

        lines.append("")



    return "\n".join(lines).strip() + "\n"





# ---------------------------------------------------------------------------

# URL Router & Unified Dispatcher (`is_community_url` / `fetch_community_url`)

# ---------------------------------------------------------------------------

COMMUNITY_HOST_PATTERNS = re.compile(

    r"(?:^|\.)(?:"

    r"reddit\.com|redd\.it|twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com|"

    r"news\.ycombinator\.com|hn\.algolia\.com|stackexchange\.com|stackoverflow\.com|"

    r"serverfault\.com|superuser\.com|askubuntu\.com|mathoverflow\.net|"

    r"lobste\.rs|producthunt\.com|forexfactory\.com|elitetrader\.com|futures\.io|"

    r"wilmott\.com|healthunlocked\.com|inspire\.com"

    r")$",

    re.I,

)





def detect_community_platform(url: str) -> str | None:

    """Identifies if `url` is a practitioner/community thread and returns its router key."""

    parsed = urllib.parse.urlparse(url)

    host = (parsed.hostname or "").lower()

    path = parsed.path or ""



    if re.search(r"(?:^|\.)(?:reddit\.com|redd\.it)$", host):

        return "reddit"

    if re.search(r"(?:^|\.)(?:twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com)$", host) and "/status" in path:

        return "x"

    if host in ("news.ycombinator.com", "hn.algolia.com") and ("id=" in parsed.query or "/items/" in path):

        return "hn"

    if re.search(

        r"(?:^|\.)(?:stackexchange\.com|stackoverflow\.com|serverfault\.com|superuser\.com|askubuntu\.com|mathoverflow\.net)$",

        host,

    ) and ("/questions/" in path or "/q/" in path):

        return "stackexchange"

    if host == "github.com" and re.search(r"/[^/]+/[^/]+/(?:issues|pull|discussions)/\d+", path):

        return "github"

    if re.match(r"^/t/[^/]+/\d+", path):

        return "discourse"

    if COMMUNITY_HOST_PATTERNS.search(host) or any(

        tok in path.lower() for tok in ("/threads/", "/thread/", "/topic/", "/t/", "/forums/", "/discussions/")

    ):

        return "forum"

    return None





def fetch_community_url(

    url: str,

    min_score: int = 1,

    target_kind: str = "all",

    max_comments: int = 25,

    timeout: float = 18.0,

) -> dict[str, Any]:

    """Unified entry point for `lean_engine.py`'s `_fetch_single_url`.



    Returns:

        {"ok": bool, "url": str, "text": str, "status": int | None, "error": str, "thread": CommunityThread | None}

    """

    platform = detect_community_platform(url)

    try:

        if platform == "reddit":

            thread = fetch_reddit_thread(

                url, min_score=max(1, min_score), target_kind=target_kind, max_comments=max_comments, timeout=timeout

            )

        elif platform == "x":

            thread = fetch_x_post(url, min_score=min_score, target_kind=target_kind, timeout=timeout)

        elif platform == "hn":

            thread = fetch_hn_thread(

                url, min_score=min_score, target_kind=target_kind, max_comments=max_comments, timeout=timeout

            )

        elif platform == "stackexchange":

            thread = fetch_stackexchange_thread(

                url, min_score=min_score, target_kind=target_kind, max_comments=max_comments, timeout=timeout

            )

        elif platform == "discourse":

            thread = fetch_discourse_thread(

                url, min_score=min_score, target_kind=target_kind, max_comments=max_comments, timeout=timeout

            )

        elif platform == "github":

            thread = fetch_github_issue_thread(

                url, min_score=min_score, target_kind=target_kind, max_comments=max_comments, timeout=timeout

            )

        else:

            # Try Discourse `.json` first if `/t/` path, else generic HTML forum extractor

            status, _, raw_html = _http_get_raw(url, timeout=timeout)

            thread = parse_generic_forum_html(

                raw_html,

                source_url=url,

                min_score=min_score,

                target_kind=target_kind,

                max_comments=max_comments,

            )



        snapshot_txt = format_thread_to_snapshot(thread)

        return {

            "ok": len(snapshot_txt) >= 120,

            "url": url,

            "text": snapshot_txt,

            "status": 200,

            "error": "",

            "thread": thread,

        }

    except Exception as e:

        return {

            "ok": False,

            "url": url,

            "text": "",

            "status": None,

            "error": f"community_engine ({platform or 'generic'}): {str(e)[:160]}",

            "thread": None,

        }





# ---------------------------------------------------------------------------

# Keyless Multi-Platform Community Search (`search` subcommand)

# ---------------------------------------------------------------------------

def search_community_discussions(

    query: str,

    platforms: list[str] | None = None,

    target_kind: str = "all",

    limit_per_platform: int = 5,

    timeout: float = 15.0,

) -> list[dict[str, Any]]:

    """Queries keyless Reddit JSON, Hacker News Algolia, and StackExchange search APIs."""

    active_platforms = platforms or ["reddit", "hn", "stackexchange"]

    q_enc = urllib.parse.quote_plus(query)

    results: list[dict[str, Any]] = []



    if "reddit" in active_platforms:

        try:

            r_url = f"https://www.reddit.com/search.json?q={q_enc}&sort=relevance&t=all&limit={limit_per_platform}&raw_json=1"

            r_data = _http_get_json(r_url, headers={"User-Agent": REDDIT_USER_AGENT}, timeout=timeout)

            for child in (r_data.get("data") or {}).get("children") or []:

                d = child.get("data") or {}

                title = _normalise_verbatim_text(d.get("title") or "")

                selftext = _normalise_verbatim_text(d.get("selftext") or "")

                combined = f"{title}. {selftext}".strip()

                score = int(d.get("score") or 0)

                kind, proves, sig, _, _ = classify_and_score_text(combined, score)

                if target_kind not in ("all", kind):

                    continue

                permalink = d.get("permalink") or ""

                full_url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else d.get("url", "")

                results.append({

                    "platform": "Reddit",

                    "channel": d.get("subreddit_name_prefixed") or f"r/{d.get('subreddit', '')}",

                    "title": title,

                    "url": full_url,

                    "score": score,

                    "date": _utc_iso_date(d.get("created_utc")),

                    "kind": kind,

                    "proves": proves,

                    "signal_score": sig,

                })

        except Exception:

            pass



    if "hn" in active_platforms:

        try:

            hn_url = f"https://hn.algolia.com/api/v1/search?query={q_enc}&tags=story&hitsPerPage={limit_per_platform}"

            hn_data = _http_get_json(hn_url, timeout=timeout)

            for hit in hn_data.get("hits") or []:

                title = _normalise_verbatim_text(hit.get("title") or "")

                points = int(hit.get("points") or 0)

                kind, proves, sig, _, _ = classify_and_score_text(title, points)

                if target_kind not in ("all", kind):

                    continue

                obj_id = hit.get("objectID")

                results.append({

                    "platform": "HackerNews",

                    "channel": "news.ycombinator.com",

                    "title": title,

                    "url": f"https://news.ycombinator.com/item?id={obj_id}",

                    "score": points,

                    "date": _utc_iso_date(hit.get("created_at_i") or hit.get("created_at")),

                    "kind": kind,

                    "proves": proves,

                    "signal_score": sig,

                })

        except Exception:

            pass



    if "stackexchange" in active_platforms:

        try:

            site = "quant" if any(k in query.lower() for k in ("0dte", "gamma", "sharpe", "volatility", "slippage", "futures")) else "stackoverflow"

            se_url = f"https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=votes&q={q_enc}&site={site}&pagesize={limit_per_platform}"

            se_data = _http_get_json(se_url, timeout=timeout)

            for item in se_data.get("items") or []:

                title = _normalise_verbatim_text(item.get("title") or "")

                score = int(item.get("score") or 0)

                kind, proves, sig, _, _ = classify_and_score_text(title, score)

                if target_kind not in ("all", kind):

                    continue

                results.append({

                    "platform": "StackExchange",

                    "channel": f"{site}.stackexchange",

                    "title": title,

                    "url": item.get("link") or f"https://{site}.stackexchange.com/questions/{item.get('question_id')}",

                    "score": score,

                    "date": _utc_iso_date(item.get("creation_date")),

                    "kind": kind,

                    "proves": proves,

                    "signal_score": sig,

                })

        except Exception:

            pass



    results.sort(key=lambda r: (r["signal_score"], r["score"]), reverse=True)

    return results





# ---------------------------------------------------------------------------

# CLI Commands (`fetch`, `search`, `flatten`, `selftest`)

# ---------------------------------------------------------------------------

def cmd_fetch(args: argparse.Namespace) -> int:

    res = fetch_community_url(

        args.url,

        min_score=args.min_score,

        target_kind=args.kind,

        max_comments=args.max_comments,

    )

    if not res["ok"]:

        print(f"ERROR: {res['error']}", file=sys.stderr)

        return 1

    if args.out:

        out_path = Path(args.out)

        out_path.parent.mkdir(parents=True, exist_ok=True)

        out_path.write_text(res["text"], encoding="utf-8")

        print(f"[FETCH OK] Wrote {len(res['text'])} chars -> {out_path}")

    else:

        print(res["text"])

    return 0





def cmd_search(args: argparse.Namespace) -> int:

    platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]

    hits = search_community_discussions(

        args.query,

        platforms=platforms,

        target_kind=args.kind,

        limit_per_platform=args.limit,

    )

    if args.json:

        print(json.dumps(hits, ensure_ascii=False, indent=2))

    else:

        print(f"# Community Discovery Hits for {args.query!r} (kind={args.kind}, n={len(hits)})")

        for idx, h in enumerate(hits, 1):

            print(

                f"{idx:2d}. [{h['platform']} | {h['channel']}] (Score: {h['score']}, "

                f"Kind: {h['kind']}, Signal: {h['signal_score']}) {h['title']}\n    URL: {h['url']}"

            )

    return 0





def cmd_flatten(args: argparse.Namespace) -> int:

    in_path = Path(args.input)

    if not in_path.exists():

        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)

        return 2

    raw = in_path.read_text(encoding="utf-8", errors="replace")

    fmt = args.format.lower()



    if fmt in ("reddit", "x", "hn", "discourse", "stackexchange"):

        payload = json.loads(raw)

        if fmt == "reddit":

            thread = parse_reddit_json_payload(payload, args.url, min_score=args.min_score, target_kind=args.kind)

        elif fmt == "x":

            thread = parse_x_syndication_payload(payload, args.url, min_score=args.min_score, target_kind=args.kind)

        elif fmt == "hn":

            thread = parse_hn_algolia_payload(payload, args.url, min_score=args.min_score, target_kind=args.kind)

        elif fmt == "discourse":

            thread = parse_discourse_json_payload(payload, args.url, min_score=args.min_score, target_kind=args.kind)

        else:

            thread = parse_stackexchange_payload(

                payload, None, site="quant", source_url=args.url, min_score=args.min_score, target_kind=args.kind

            )

    else:

        thread = parse_generic_forum_html(raw, args.url, min_score=args.min_score, target_kind=args.kind)



    snap = format_thread_to_snapshot(thread)

    if args.out:

        out_path = Path(args.out)

        out_path.parent.mkdir(parents=True, exist_ok=True)

        out_path.write_text(snap, encoding="utf-8")

        print(f"[FLATTEN OK] Wrote {len(snap)} chars -> {out_path}")

    else:

        print(snap)

    return 0





def cmd_selftest(_args: argparse.Namespace) -> int:

    """Zero-mock, < 50 ms verification of Reddit, X, HN, StackExchange, Discourse, and Noise Gate."""

    t0 = time.perf_counter()



    # 1. Synthetic Reddit JSON payload (with nested comments, shill noise, and negative-karma noise)

    reddit_payload = [

        {

            "data": {

                "children": [

                    {

                        "kind": "t3",

                        "data": {

                            "subreddit_name_prefixed": "r/algotrading",

                            "title": "0DTE SPX Execution Slippage and Spread Widening on M15",

                            "selftext": (

                                "During FOMC and cash close, top-of-book spread widens from 0.8 bps to 3.4 bps "

                                "with 1.9 bps adverse fill slippage per side."

                            ),

                            "author": "quant_execution_op",

                            "score": 142,

                            "created_utc": 1778371200,  # 2026-05-10

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

                            "id": "c_pain_1",

                            "author": "prop_desk_vet",

                            "score": 68,

                            "created_utc": 1778374800,

                            "body": (

                                "We measured 2.6 bps execution slippage on market orders and canceled our "

                                "retail broker routing due to hidden requote delays during gamma flips."

                            ),

                            "replies": {

                                "data": {

                                    "children": [

                                        {

                                            "kind": "t1",

                                            "data": {

                                                "id": "c_tech_2",

                                                "author": "lob_architect",

                                                "score": 45,

                                                "created_utc": 1778378400,

                                                "body": (

                                                    "The deterministic workaround is pegging midpoint limit orders "

                                                    "when net dealer GEX drops below -2.5 billion USD (`gex_bn < -2.5`), "

                                                    "cutting p99 fill slippage to 0.4 bps."

                                                ),

                                                "replies": "",

                                            },

                                        }

                                    ]

                                }

                            },

                        },

                    },

                    {

                        "kind": "t1",

                        "data": {

                            "id": "c_shill_noise",

                            "author": "crypto_moon_bot",

                            "score": 99,

                            "created_utc": 1778379000,

                            "body": "Join my Telegram VIP group for guaranteed 50% daily signals! https://t.me/+shill123",

                            "replies": "",

                        },

                    },

                    {

                        "kind": "t1",

                        "data": {

                            "id": "c_neg_noise",

                            "author": "retail_gambler",

                            "score": -4,

                            "created_utc": 1778379500,

                            "body": "Unfiltered RSI crossover works 100% of the time on 1-minute charts.",

                            "replies": "",

                        },

                    },

                ]

            }

        },

    ]



    r_thread = parse_reddit_json_payload(

        reddit_payload,

        source_url="https://www.reddit.com/r/algotrading/comments/xyz/0dte_slippage",

        min_score=2,

        target_kind="all",

    )

    assert r_thread.platform == "Reddit"

    assert r_thread.channel == "r/algotrading"

    assert r_thread.created_date == "2026-05-10"

    assert len(r_thread.comments) == 2, f"Expected 2 kept comments (shill + neg dropped), got {len(r_thread.comments)}"

    assert r_thread.filtered_noise_count == 2

    by_id = {c.comment_id: c for c in r_thread.comments}

    assert by_id["c_pain_1"].kind == "review_pain"

    assert by_id["c_pain_1"].proves == "incumbent_weakness"

    assert by_id["c_tech_2"].kind == "technical_lead"

    assert by_id["c_tech_2"].proves == "architectural_workaround"



    r_snap = format_thread_to_snapshot(r_thread)

    assert "[OP Post by u/quant_execution_op (Score: 142, Date: 2026-05-10" in r_snap

    assert "--- High-Signal Comments ---" in r_snap

    assert "pegging midpoint limit orders when net dealer GEX drops below -2.5 billion USD" in r_snap



    # 2. Synthetic X / Twitter Syndication JSON payload (`api.fxtwitter.com` structure)

    x_payload = {

        "code": 200,

        "tweet": {

            "id": "192001234567890",

            "text": (

                "Dealer 0DTE gamma pinning compressed realized S&P 500 volatility by 34% "

                "whenever net GEX exceeded +3.0bn USD across 250 sessions. https://bit.ly/aff_track"

            ),

            "created_timestamp": 1778371200,

            "likes": 310,

            "retweets": 85,

            "replies": 24,

            "author": {"screen_name": "derivs_micro", "name": "Derivatives Flow Desk"},

            "quote": {

                "id": "191999888777",

                "text": "Cash close MOC imbalances above $500M force short-gamma dealers to hedge into the close.",

                "likes": 190,

                "created_timestamp": 1778360000,

                "author": {"screen_name": "cboe_flow_quant"},

            },

        },

    }

    x_thread = parse_x_syndication_payload(x_payload, source_url="https://x.com/derivs_micro/status/192001234567890")

    assert x_thread.platform == "X/Twitter"

    assert x_thread.score == 310 + (2 * 85)

    assert "[affiliate-link-stripped]" in x_thread.op_body

    assert len(x_thread.comments) == 1

    assert x_thread.comments[0].author == "@cboe_flow_quant"



    # 3. Synthetic Hacker News Algolia JSON payload

    hn_payload = {

        "id": 41234567,

        "title": "Show HN: Deterministic in-browser WASM preflight parser for B2B tax XML",

        "author": "systems_founder",

        "points": 215,

        "created_at_i": 1778371200,

        "text": "<p>We replaced fragile two-way syncs with a zero-liability read-only AST validator.</p>",

        "children": [

            {

                "id": 41234600,

                "author": "saas_cto",

                "points": 54,

                "created_at_i": 1778372000,

                "text": (

                    "<p>Our legacy vendor had a 14% monthly billing error rate and API quota lock-in; "

                    "switching to a deterministic preflight diff reduced support tickets by 78%.</p>"

                ),

                "children": [],

            },

            {

                "id": 41234601,

                "author": "low_effort_user",

                "points": 1,

                "created_at_i": 1778372100,

                "text": "<p>+1</p>",

                "children": [],

            },

        ],

    }

    hn_thread = parse_hn_algolia_payload(hn_payload, source_url="https://news.ycombinator.com/item?id=41234567")

    assert hn_thread.platform == "HackerNews"

    assert len(hn_thread.comments) == 1

    assert hn_thread.comments[0].kind == "review_pain"

    assert hn_thread.comments[0].proves == "incumbent_weakness"



    # 4. Synthetic StackExchange JSON payload (preserving LaTeX math)

    se_q = {

        "items": [

            {

                "question_id": 88901,

                "title": "Ornstein-Uhlenbeck half-life estimation bias under microstructure noise",

                "score": 32,

                "creation_date": 1778371200,

                "tags": ["market-microstructure", "ornstein-uhlenbeck"],

                "owner": {"display_name": "stat_arb_researcher"},

                "body": "<p>When estimating $dX_t = \\theta (\\mu - X_t)dt + \\sigma dW_t$ on M15 bars, bid-ask bounce biases $\\hat{\\theta}$.</p>",

            }

        ]

    }

    se_a = {

        "items": [

            {

                "answer_id": 88905,

                "score": 41,

                "is_accepted": True,

                "creation_date": 1778374000,

                "owner": {"display_name": "stochastic_calculus_phd"},

                "body": "<p>Use the Newey-West pre-averaged estimator with half-life $t_{1/2} = \\frac{\\ln(2)}{\\theta}$ and filter spreads above 2.5 bps.</p>",

            }

        ]

    }

    se_thread = parse_stackexchange_payload(

        se_q, se_a, site="quant", source_url="https://quant.stackexchange.com/questions/88901/ou-bias"

    )

    assert "$t_{1/2} = \\frac{\\ln(2)}{\\theta}$" in se_thread.comments[0].body



    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 50.0, f"Selftest exceeded 50ms budget: {elapsed_ms:.2f}ms"

    print(

        f"[SELFTEST PASS] community_engine v9.0 verified Reddit, X, HN, StackExchange & Noise Gate "

        f"in {elapsed_ms:.2f} ms (< 50.0 ms)."

    )

    return 0





def build_arg_parser() -> argparse.ArgumentParser:

    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])

    sub = ap.add_subparsers(dest="cmd", required=True)



    p_fetch = sub.add_parser("fetch", help="Fetch and format a community thread URL into a deterministic snapshot")

    p_fetch.add_argument("--url", required=True, help="Target Reddit, X, HN, StackExchange, Discourse, or Forum URL")

    p_fetch.add_argument("--kind", choices=["all", "review_pain", "technical_lead"], default="all")

    p_fetch.add_argument("--min-score", type=int, default=1, help="Minimum comment score/upvote floor")

    p_fetch.add_argument("--max-comments", type=int, default=25)

    p_fetch.add_argument("--out", help="Output snapshot file path (e.g., sources/S001.txt)")

    p_fetch.set_defaults(fn=cmd_fetch)



    p_search = sub.add_parser("search", help="Search Reddit, Hacker News, and StackExchange without API keys")

    p_search.add_argument("--query", required=True, help="Search query string")

    p_search.add_argument("--platforms", default="reddit,hn,stackexchange", help="Comma-separated platforms")

    p_search.add_argument("--kind", choices=["all", "review_pain", "technical_lead"], default="all")

    p_search.add_argument("--limit", type=int, default=5, help="Results per platform")

    p_search.add_argument("--json", action="store_true", help="Output JSON list")

    p_search.set_defaults(fn=cmd_search)



    p_flat = sub.add_parser("flatten", help="Flatten a saved local JSON/HTML file into a verifier-ready snapshot")

    p_flat.add_argument("--input", required=True, help="Path to raw JSON or HTML file")

    p_flat.add_argument(

        "--format",

        choices=["reddit", "x", "hn", "stackexchange", "discourse", "html"],

        required=True,

    )

    p_flat.add_argument("--url", default="https://local.snapshot/thread", help="Canonical source URL")

    p_flat.add_argument("--kind", choices=["all", "review_pain", "technical_lead"], default="all")

    p_flat.add_argument("--min-score", type=int, default=1)

    p_flat.add_argument("--out", help="Output snapshot file path")

    p_flat.set_defaults(fn=cmd_flatten)



    p_st = sub.add_parser("selftest", help="Run zero-mock synthetic verification (< 50 ms)")

    p_st.set_defaults(fn=cmd_selftest)



    return ap





def main(argv: list[str] | None = None) -> int:

    if hasattr(sys.stdout, "reconfigure"):

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = build_arg_parser()

    args = ap.parse_args(argv)

    return args.fn(args)





if __name__ == "__main__":

    sys.exit(main())
