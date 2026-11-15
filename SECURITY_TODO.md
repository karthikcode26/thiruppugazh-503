# Security / cost hardening — resume notes

_Paused mid-discussion. Site is live and fine; these are protective improvements._

## Context
The user worried about (a) a bad actor driving up AWS cost, (b) missing a budget
alert email, and (c) whether the S3 endpoint can be hit directly. A budget alert
is already set up (~$5 monthly, email). These next steps close the real gaps.

## Do these next session, in priority order

### 1. Lock S3 so ONLY CloudFront can read it (HIGHEST priority)
Why: the S3 static-website endpoint
`thiruppugazh-503-us-east-1-first-site.s3-website-us-east-1.amazonaws.com`
is still publicly reachable, bypassing CloudFront. Direct-to-S3 traffic is billed
per request/data and is NOT cached or Shield-protected — the main cost-attack hole.

Fix (guide the user through the AWS Console, verify site stays up at each step):
- Switch CloudFront origin to use **Origin Access Control (OAC)**.
- **Block all public access** on the bucket; add a bucket policy allowing ONLY
  this CloudFront distribution (E3LJUZHEDHG497) to read.
- Result: thiruppugazh503.com works as before; the raw S3 URL returns Access Denied.
- ⚠️ Gotcha: bucket currently uses **S3 static website hosting** (s3-website endpoint).
  OAC uses the **REST endpoint**, which changes default-root/folder-index behavior.
  Must handle `index.html` default root object and confirm song.html + lyrics/audio
  paths still resolve. Test the CloudFront domain BEFORE relying on it.

### 2. Automatic AWS Budgets Action (so a missed email can't cause a runaway bill)
- Configure a Budget **Action** that triggers at the threshold WITHOUT user input.
- Cleanest brake for this architecture: auto-disable CloudFront (site goes offline
  until re-enabled) or attach a deny policy. Needs an IAM role for Budgets.
- Trade-off the user accepted in principle: automatic = site may go offline on
  threshold, which is the intended fail-safe.

### 3. (Optional) AWS WAF rate-limiting on CloudFront
- Throttle abusive IPs; ~a few $/month. Nice-to-have once #1 is done; not essential.

## Also recommended (user action, no code)
- Enable **2FA** on GitHub and AWS (root + IAM user). Biggest security win.

## Current state
- Site live: https://thiruppugazh503.com (CloudFront E3LJUZHEDHG497 -> S3 bucket
  thiruppugazh-503-us-east-1-first-site, us-east-1).
- Deploy: `bash deploy.sh` (uploads public files + lyrics/*.png + audio/*.mp3 +
  audio.json, then invalidates CloudFront). Cache-busting `?v=17` on css/js.
- Latest features all merged: favourites, recently viewed, WhatsApp share,
  per-song audio (main + extras), Play favourites playlist w/ seek bar, range
  jump-bar (sticky), original kumkum-red theme restored.
- Deploy IAM user `thiruppugazh-deploy` has S3 + cloudfront:CreateInvalidation.
  For step 1/2 it will ALSO need CloudFront read/update (GetDistributionConfig,
  UpdateDistribution) and S3 bucket-policy permissions — provide the IAM policy.
