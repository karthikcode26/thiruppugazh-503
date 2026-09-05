#!/usr/bin/env bash
set -euo pipefail

BUCKET="thiruppugazh-503-us-east-1-first-site"
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

if [[ -n "$DRY_RUN" ]]; then
  echo "Dry run complete. Only the five public site files above would be uploaded."
else
  echo "Deployment complete: http://${BUCKET}.s3-website-us-east-1.amazonaws.com"
fi
