#!/usr/bin/env bash
set -euo pipefail
STACK_NAME="${1:?Usage: scripts/publish_site.sh STACK_NAME [REGION]}"
DEPLOY_REGION="${2:-us-east-1}"
: "${AWS_EXPECTED_ACCOUNT_ID:?Set AWS_EXPECTED_ACCOUNT_ID to the intended 12-digit AWS account ID}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTUAL_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$ACTUAL_ACCOUNT_ID" != "$AWS_EXPECTED_ACCOUNT_ID" ]]; then
  printf 'Wrong AWS account. No files uploaded.\n' >&2
  exit 1
fi
OUTPUTS="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$DEPLOY_REGION" --query 'Stacks[0].Outputs' --output json)"
SITE_BUCKET="$(python3 -c 'import json,sys; print(next(x["OutputValue"] for x in json.load(sys.stdin) if x["OutputKey"]=="SiteBucketName"))' <<< "$OUTPUTS")"
DISTRIBUTION_ID="$(python3 -c 'import json,sys; print(next(x["OutputValue"] for x in json.load(sys.stdin) if x["OutputKey"]=="DistributionId"))' <<< "$OUTPUTS")"
python3 "$REPO_DIR/scripts/check_site.py"
aws s3 sync "$REPO_DIR/site/" "s3://$SITE_BUCKET/" --region "$DEPLOY_REGION" --delete --sse AES256 --cache-control 'public,max-age=3600'
aws s3 cp "$REPO_DIR/site/index.html" "s3://$SITE_BUCKET/index.html" --region "$DEPLOY_REGION" --sse AES256 --content-type 'text/html; charset=utf-8' --cache-control 'no-cache'
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths '/*' --query Invalidation.Id --output text
printf 'Uploaded site and requested cache invalidation.\n'
