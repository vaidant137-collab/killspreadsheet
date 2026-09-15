#!/bin/bash
# Double-click this file. It sets everything up and opens the demo.
cd "$(dirname "$0")"
clear
echo ""
echo "  Kill the Quote Spreadsheet"
echo "  ─────────────────────────────────────────────"
echo ""

# --- find a python that actually works -----------------------------------
# Newest is NOT the right criterion. Homebrew Pythons frequently ship with no
# pip and no working ensurepip, and a newer Python that cannot install
# anything is worse than an older one that can. So: prefer the newest that
# HAS pip, and only then fall back to bootstrapping one.
CANDIDATES="python3.13 python3.12 python3.11 python3.10 python3.9 python3"
PY=""
for c in $CANDIDATES; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -m pip --version >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "  None of your Pythons has pip. Installing it..."
  curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/ks_get_pip.py 2>/dev/null
  for c in $CANDIDATES; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" /tmp/ks_get_pip.py --user -q >/dev/null 2>&1
    "$c" -m pip --version >/dev/null 2>&1 && { PY="$c"; echo "        done"; break; }
  done
fi

if [ -z "$PY" ]; then
  echo "  Could not find a usable Python."
  echo ""
  echo "  Quickest fix - paste this into Terminal and press Enter:"
  echo "      brew install python@3.12"
  echo "  then double-click this file again."
  echo ""
  xcode-select --install 2>/dev/null
  read -n 1 -s -r -p "  Press any key to close."; exit 1
fi
PYVER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "  Using Python $PYVER  ($PY)"
[ "$PYVER" = "3.9" ] && echo "  (3.9 is fine - a compatibility package is installed below.)"
echo ""

# --- API key -------------------------------------------------------------
if [ ! -f .env ] || ! grep -qE '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env; then
  echo "  No API key saved yet."
  echo "  Paste your OpenRouter key and press Enter (free at openrouter.ai/keys),"
  echo "  or press Enter to skip - everything works without one except the"
  echo "  live analyst chat."
  echo ""
  printf "  Key: "
  read -r USERKEY
  if [ -n "$USERKEY" ]; then
    printf 'OPENROUTER_API_KEY=%s\n' "$USERKEY" > .env
    printf 'OPENROUTER_ANALYST_MODEL=anthropic/claude-sonnet-5\n' >> .env
    echo "        Saved. git ignores .env, so it never leaves your Mac."
  else
    echo "        Skipped."
  fi
  echo ""
fi

# --- somewhere to install packages ---------------------------------------
# Three strategies, because Python installs on macOS vary wildly: Homebrew's
# ensurepip is often broken, and the system one refuses plain pip installs.
# Whichever works, we end up with $VPY able to import what we need.
VPY=""
PIPFLAGS=""

echo "  [1/5] Setting up an isolated environment..."
if "$PY" -m venv .venv >/dev/null 2>&1 && [ -x .venv/bin/python ] \
   && .venv/bin/python -m pip --version >/dev/null 2>&1; then
  VPY=".venv/bin/python"
  echo "        done"
else
  rm -rf .venv
  echo "        Standard method unavailable on this Python. Trying another..."
  if "$PY" -m venv --without-pip .venv >/dev/null 2>&1 && [ -x .venv/bin/python ]; then
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/ks_get_pip.py 2>/dev/null \
      && .venv/bin/python /tmp/ks_get_pip.py -q >/dev/null 2>&1 \
      && .venv/bin/python -m pip --version >/dev/null 2>&1 \
      && { VPY=".venv/bin/python"; echo "        done"; }
  fi
fi
if [ -z "$VPY" ]; then
  rm -rf .venv
  VPY="$PY"
  PIPFLAGS="--break-system-packages"
  echo "        Using your main Python instead. That is fine."
fi
echo ""

echo "  [2/5] Installing what it needs (a minute or two the first time)..."
"$VPY" -m pip install $PIPFLAGS --quiet --upgrade pip >/dev/null 2>&1
"$VPY" -m pip install $PIPFLAGS --quiet -r requirements.txt 2>&1 | tail -4
[ "$PYVER" = "3.9" ] && "$VPY" -m pip install $PIPFLAGS --quiet eval_type_backport >/dev/null 2>&1

if ! "$VPY" -c "from api.app import app" 2>/tmp/ks_err; then
  echo ""
  echo "  Still missing something. The line that matters:"
  echo ""
  tail -4 /tmp/ks_err | sed 's/^/    /'
  echo ""
  echo "  Copy that into the Claude chat and I will fix it."
  echo ""
  read -n 1 -s -r -p "  Press any key to close."; exit 1
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
if grep -qE '^(OPENROUTER|ANTHROPIC|OPENAI|GEMINI)_API_KEY=.+' .env 2>/dev/null; then
  echo "        API key found - recording a real extraction run..."
  "$VPY" -m pipeline --extractor record 2>&1 | tail -9 || {
    echo "        Real extraction had a problem. Falling back so the demo still works."
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

PORT=8000
while lsof -ti :$PORT >/dev/null 2>&1; do PORT=$((PORT+1)); done
echo "  ─────────────────────────────────────────────"
echo "  Opening http://127.0.0.1:$PORT"
echo ""
echo "  LEAVE THIS WINDOW OPEN while you demo."
echo "  ─────────────────────────────────────────────"
echo ""
( for i in $(seq 1 40); do
    curl -s -o /dev/null "http://127.0.0.1:$PORT/" && { open "http://127.0.0.1:$PORT"; break; }
    sleep 1
  done ) &
"$VPY" -m uvicorn api.app:app --host 127.0.0.1 --port $PORT
echo ""
echo "  Server stopped."
read -n 1 -s -r -p "  Press any key to close."
