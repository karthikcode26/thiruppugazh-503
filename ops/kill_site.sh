#!/usr/bin/env bash
# Manual kill switch: DISABLE the CloudFront distribution so the site stops
# serving and cost stops accruing. Use this if you get a budget alert.
#
#   bash ops/kill_site.sh
#
# Re-enable later with:  bash ops/resume_site.sh
#
# Needs AWS credentials that can GetDistributionConfig + UpdateDistribution
# (see ops/cloudfront-toggle-policy.json).
set -euo pipefail

DIST_ID="${CLOUDFRONT_DISTRIBUTION_ID:-E3LJUZHEDHG497}"

echo "Fetching current CloudFront config for ${DIST_ID} ..."
aws cloudfront get-distribution-config --id "$DIST_ID" > /tmp/cf-config.json
ETAG=$(python3 -c "import json;print(json.load(open('/tmp/cf-config.json'))['ETag'])")

python3 - <<'PY'
import json, sys
data = json.load(open("/tmp/cf-config.json"))
cfg = data["DistributionConfig"]
if not cfg.get("Enabled"):
    print("Distribution is already disabled; nothing to do.")
    sys.exit(0)
cfg["Enabled"] = False
json.dump(cfg, open("/tmp/cf-config-disabled.json", "w"))
print("Prepared config with Enabled=false.")
PY

if [[ -f /tmp/cf-config-disabled.json ]]; then
  aws cloudfront update-distribution \
    --id "$DIST_ID" \
    --if-match "$ETAG" \
    --distribution-config "file:///tmp/cf-config-disabled.json" >/dev/null
  rm -f /tmp/cf-config-disabled.json
  echo "Disabled CloudFront ${DIST_ID}. The site will stop serving once the change deploys (a few minutes)."
  echo "Re-enable when ready with: bash ops/resume_site.sh"
fi
