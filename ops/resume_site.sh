#!/usr/bin/env bash
# Re-enable the CloudFront distribution after the budget kill-switch disabled it.
# Run this from a machine with AWS credentials that can update CloudFront.
#
#   bash ops/resume_site.sh
#
# It reads the current config, sets Enabled=true, and updates the distribution.
set -euo pipefail

DIST_ID="${CLOUDFRONT_DISTRIBUTION_ID:-E3LJUZHEDHG497}"

echo "Fetching current CloudFront config for ${DIST_ID} ..."
aws cloudfront get-distribution-config --id "$DIST_ID" > /tmp/cf-config.json
ETAG=$(python3 -c "import json;print(json.load(open('/tmp/cf-config.json'))['ETag'])")

python3 - "$DIST_ID" <<'PY'
import json, sys
data = json.load(open("/tmp/cf-config.json"))
cfg = data["DistributionConfig"]
if cfg.get("Enabled"):
    print("Distribution is already enabled; nothing to do.")
    sys.exit(0)
cfg["Enabled"] = True
json.dump(cfg, open("/tmp/cf-config-enabled.json", "w"))
print("Prepared config with Enabled=true.")
PY

if [[ -f /tmp/cf-config-enabled.json ]]; then
  aws cloudfront update-distribution \
    --id "$DIST_ID" \
    --if-match "$ETAG" \
    --distribution-config "file:///tmp/cf-config-enabled.json" >/dev/null
  echo "Re-enabled CloudFront ${DIST_ID}. It will start serving again once deployed (a few minutes)."
fi
