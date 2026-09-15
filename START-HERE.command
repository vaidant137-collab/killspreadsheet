#!/bin/bash
# Double-click this file. It sets everything up and opens the demo.
cd "$(dirname "$0")"
clear
echo ""
echo "  Kill the Quote Spreadsheet"
echo "  ─────────────────────────────────────────────"
echo ""

# --- python --------------------------------------------------------------
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
  echo "  Python 3 isn't installed."
  echo ""
  echo "  A window should pop up offering to install Developer Tools."
  echo "  Click Install, wait for it to finish, then double-click this file again."
  xcode-select --install 2>/dev/null
  echo ""
  read -n 1 -s -r -p "  Press any key to close."
  exit 1
fi
echo "  Using $($PY --version 2>&1)"
echo ""

# --- API key -------------------------------------------------------------
if [ ! -f .env ] || ! grep -qE '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env; then
  echo "  No API key saved yet."
  echo ""
  echo "  Paste your OpenRouter key and press Enter."
  echo "  (Free at openrouter.ai/keys - it starts with sk-or-)"
  echo ""
  echo "  Or press Enter to skip. Everything still works without one;"
  echo "  you only lose the live analyst chat."
  echo ""
  printf "  Key: "
  read -r USERKEY
  if [ -n "$USERKEY" ]; then
    printf 'OPENROUTER_API_KEY=%s\n' "$USERKEY" > .env
    printf 'OPENROUTER_ANALYST_MODEL=anthropic/claude-sonnet-5\n' >> .env
    echo "        Saved. (git ignores .env, so it never leaves your Mac.)"
  else
    echo "        Skipped."
  fi
  echo ""
fi

# --- dependencies, in an isolated environment ----------------------------
# A virtual environment, because modern macOS refuses a plain `pip install`
# with "externally-managed-environment". This also means nothing here can
# disturb any other Python you have.
if [ ! -d .venv ]; then
  echo "  [1/5] Creating an isolated Python environment (first run only)..."
  "$PY" -m venv .venv || {
    echo ""
    echo "  Could not create it. Tell Claude exactly what this says:"
    "$PY" -m venv .venv
    read -n 1 -s -r -p "  Press any key to close."; exit 1; }
else
  echo "  [1/5] Environment already set up."
fi
VPY=".venv/bin/python"
echo ""

echo "  [2/5] Installing what it needs (a minute or two the first time)..."
"$VPY" -m pip install --quiet --upgrade pip 2>&1 | tail -2
if ! "$VPY" -m pip install --quiet -r requirements.txt 2>&1 | tail -5; then
  echo ""
  echo "  Install had trouble. Trying the essentials only..."
  "$VPY" -m pip install --quiet pydantic fastapi uvicorn python-dotenv openpyxl \
      pypdf python-docx Pillow numpy reportlab openai anthropic 2>&1 | tail -3
fi
echo "        done"
echo ""

echo "  [3/5] Building the dataset..."
"$VPY" -m data.build_ground_truth 2>&1 | tail -1
echo ""

echo "  [4/5] Rendering the five vendor documents..."
"$VPY" -m tools.render_all 2>&1 | tail -2
echo ""

echo "  [5/5] Extraction, matching, normalisation..."
if [ -f .env ] && grep -qE '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env; then
  echo "        API key found - recording a real extraction run..."
  "$VPY" -m pipeline --extractor record 2>&1 | tail -9 || {
    echo "        Real extraction hit a problem. Falling back so the demo still works."
    "$VPY" -m pipeline --extractor fixture 2>&1 | tail -9; }
else
  echo "        No API key - using the replay path."
  "$VPY" -m pipeline --extractor fixture 2>&1 | tail -9
fi
echo ""

echo "  Scorecard"
echo "  ─────────────────────────────────────────────"
"$VPY" -m eval.harness 2>&1 | sed -n '/SCORECARD/,/escape rate/p'
echo ""

# --- serve ---------------------------------------------------------------
PORT=8000
while lsof -ti :$PORT >/dev/null 2>&1; do PORT=$((PORT+1)); done
echo "  ─────────────────────────────────────────────"
echo "  Opening http://127.0.0.1:$PORT"
echo ""
echo "  LEAVE THIS WINDOW OPEN while you demo."
echo "  Close it when you're finished."
echo "  ─────────────────────────────────────────────"
echo ""

( for i in $(seq 1 30); do
    curl -s -o /dev/null "http://127.0.0.1:$PORT/" && { open "http://127.0.0.1:$PORT"; break; }
    sleep 1
  done ) &

"$VPY" -m uvicorn api.app:app --host 127.0.0.1 --port $PORT
echo ""
echo "  Server stopped."
read -n 1 -s -r -p "  Press any key to close."
