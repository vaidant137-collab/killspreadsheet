#!/usr/bin/env bash
# Boot for a hosted deploy. Builds the dataset on first start if it isn't
# there (hosted disks are wiped between deploys), then serves.
set -e
cd "$(dirname "$0")"

if [ ! -f killspreadsheet.db ]; then
  echo "--- building dataset ---"
  # ground_truth.json and all five vendor documents are committed, so on a
  # hosted boot there is nothing to build. Re-rendering them here is wasted
  # work at best, and at worst it is a hard failure on a host without the
  # fonts the photo renderer wants. Build only what is actually missing.
  [ -f data/ground_truth.json ] || python -m data.build_ground_truth
  [ -f data/generated/ganesh_rate_card_photo.jpg ] || python -m tools.render_all
  echo "--- running pipeline (${EXTRACTOR:-fixture}) ---"
  python -m pipeline --extractor "${EXTRACTOR:-fixture}" || {
    echo "--- real extraction failed; falling back so the site still works ---"
    python -m pipeline --extractor fixture; }
fi

echo "--- serving on ${PORT:-8000} ---"
exec python -m uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
