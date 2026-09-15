"""
Which implementation of each seam is live.

This file is the whole swap mechanism. A new allocator, a new model provider, a
new analyst — each is a class that returns the same Pydantic contract, and
switching to it is one line changed here. Nothing upstream or downstream is
touched, because nothing upstream or downstream ever knew which implementation
it was talking to.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DB_PATH = ROOT / "killspreadsheet.db"

# --- seams ------------------------------------------------------------------
# Two roles, because they have different economics and different stakes.
#
# EXTRACTION is vision-heavy, runs once per document, and is schema-constrained
# so a weaker model has little room to go wrong. It is also the expensive half:
# ~26k input and ~15k output tokens per full pass, and output costs 4-5x input.
#
# The ANALYST is what the interviewer actually watches. It needs good tool
# calling and readable prose, it is cheap per question (~17k in, ~1.2k out),
# and a clumsy answer is visible in a way a clumsy parse is not.
#
# So they are separate settings. Run extraction on something cheap, spend on
# the analyst.
LLM_PROVIDER          = os.getenv("LLM_PROVIDER", "auto")   # auto|anthropic|openai|gemini
LLM_PROVIDER_ANALYST  = os.getenv("LLM_PROVIDER_ANALYST", "")   # falls back to LLM_PROVIDER
ALLOCATOR    = os.getenv("ALLOCATOR", "subsets")     # naive | subsets | milp
ANALYST      = os.getenv("ANALYST", "toolloop")      # toolloop | langgraph
# "fixture" replays known-good extraction output in place of the model, so the
# store, matcher, normaliser, allocator, analyst and UI all run with no API key.
# The matcher is NOT faked in fixture mode - it runs for real against the
# vendor's own labels, so the hard half is genuinely exercised either way.
EXTRACTOR    = os.getenv("EXTRACTOR", "fixture")     # fixture | model

# --- product decisions, not hyperparameters ---------------------------------
# Extraction confidence below this routes a cell to the human review queue.
# Tune it until the queue is short enough that a human actually reads it; a
# 60-item queue gets rubber-stamped and the trust layer becomes theatre.
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.82"))

# Buyer's cost of capital, used to NPV-adjust differing payment terms. 90-day
# terms are worth real money against 30-day terms and the comparison has to say
# so — but the number is the buyer's to set, not ours to assume silently.
COST_OF_CAPITAL_PCT = float(os.getenv("COST_OF_CAPITAL_PCT", "9.0"))

# Most category managers will not run more than three suppliers on one category.
MAX_VENDORS_IN_SPLIT = int(os.getenv("MAX_VENDORS_IN_SPLIT", "3"))

GST_PCT = 18.0
