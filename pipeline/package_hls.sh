#!/usr/bin/env bash
# Package an MP4 as VOD HLS (fMP4 segments) for local serving and, later, S3/CloudFront.
#
# Usage: pipeline/package_hls.sh media/synth/composited.mp4 [out_dir]
#   out_dir defaults to <input dir>/hls
#
# Timestamps are normalized to start at 0 so the player's currentTime lines up with the
# sidecar track's t values. B-frames are off because their reorder delay shifts the
# first presentation timestamp (~2 frames), which shows up as constant overlay skew.
set -euo pipefail

in="${1:?usage: package_hls.sh <input.mp4> [out_dir]}"
out="${2:-$(dirname "$in")/hls}"
rm -rf "$out"
mkdir -p "$out"

ffmpeg -hide_banner -loglevel error -y -i "$in" \
  -map 0:v:0 -map '0:a:0?' \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -bf 0 \
  -force_key_frames 'expr:gte(t,n_forced*2)' -sc_threshold 0 \
  -c:a aac -b:a 128k \
  -avoid_negative_ts make_zero \
  -f hls -hls_time 2 -hls_playlist_type vod \
  -hls_segment_type fmp4 -hls_fmp4_init_filename init.mp4 \
  -hls_segment_filename "$out/seg_%03d.m4s" \
  "$out/index.m3u8"

echo "wrote $out/index.m3u8 ($(ls "$out"/seg_*.m4s | wc -l | tr -d ' ') segments)"
