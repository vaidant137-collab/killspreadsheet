#!/usr/bin/env bash
# Boot for a hosted deploy. Builds the dataset on first start if it isn't
# there (hosted disks are wiped between deploys), then serves.
set -e
cd "$(dirname "$0")"

if [ ! -f killspreadsheet.db ]; then
  echo "--- building dataset ---"
  python -m data.build_ground_truth
  python -m tools.render_all
  echo "--- running pipeline (${EXTRACTOR:-fixture}) ---"
  python -m pipeline --extractor "${EXTRACTOR:-fixture}" || {
    echo "--- real extraction failed; falling back so the site still works ---"
    python -m pipeline --extractor fixture; }
fi

echo "--- serving on ${PORT:-8000} ---"
exec python -m uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
