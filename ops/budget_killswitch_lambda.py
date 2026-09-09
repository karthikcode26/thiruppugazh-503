"""
Budget kill-switch Lambda for thiruppugazh503.com.

Purpose
-------
When the AWS Budget threshold is exceeded, AWS sends a notification to an SNS
topic, which triggers this Lambda. The Lambda DISABLES the CloudFront
distribution so the site stops serving traffic and cost stops accruing.

This is a deliberate fail-safe: the site goes OFFLINE when the budget is hit,
until an admin re-enables the distribution (see ops/resume_site.sh or the
CloudFront console). Files in S3 are untouched; only serving is paused.

Setup (see ops/BUDGET_KILLSWITCH_SETUP.md):
- Runtime: Python 3.12
- Handler: budget_killswitch_lambda.handler
- Env var: DISTRIBUTION_ID = E3LJUZHEDHG497
- Execution role must allow cloudfront:GetDistributionConfig and
  cloudfront:UpdateDistribution on that distribution.
- Subscribe this Lambda to the budget's SNS topic.

It is idempotent: if the distribution is already disabled, it does nothing.
"""

import os
import boto3

DISTRIBUTION_ID = os.environ.get("DISTRIBUTION_ID", "E3LJUZHEDHG497")

cloudfront = boto3.client("cloudfront")


def handler(event, context):
    print(f"Budget kill-switch invoked for distribution {DISTRIBUTION_ID}")
    # Read the current config + ETag (required for updates).
    current = cloudfront.get_distribution_config(Id=DISTRIBUTION_ID)
    etag = current["ETag"]
    config = current["DistributionConfig"]

    if not config.get("Enabled", False):
        print("Distribution already disabled. Nothing to do.")
        return {"status": "already_disabled", "distributionId": DISTRIBUTION_ID}

    config["Enabled"] = False
    cloudfront.update_distribution(
        Id=DISTRIBUTION_ID,
        IfMatch=etag,
        DistributionConfig=config,
    )
    print("Distribution disabled. The site will stop serving once the change deploys.")
    return {"status": "disabled", "distributionId": DISTRIBUTION_ID}
