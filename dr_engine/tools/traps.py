"""Institutional quality standards and validation logic for deep research.

Enforces:
1. Source Tier Integrity: Prevents Source Tier Inflation (marking community/blog/personal repos as T1/T2).
2. Probability Calibration: Catches uncalibrated subjective probability intervals or Bayesian priors.
3. Known Killed Edges / Traps Registry: Prevents asserting edges killed in lab data (e.g. London 4 PM Fix Reversal)
   and fallacious legal/contract analogies (e.g. Baštová / Natural Person KYC).

Stdlib only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_TRAPS_FILE = Path(__file__).resolve().parent / "known_traps.json"

COMMUNITY_DOMAINS = {
    "reddit.com", "twitter.com", "x.com", "youtube.com", "youtu.be",
    "trustpilot.com", "discord.com", "discord.gg", "discordapp.com",
    "quora.com", "medium.com", "substack.com", "wordpress.com",
    "blogspot.com", "blogger.com", "t.me", "telegram.org", "pastebin.com",
    "patreon.com", "tiktok.com", "instagram.com", "facebook.com", "fb.com",
    "linkedin.com", "t.co", "threads.net"
}

COMMUNITY_DOMAIN_PATTERNS = [
    re.compile(r"(^|\.)(substack|wordpress|blogspot|medium|wixsite|weebly|webflow|notion)\.(com|site|io)$", re.I),
    re.compile(r"(^|\.)(forums?|community)\.[^/]+$", re.I),
]

TERTIARY_ENCYCLOPEDIA_DOMAINS = {
    "wikipedia.org", "wikimedia.org", "wikibooks.org", "wiktionary.org",
    "wikiversity.org", "investopedia.com", "britannica.com", "babypips.com",
    "corporatefinanceinstitute.com", "nerdwallet.com", "bankrate.com",
    "thebalance.com", "thebalancemoney.com",
}

# Known verified official foundations, languages, frameworks, and institutional organizations
KNOWN_OFFICIAL_ORGS = {
    "matplotlib", "pandas-dev", "numpy", "scipy", "python", "google", "microsoft",
    "openai", "anthropics", "anthropic", "pytorch", "tensorflow", "facebookresearch", "meta",
    "huggingface", "ethereum", "bitcoin", "torvalds", "apache", "django", "pallets",
    "curl", "git", "nodejs", "golang", "rust-lang", "llvm", "apple", "aws", "kubernetes",
    "solana-labs", "scikit-learn"
}

UNOFFICIAL_REPO_INDICATORS = re.compile(
    r"(-mcp\b|mcp-|-wrapper\b|wrapper-|-unofficial\b|unofficial-|-bot\b|-scraper\b|-client\b|alpha|alphas|backtest|research)",
    re.I
)

# Probability intervals like [0.02, 0.05, 0.12], [0.02 - 0.12], [2%, 5%, 12%], or "в диапазона от 45% до 65%"
PROB_INTERVAL_RE = re.compile(
    r"\[\s*(?:0?\.\d+|\d+%)\s*(?:[,–-]\s*(?:0?\.\d+|\d+%))+\s*\]|"
    r"(?:вероятност\w*|probability)\s+[^.\n]*?\b(?:в\s+диапазона|в\s+граници|in\s+the\s+range\s+of)\s+(?:от\s+)?\d+%\s*(?:до|-|–|to)\s*\d+%",
    re.I
)

# Subjective Bayesian priors or ungrounded probability assignments (excluding frequentist p-values)
SUBJECTIVE_PRIOR_RE = re.compile(
    r"\b(?:[π\\pi]\s*[:=]\s*0?\.\d+|"
    r"prior\s*(?:probability)?\s*(?:[π:=]|is|of)?\s*0?\.\d+|"
    r"prior\s*[:=]\s*0?\.\d+|"
    r"байесов\w*\s+(?:предварителен\s+ориентир|prior).*?0?\.\d+|"
    r"субективна\s+вероятност.*?(?:0?\.\d+|\d+%)|"
    r"subjective\s+probability.*?(?:0?\.\d+|\d+%)|"
    r"P\([^)]+\)\s*(?:=|се оценява|се изчислява|is estimated|≈|~)\s*\[?0?\.\d+)",
    re.I
)

# Formal calculation label
FORMAL_CALC_RE = re.compile(r"\b(Calculation|Изчисление)\s*:", re.I)

# Explicit empirical sample size
SAMPLE_SIZE_RE = re.compile(
    r"\b(?:n|N|извадка|sample\s*size)\s*(?:of|[:=])?\s*\d+|"
    r"\b(?:извадка|sample)\s*(?:от|of)\s+(?:n\s*[:=]\s*)?\d+|"
    r"\bОценка\s+на\s+база\s+извадка\s+n\s*=\s*\d+|"
    r"\b(?:на\s+база|based\s+on)\s+(?:извадка|sample)\s*(?:от)?\s*(?:n\s*[:=]\s*)?\d+",
    re.I
)


def is_community_domain(url: str) -> bool:
  """Returns True if the URL host is a known community, blog, or social platform."""
  try:
    host = (urlparse(url).hostname or "").lower()
  except Exception:
    return False
  if host.startswith("www."):
    host = host[4:]
  for d in COMMUNITY_DOMAINS:
    if host == d or host.endswith("." + d):
      return True
  # Personal GitHub Pages (e.g. username.github.io)
  if host.endswith(".github.io") or host == "github.io":
    sub = host[:-10] if host.endswith(".github.io") else ""
    if sub not in KNOWN_OFFICIAL_ORGS:
      return True
  for pat in COMMUNITY_DOMAIN_PATTERNS:
    if pat.search(host):
      return True
  return False


def is_unofficial_github(url: str, publisher: str = "") -> tuple[bool, str]:
  """Checks if a GitHub/GitLab URL is a personal or unofficial community repository.
  
  Returns (is_unofficial, reason).
  """
  try:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
  except Exception:
    return False, ""
  if host.startswith("www."):
    host = host[4:]
  if host not in ("github.com", "raw.githubusercontent.com", "gist.github.com", "gitlab.com", "bitbucket.org"):
    return False, ""
  if host == "gist.github.com":
    return True, "GitHub Gist is a personal code snippet, not an official binding specification (T5)"
  path_parts = [p for p in parsed.path.strip("/").split("/") if p]
  if not path_parts:
    return False, ""
  owner = path_parts[0]
  repo = path_parts[1] if len(path_parts) > 1 else ""
  
  # Check if repository name indicates a community wrapper/mcp/bot/alpha
  if UNOFFICIAL_REPO_INDICATORS.search(repo):
    return True, f"Code repository '{owner}/{repo}' is a community tool/alpha/wrapper, not an official platform spec (T5)"
  
  # If owner is a known official foundation/org, it's official software
  if owner.lower() in KNOWN_OFFICIAL_ORGS:
    return False, ""
  
  pub_clean = (publisher or "").strip().lower()
  # A personal GitHub repository cannot become official simply by setting publisher=owner
  # Unofficial if publisher is generic, empty, or owner is not a known official foundation
  if pub_clean in ("github", "", "git", "gitlab", "community") or pub_clean != owner.lower() or any(c.isdigit() for c in owner):
    return True, f"Code repository '{owner}/{repo}' is an unofficial personal/community repository (T5)"
  
  # If publisher matches owner but owner is not in KNOWN_OFFICIAL_ORGS and repo has community cues
  if owner.lower() not in KNOWN_OFFICIAL_ORGS:
    return True, f"Code repository '{owner}/{repo}' is an unverified personal/community repository (T5)"
  return False, ""


def is_tertiary_encyclopedia(url: str) -> bool:
  """Returns True if the URL host is a tertiary encyclopedia or retail explainer site."""
  try:
    host = (urlparse(url).hostname or "").lower()
  except Exception:
    return False
  if host.startswith("www."):
    host = host[4:]
  for d in TERTIARY_ENCYCLOPEDIA_DOMAINS:
    if host == d or host.endswith("." + d):
      return True
  return False


def check_source_tier_inflation(url: str, tier: str, publisher: str = "") -> str | None:
  """Validates that a URL is eligible for the specified source tier.
  
  Returns an error message if tier inflation is detected, or None if valid.
  """
  tier_upper = (tier or "").upper()
  if tier_upper not in ("T1", "T2", "T3"):
    return None
  
  if is_community_domain(url):
    return (f"Source tier inflation: {url} is a community/blog platform but marked as {tier_upper}. "
            "Community and forum sources must be T5.")
  
  is_unoff, reason = is_unofficial_github(url, publisher=publisher)
  if is_unoff:
    return (f"Source tier inflation: {url} marked as {tier_upper}. {reason}. "
            "Community tools and personal repositories must be T5.")

  if is_tertiary_encyclopedia(url):
    return (f"Source tier inflation: {url} is a tertiary encyclopedia/retail explainer but marked as {tier_upper}. "
            "Encyclopedias and general explainers must be T4 (secondary/context), never T1-T3.")
  return None


def check_uncalibrated_probabilities(text: str, quote: str = "") -> str | None:
  """Checks if text asserts arbitrary probability intervals or Bayesian priors
  without an explicit empirical sample size (n=...) or formal calculation label.
  
  Returns an error string if uncalibrated, None if valid.
  """
  # Exempt if explicitly labelled with formal calculation
  if FORMAL_CALC_RE.search(text):
    return None
  
  # Check for probability interval or subjective prior
  interval_match = PROB_INTERVAL_RE.search(text)
  prior_match = SUBJECTIVE_PRIOR_RE.search(text)
  
  matched_expr = None
  if interval_match:
    matched_expr = interval_match.group(0)
  elif prior_match:
    matched_expr = prior_match.group(0)
    
  if not matched_expr:
    return None
  
  # If verbatim present in the cited evidence quote, it is an empirical finding from the source
  if quote:
    norm_quote = re.sub(r"\s+", " ", quote)
    norm_expr = re.sub(r"\s+", " ", matched_expr)
    if norm_expr in norm_quote:
      return None
  
  # If backed by an explicit empirical sample size, it is calibrated
  if SAMPLE_SIZE_RE.search(text):
    return None
  
  return (f"uncalibrated subjective probability or Bayesian prior '{matched_expr}' "
          "without explicit empirical sample size (e.g. n=100) or formal 'Calculation:' label")


def load_known_traps(traps_path: Path | None = None) -> list[dict]:
  """Loads known killed edges and traps from JSON registry."""
  path = traps_path or DEFAULT_TRAPS_FILE
  if not path.exists():
    return []
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return []


def check_known_traps_in_text(text: str, traps: list[dict] | None = None) -> list[dict]:
  """Checks text against registered known killed edges and traps.
  
  Returns list of violations if a killed edge is asserted without acknowledging refutation.
  Refutation acknowledgment must be present in the tested statement/unit itself.
  """
  if traps is None:
    traps = load_known_traps()
  violations = []
  for trap in traps:
    matched = False
    for pat in trap.get("patterns", []):
      if re.search(pat, text, re.I):
        matched = True
        break
    if not matched:
      continue
    # Check if text acknowledges the refutation
    ack = False
    for ack_pat in trap.get("acknowledgment_patterns", []):
      if re.search(ack_pat, text, re.I):
        ack = True
        break
    if not ack:
      violations.append(trap)
  return violations
