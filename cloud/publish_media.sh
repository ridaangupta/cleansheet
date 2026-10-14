#!/usr/bin/env bash
# Upload what the app plays to the CDN bucket: per clip the HLS stream, sidecar tracks and
# obscuring textures (never the uncomposited source clips: they show real sponsors), plus the
# brand and UI art. Then invalidate CloudFront so changed files show up.
#
# Usage: cloud/publish_media.sh [clip ...]   (default: the demo and held-out clips)
set -euo pipefail
cd "$(dirname "$0")/.."

export AWS_PROFILE="${AWS_PROFILE:-cleansheet}" AWS_REGION=us-east-2
out() { aws cloudformation describe-stacks --stack-name cleansheet \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET="$(out MediaBucket)"
DIST="$(out DistributionId)"

clips=("$@")
[[ ${#clips[@]} -gt 0 ]] || clips=(synth tachira_01 tachira_02 tachira_03 tachira_04 metro_ucv_01)

for c in "${clips[@]}"; do
  d="media/$c"
  [[ -f "$d/hls/index.m3u8" ]] || { echo "skip $c: no $d/hls (run make clip CLIP=$c)"; continue; }
  aws s3 sync "$d/hls" "s3://$BUCKET/$d/hls" --delete --only-show-errors --exclude "*" \
    --include "*.m3u8" --content-type application/vnd.apple.mpegurl
  aws s3 sync "$d/hls" "s3://$BUCKET/$d/hls" --delete --only-show-errors --exclude "*.m3u8" \
    --exclude "*.m4s" --content-type video/mp4
  aws s3 sync "$d/hls" "s3://$BUCKET/$d/hls" --only-show-errors --exclude "*" \
    --include "*.m4s" --content-type video/iso.segment
  for s in sidecar.json sidecar.model.json; do
    [[ -f "$d/$s" ]] && aws s3 cp "$d/$s" "s3://$BUCKET/$d/$s" --only-show-errors --content-type application/json
  done
  for t in textures textures.model; do
    [[ -d "$d/$t" ]] && aws s3 sync "$d/$t" "s3://$BUCKET/$d/$t" --delete --only-show-errors
  done
  echo "published $c"
done
aws s3 sync assets/brands "s3://$BUCKET/assets/brands" --delete --only-show-errors
aws s3 sync assets/ui "s3://$BUCKET/assets/ui" --delete --only-show-errors
echo "published assets"

aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
  --query Invalidation.Id --output text
