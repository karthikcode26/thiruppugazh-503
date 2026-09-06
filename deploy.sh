#!/usr/bin/env bash
set -euo pipefail

BUCKET="thiruppugazh-503-us-east-1-first-site"
# Once the CloudFront distribution exists, set its ID here (or export
# CLOUDFRONT_DISTRIBUTION_ID before running) so each deploy clears the CDN cache
# and changes appear immediately. Leave empty until CloudFront is set up.
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-E3LJUZHEDHG497}"
SITE_URL="${SITE_URL:-https://thiruppugazh503.com}"
DRY_RUN=""

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN="--dryrun"
elif [[ -n "${1:-}" ]]; then
  echo "Usage: bash deploy.sh [--dry-run]" >&2
  exit 2
fi

# Deliberately deploy only public runtime assets. Do not replace this with
# `aws s3 sync .`: the working tree can contain ignored API keys, playlist
# metadata, and review files that must never be made public.
PUBLIC_FILES=(
  index.html
  song.html
  app.js
  store.js
  styles.css
  songs.json
)

for file in "${PUBLIC_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required site file: $file" >&2
    exit 1
  fi
  aws s3 cp "$file" "s3://${BUCKET}/${file}" ${DRY_RUN}
done

# Upload the public-domain lyrics files, if present. Restricted to the lyrics/
# folder and .txt/.png files so nothing else in the tree can leak.
if [[ -d lyrics ]]; then
  aws s3 sync lyrics "s3://${BUCKET}/lyrics" \
    --exclude "*" --include "*.txt" \
    --content-type "text/plain; charset=utf-8" \
    --delete ${DRY_RUN}
  aws s3 sync lyrics "s3://${BUCKET}/lyrics" \
    --exclude "*" --include "*.png" \
    --content-type "image/png" \
    ${DRY_RUN}
fi

if [[ -n "$DRY_RUN" ]]; then
  echo "Dry run complete. Only the public site files and lyrics/*.txt/*.png above would be uploaded."
  if [[ -n "$CLOUDFRONT_DISTRIBUTION_ID" ]]; then
    echo "(Would also invalidate CloudFront distribution ${CLOUDFRONT_DISTRIBUTION_ID}.)"
  fi
  exit 0
fi

# Clear the CloudFront cache so visitors get the new files right away. Skipped
# until a distribution ID is configured (before HTTPS/CloudFront is set up).
if [[ -n "$CLOUDFRONT_DISTRIBUTION_ID" ]]; then
  echo "Invalidating CloudFront cache (${CLOUDFRONT_DISTRIBUTION_ID}) ..."
  aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths "/*" >/dev/null
  echo "CloudFront cache invalidation requested."
fi

echo "Deployment complete: ${SITE_URL}"
