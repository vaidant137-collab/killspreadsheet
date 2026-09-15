#!/usr/bin/env bash
# Render's BUILD step.
#
# Extraction happens here, once, with a real model call. Not at boot — a cold
# start cannot afford sixty seconds of OCR before the health check. Not per
# request — that would bill a model call to every visitor.
#
# The brief's one hard rule is "don't fake the extraction". So the deployed
# instance serves a RECORDING OF A REAL RUN: a model genuinely parsed the five
# documents, and data/extraction_runs/ holds verbatim what came back, with the
# model name and the timestamp attached.
#
# That recording is made deliberately and committed — see below for why it is no
# longer made during the build. If none is committed, the build falls back to the
# fixture path and says so, and /api/provenance tells the truth about which path
# produced the numbers on screen. A deploy that quietly served fixture numbers
# while claiming a real run would be the exact failure this project argues
# against, and it is one this build made four times before it was caught.
set -e
cd "$(dirname "$0")"

pip install -r requirements.txt

# Both are committed; this is belt and braces for a fresh clone.
[ -f data/ground_truth.json ] || python -m data.build_ground_truth
[ -f data/generated/ganesh_rate_card_photo.jpg ] || python -m tools.render_all

# Recording is a DELIBERATE ACT, not a side effect of deploying.
#
# It used to run on every deploy. That cost ten minutes a build, hit the build's
# time ceiling every time, fell back, and produced the same bytes it started
# with -- so four deploys in a row shipped the fixture path while the log said
# "recording a real model run". A deploy that takes twelve minutes to arrive
# where it began is a deploy nobody runs, and a slow deploy loop is how the
# other bugs stayed alive as long as they did.
#
# So: the recording is an artefact in the repo, made once on a machine with no
# ceiling on it (RECORD-EXTRACTION.command, or `python -m pipeline --extractor
# record`), and committed. The build replays it. FORCE_RECORD=1 makes a fresh
# one, for when the documents or the extraction schema change -- which is the
# only time the bytes would differ.
HAS_RECORDING=0
if [ -d data/extraction_runs ] && [ -n "$(ls -A data/extraction_runs 2>/dev/null)" ]; then
  HAS_RECORDING=$(ls data/extraction_runs/*.json 2>/dev/null | wc -l | tr -d ' ')
fi

if [ -n "$FORCE_RECORD" ] && \
   [ -n "$OPENROUTER_API_KEY$ANTHROPIC_API_KEY$GEMINI_API_KEY$OPENAI_API_KEY" ]; then
  echo "--- extraction: FORCE_RECORD set, calling a real model ---"
  set +e
  timeout "${EXTRACT_BUDGET_S:-900}" python -m pipeline --extractor record
  rc=$?
  set -e
  N=0
  if [ -d data/extraction_runs ]; then
    N=$(ls data/extraction_runs/*.json 2>/dev/null | wc -l | tr -d ' ')
  fi
  # Exit 0 is NOT the same as "a model read the documents": pipeline.run falls
  # back per document and still exits cleanly, so a run in which every document
  # timed out looks identical from here to a perfect one. Check the artefact.
  if [ "$rc" -eq 0 ] && [ "$N" != "0" ]; then
    echo "--- recorded $N document(s); the deploy will replay this run ---"
    exit 0
  fi
  if [ "$rc" -eq 124 ]; then
    echo "--- the record run hit the ${EXTRACT_BUDGET_S:-900}s ceiling."
  elif [ "$rc" -ne 0 ]; then
    echo "--- the record run failed with exit $rc."
  else
    echo "--- the run completed but recorded NOTHING: every document fell back."
    echo "--- the reasons are above, under 'documents that fell back'."
  fi
  echo "--- record it on a laptop instead: ./RECORD-EXTRACTION.command"
  git checkout -- data/extraction_runs data/extraction_latest.json 2>/dev/null || true
  git clean -fdq data/extraction_runs 2>/dev/null || true
  HAS_RECORDING=$(ls data/extraction_runs/*.json 2>/dev/null | wc -l | tr -d ' ')
fi

if [ "$HAS_RECORDING" != "0" ]; then
  echo "--- extraction: replaying a real run, $HAS_RECORDING document(s), committed in the repo ---"
  python -m pipeline --extractor replay
  exit 0
fi

echo "--- extraction: fixture path. No recording is committed, so no model has"
echo "--- read these documents. /api/provenance and the header say exactly that."
echo "--- make one: ./RECORD-EXTRACTION.command, then commit data/extraction_runs/"
python -m pipeline --extractor fixture
