#!/bin/bash
# Double-click this file.
#
# It makes a model actually read the five vendor documents, once, on your
# machine, and saves exactly what came back — the model name, the timestamp and
# the verbatim output — into data/extraction_runs/. The deployed site then
# replays that run, and the header says which model read which document.
#
# Why here rather than on the deploy: the build has a time ceiling and a free
# instance is slow, so every deploy so far has hit the ceiling and fallen back
# to the fixture path. Your laptop has no such ceiling. Record once, commit it,
# and every deploy after this serves a real run without calling a model at all.
#
# Your API key never leaves this machine. This script does not print it, send
# it anywhere, or commit it — .env is in .gitignore.

cd "$(dirname "$0")" || exit 1
clear
echo
echo "  ── Record a real extraction run ──────────────────────────────"
echo

# ---------------------------------------------------------------------------
# 1. The key
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || touch .env
  echo "  I have made a file called .env and I am opening it now."
  echo
  echo "  Find the line that says     OPENROUTER_API_KEY="
  echo "  and paste your key straight after the = sign, no spaces, like:"
  echo
  echo "      OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx"
  echo
  echo "  It is the same key you put into Render. Save the file (Cmd-S),"
  echo "  close it, then DOUBLE-CLICK THIS FILE AGAIN."
  echo
  sleep 1
  open -e .env 2>/dev/null || open .env
  echo "  Press any key to close this window."
  read -r -n 1 -s
  exit 0
fi

KEYLINE=$(grep -E '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env | head -1)
if [ -z "$KEYLINE" ]; then
  echo "  .env exists but no API key is filled in yet."
  echo
  echo "  Opening it. Paste your key after OPENROUTER_API_KEY= , save, close,"
  echo "  and double-click this file again."
  echo
  open -e .env 2>/dev/null || open .env
  echo "  Press any key to close this window."
  read -r -n 1 -s
  exit 0
fi
echo "  Key found (${KEYLINE%%=*}). Not printing it."
echo

# ---------------------------------------------------------------------------
# 2. The run
# ---------------------------------------------------------------------------
# Generous per-call ceiling. This is not a build; nobody is waiting on a health
# check, and a photographed rate card can take a couple of minutes to read.
export LLM_TIMEOUT_S="${LLM_TIMEOUT_S:-600}"

echo "  Reading five documents with a real model. Three to ten minutes."
echo "  You will see each one as it lands."
echo

python3 -m pipeline --extractor record
RC=$?
echo

# ---------------------------------------------------------------------------
# 3. What actually happened — the artefact, not the exit code
# ---------------------------------------------------------------------------
N=0
if [ -d data/extraction_runs ]; then
  N=$(ls data/extraction_runs/*.json 2>/dev/null | wc -l | tr -d ' ')
fi

echo "  ──────────────────────────────────────────────────────────────"
if [ "$N" -gt 0 ]; then
  echo "  Recorded $N of 5 documents."
  echo
  python3 - <<'PY'
import json, pathlib
for p in sorted(pathlib.Path("data/extraction_runs").glob("*.json")):
    r = json.loads(p.read_text())
    print(f"      {p.stem:10s} {r.get('model','?'):32s} {r.get('recorded_at','')}")
PY
  echo
  if [ "$N" -lt 5 ]; then
    echo "  The rest fell back to the fixture path. That is fine and the site"
    echo "  says so honestly: the header will read \"4 of 5 documents\"."
    echo
  fi
  echo "  NOW: open GitHub Desktop, commit, and push."
  echo "  The deploy will replay this run and the header will name the model."
else
  echo "  Nothing was recorded — every document fell back. The reasons are"
  echo "  printed above, under \"documents that fell back to the fixture path\"."
  echo "  Nothing is broken: the site keeps working on the fixture path and"
  echo "  says so in the assumptions panel."
fi
echo "  ──────────────────────────────────────────────────────────────"
echo
echo "  Press any key to close this window."
read -r -n 1 -s
exit $RC
