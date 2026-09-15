#!/bin/bash
# Double-click this file. It sets everything up and opens the demo.
cd "$(dirname "$0")"
clear
echo ""
echo "  Kill the Quote Spreadsheet"
echo "  ─────────────────────────────────────────────"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "  Python 3 isn't installed."
  echo ""
  echo "  A window should pop up offering to install Developer Tools."
  echo "  Click Install, wait for it to finish, then double-click this file again."
  echo ""
  xcode-select --install 2>/dev/null
  read -n 1 -s -r -p "  Press any key to close."
  exit 1
fi

# --- API key -------------------------------------------------------------
# Asked for here rather than in a hidden file, and written straight to .env
# which git ignores. Nobody else ever sees it.
if [ ! -f .env ] || ! grep -qE '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env; then
  echo "  No API key saved yet."
  echo ""
  echo "  Paste your OpenRouter key below and press Enter."
  echo "  (Get one free at openrouter.ai/keys - it starts with sk-or-)"
  echo ""
  echo "  Or just press Enter to skip. Everything still works without one;"
  echo "  you only lose the live analyst chat."
  echo ""
  printf "  Key: "
  read -r USERKEY
  if [ -n "$USERKEY" ]; then
    printf 'OPENROUTER_API_KEY=%s\n' "$USERKEY" > .env
    printf 'OPENROUTER_ANALYST_MODEL=anthropic/claude-sonnet-5\n' >> .env
    echo "        Saved to .env (git ignores this file, so it never leaves your Mac)."
  else
    echo "        Skipped."
  fi
  echo ""
fi

echo "  [1/4] Installing what it needs (a minute or two the first time)..."
python3 -m pip install --quiet --upgrade pip 2>/dev/null
python3 -m pip install --quiet -r requirements.txt 2>&1 | grep -vi "warning\|already satisfied" | tail -3
echo "        done"
echo ""

echo "  [2/4] Building the dataset..."
python3 -m data.build_ground_truth 2>&1 | tail -1
echo ""

echo "  [3/4] Rendering the five vendor documents..."
python3 -m tools.render_all 2>&1 | tail -2
echo ""

echo "  [4/4] Running extraction, matching, normalisation..."
if [ -f .env ] && grep -qE '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env; then
  echo "        Found an API key. Recording a real extraction run..."
  python3 -m pipeline --extractor record 2>&1 | tail -9 || {
    echo ""
    echo "        Real extraction hit a problem. Falling back to the replay path"
    echo "        so the demo still works."
    python3 -m pipeline --extractor fixture 2>&1 | tail -9
  }
else
  echo "        No API key in .env — using the replay path."
  echo "        (Everything below works either way.)"
  python3 -m pipeline --extractor fixture 2>&1 | tail -9
fi
echo ""

echo "  Scorecard"
echo "  ─────────────────────────────────────────────"
python3 -m eval.harness 2>&1 | sed -n '/SCORECARD/,/escape rate/p'
echo ""
echo "  ─────────────────────────────────────────────"
echo "  Opening http://127.0.0.1:8000 in your browser."
echo ""
echo "  LEAVE THIS WINDOW OPEN while you demo."
echo "  Close it (or press Ctrl+C) when you're finished."
echo "  ─────────────────────────────────────────────"
echo ""

( sleep 3 && open http://127.0.0.1:8000 ) &
python3 -m uvicorn api.app:app --port 8000
