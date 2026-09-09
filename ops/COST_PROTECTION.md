# Cost protection — Option C (alerts + manual kill switch)

A simple, low-risk safety net for AWS cost:
1. A **low early-warning** budget threshold so you hear about unusual spend early.
2. **SMS/text alerts** (not just email) so you don't miss it.
3. A **one-command kill switch** to disable the site in seconds if needed, and a
   resume command to bring it back.

Nothing shuts the site down automatically — you stay in control.

---

## 1. Lower early-warning threshold (Budgets console)
1. Console → **Billing and Cost Management → Budgets** → open
   `thiruppugazh503-monthly` → **Edit**.
2. In the alerts step, add/keep thresholds so you get warned early, e.g.:
   - **50% of budgeted (actual)** → early heads-up (~$2.50 if budget is $5)
   - **80%** and **100%** → escalating
   - optionally **100% forecasted** → warns before month-end if trending high
3. Save.

## 2. SMS/text alerts (via SNS)
Email alone is easy to miss; add a text message.
1. Console → **SNS → Topics → Create topic** → **Standard** →
   name `budget-alerts` → **Create**. Copy its **ARN**.
2. **Create subscription** on that topic:
   - Protocol: **SMS**
   - Endpoint: your phone number in **+<countrycode><number>** form
     (e.g. `+9198XXXXXXXX` for India) → **Create subscription**.
   (SMS subscriptions are confirmed automatically; you may get a test text.)
3. Let the budgets service publish to the topic — on the topic → **Edit →
   Access policy**, add to the Statement list:
   ```json
   {
     "Sid": "AllowBudgetsPublish",
     "Effect": "Allow",
     "Principal": { "Service": "budgets.amazonaws.com" },
     "Action": "SNS:Publish",
     "Resource": "<PASTE-THE-TOPIC-ARN>"
   }
   ```
4. Point the budget at the topic: Budgets → your budget → **Edit** → on a
   threshold's **Notification**, add **Amazon SNS topic** = the `budget-alerts`
   ARN (keep the email too). Save.

Now a threshold breach sends you a **text** as well as an email.

> Note: AWS SMS has region/spend-limit setup in some accounts. If the SMS
> subscription doesn't send, the email alert still works; you can also use the
> free **AWS Console mobile app** push notifications as an alternative.

## 3. Kill switch (manual, one command)
If you get an alert and want to stop cost immediately:
```bash
bash ops/kill_site.sh       # disables CloudFront -> site offline, cost stops
```
When you're ready to bring it back:
```bash
bash ops/resume_site.sh     # re-enables CloudFront
```
Both take a few minutes to deploy across CloudFront. Files in S3 are untouched.

### Permissions for the scripts
They need `cloudfront:GetDistributionConfig` + `cloudfront:UpdateDistribution`
on the distribution. If running as the `thiruppugazh-deploy` IAM user, add the
inline policy in `ops/cloudfront-toggle-policy.json` to that user (IAM → Users →
thiruppugazh-deploy → Add permissions → Create inline policy → JSON). Or run the
scripts with an admin AWS profile.

## Reality check
For a small static site behind CloudFront (cached + AWS Shield Standard, S3 now
locked to CloudFront-only), a costly attack is unlikely and the worst case is
bounded by your budget awareness. This setup gives you fast warning + an instant
manual brake without the risk of an automatic shutdown firing unexpectedly.
