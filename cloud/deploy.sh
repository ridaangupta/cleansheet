#!/usr/bin/env bash
# Deploy the Cleansheet stack (cloud/template.yaml) and the inventory API code, then print the
# outputs. Safe to re-run. Remove everything with:
#   aws s3 rm s3://cleansheet-media-<account> --recursive --profile cleansheet   (bucket must be empty)
#   aws cloudformation delete-stack --stack-name cleansheet --profile cleansheet --region us-east-2
set -euo pipefail
cd "$(dirname "$0")/.."

export AWS_PROFILE="${AWS_PROFILE:-cleansheet}" AWS_REGION=us-east-2
STACK=cleansheet

aws cloudformation deploy --stack-name "$STACK" --template-file cloud/template.yaml \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset

zip_dir="$(mktemp -d)"
(cd cloud/inventory && zip -q "$zip_dir/api.zip" handler.py)
aws lambda update-function-code --function-name cleansheet-inventory-api \
  --zip-file "fileb://$zip_dir/api.zip" --query LastModified --output text
aws lambda wait function-updated --function-name cleansheet-inventory-api
rm -r "$zip_dir"

aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output text
