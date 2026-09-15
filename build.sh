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

# Is there a real recorded run committed in the repo? It matters below: a
# recording made last week by a real model is a far better thing to fall back to
# than the fixture, and the chip reports it honestly either way because every
# recording carries the model name and the timestamp of the run.
HAD_RECORDING=0
if [ -d data/extraction_runs ] && [ -n "$(ls -A data/extraction_runs 2>/dev/null)" ]; then
  HAD_RECORDING=1
fi

# A recording committed to the repo is the artefact; re-making it on every
# deploy was the right design only while there was none. Four deploys spent ten
# minutes each calling a model, hitting the build ceiling and falling back, and
# a deploy that takes twelve minutes to arrive at the same bytes is a deploy
# nobody runs. Set FORCE_RECORD=1 to make a fresh one — for instance after
# changing the documents or the extraction schema.
if [ "$HAD_RECORDING" -eq 1 ] && [ -z "$FORCE_RECORD" ]; then
  echo "--- extraction: replaying the real run committed in the repo ---"
  ls data/extraction_runs/*.json 2>/dev/null | wc -l | xargs echo "--- documents:"
  python -m pipeline --extractor replay
  exit 0
fi

if [ -n "$OPENROUTER_API_KEY$ANTHROPIC_API_KEY$GEMINI_API_KEY$OPENAI_API_KEY" ]; then
  echo "--- extraction: recording a real model run ---"
  # A ceiling on the whole recording, not just on each call. Belt and braces: if
  # anything below the client timeout still wedges, the build falls back and
  # ships rather than hanging and shipping nothing.
  set +e
  timeout "${EXTRACT_BUDGET_S:-420}" python -m pipeline --extractor record
  rc=$?
  set -e
  # Exit 0 is NOT the same as "a model read the documents". pipeline.run falls
  # back PER DOCUMENT and still exits cleanly, so a run in which every single
  # document timed out looks identical from here to a perfect one -- which is
  # how this deploy shipped the fixture path four times while the build log
  # said "recorded". Check for the artefact, not the exit code.
  RECORDED=0
  if [ -d data/extraction_runs ] && [ -n "$(ls -A data/extraction_runs 2>/dev/null)" ]; then
    RECORDED=$(ls data/extraction_runs/*.json 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [ "$rc" -eq 0 ] && [ "$RECORDED" != "0" ]; then
    echo "--- recorded $RECORDED document(s); the deploy will replay this run ---"
    exit 0
  fi
  if [ "$rc" -eq 0 ]; then
    echo "--- the run completed but recorded NOTHING: every document fell back."
    echo "--- the reasons are listed above, under 'documents that fell back'."
  fi
  # Say WHICH failure. A build that falls back for an unstated reason is a
  # mystery next deploy, and this one already cost an evening: 124 is the
  # ceiling, anything else is the run itself.
  if [ "$rc" -eq 124 ]; then
    echo "--- the record run hit the ${EXTRACT_BUDGET_S:-420}s ceiling. Either the"
    echo "--- extract model is slow or a call is retrying. Set"
    echo "--- OPENROUTER_EXTRACT_MODEL to something faster, or raise EXTRACT_BUDGET_S."
  else
    echo "--- the record run failed with exit $rc. ---"
  fi
  if [ "$HAD_RECORDING" -eq 1 ]; then
    echo "--- falling back to the real run committed in the repo ---"
    git checkout -- data/extraction_runs data/extraction_latest.json 2>/dev/null || true
    git clean -fdq data/extraction_runs 2>/dev/null || true
    python -m pipeline --extractor replay
    exit 0
  fi
  echo "--- no committed recording to fall back to. Fixture, and saying so. ---"
  rm -rf data/extraction_runs data/extraction_latest.json
fi

echo "--- extraction: fixture path (no key at build time, or the run failed) ---"
python -m pipeline --extractor fixture
