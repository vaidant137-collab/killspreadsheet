#!/usr/bin/env bash
# Render's BUILD step.
#
# Extraction happens here, once, with a real model call. Not at boot — a cold
# start cannot afford sixty seconds of OCR before the health check. Not per
# request — that would bill a model call to every visitor.
#
# The brief's one hard rule is "don't fake the extraction". So the deployed
# instance serves a RECORDING OF A REAL RUN: the model genuinely parsed the five
# documents during this build, and data/extraction_runs/ holds verbatim what came
# back, with the model name and timestamp attached. Because it is re-recorded on
# every deploy, it cannot drift away from the code that produced it.
#
# If no key is present, or the real run fails, the build does NOT fail — it falls
# back to the fixture path and DELETES the recordings, so /api/provenance tells
# the truth about which path produced the numbers on screen. A deploy that
# quietly served fixture numbers while claiming a real run would be the exact
# failure this whole project is arguing against.
set -e
cd "$(dirname "$0")"

pip install -r requirements.txt

# Both are committed; this is belt and braces for a fresh clone.
[ -f data/ground_truth.json ] || python -m data.build_ground_truth
[ -f data/generated/ganesh_rate_card_photo.jpg ] || python -m tools.render_all

if [ -n "$OPENROUTER_API_KEY$ANTHROPIC_API_KEY$GEMINI_API_KEY$OPENAI_API_KEY" ]; then
  echo "--- extraction: recording a real model run ---"
  # A ceiling on the whole recording, not just per call. Belt and braces: if
  # anything below the client timeout still wedges, the build falls back and
  # ships rather than hanging and shipping nothing.
  if timeout "${EXTRACT_BUDGET_S:-420}" python -m pipeline --extractor record; then
    echo "--- recorded; the deploy will replay this run ---"
    exit 0
  fi
  echo "--- real extraction failed or timed out. Falling back, and saying so. ---"
  rm -rf data/extraction_runs data/extraction_latest.json
fi

echo "--- extraction: fixture path (no key at build time, or the run failed) ---"
python -m pipeline --extractor fixture
