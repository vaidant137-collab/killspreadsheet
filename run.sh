#!/usr/bin/env bash
set -e
python3 -m data.build_ground_truth
python3 -m tools.render_all
python3 -m pipeline "$@"
python3 -m eval.harness
echo
echo "  http://127.0.0.1:8000"
python3 -m uvicorn api.app:app --port 8000
