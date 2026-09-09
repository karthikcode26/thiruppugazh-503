# Automatic budget kill-switch — setup guide

Goal: when the AWS Budget threshold is exceeded, automatically **disable
CloudFront** so the site stops serving and cost stops — even if you miss the
alert email. You re-enable it manually when ready.

Flow: **Budget → SNS topic → Lambda → disables CloudFront (E3LJUZHEDHG497)**.

All steps are in the AWS Console unless noted. Do them in order. Region for the
Lambda/SNS: use **us-east-1 (N. Virginia)** to keep everything together.

---

## 1. Create the Lambda function
1. Console → **Lambda** → **Create function** → **Author from scratch**.
2. Name: `budget-killswitch`. Runtime: **Python 3.12**. Architecture: default.
3. **Create function.**
4. In the **Code** tab, replace the contents of `lambda_function.py` with the
   code from `ops/budget_killswitch_lambda.py` in this repo.
5. **Handler:** set to `lambda_function.handler` (Code tab → Runtime settings →
   Edit → Handler). (Lambda's default file is `lambda_function.py`, so the
   handler is `lambda_function.handler`.)
6. **Configuration → Environment variables → Edit → Add:**
   - Key: `DISTRIBUTION_ID`  Value: `E3LJUZHEDHG497`
7. **Configuration → General configuration → Edit:** set **Timeout** to 30 sec.
8. **Deploy** the code.

## 2. Give the Lambda permission to disable CloudFront
1. Lambda → **Configuration → Permissions** → click the **Execution role** link
   (opens IAM).
2. **Add permissions → Create inline policy → JSON**, paste the contents of
   `ops/killswitch-lambda-policy.json`, name it `killswitch-cloudfront`, create.
   (This allows only GetDistributionConfig + UpdateDistribution on this one
   distribution.)

## 3. Create the SNS topic the budget will notify
1. Console → **SNS** → **Topics** → **Create topic** → Type **Standard**.
2. Name: `budget-killswitch-topic` → **Create topic**. Copy its **ARN**.
3. **Subscriptions → Create subscription:**
   - Protocol: **AWS Lambda**
   - Endpoint: select the `budget-killswitch` function → **Create**.
   (This lets the budget's SNS message trigger the Lambda.)

## 4. Allow the budgets service to publish to the topic
SNS needs a policy allowing AWS Budgets to publish. On the topic → **Edit** →
**Access policy**, add a statement (merge into the existing "Statement" list):

```json
{
  "Sid": "AllowBudgetsPublish",
  "Effect": "Allow",
  "Principal": { "Service": "budgets.amazonaws.com" },
  "Action": "SNS:Publish",
  "Resource": "<PASTE-THE-TOPIC-ARN>"
}
```

## 5. Point your budget at the SNS topic
1. Console → **Billing and Cost Management → Budgets** → open your budget
   (`thiruppugazh503-monthly`).
2. **Edit** → go to the **alerts/notifications** step.
3. On the threshold you want to act on (e.g. **100% of actual**, or set a
   dedicated one like **100% forecasted**), under **Notification** add an
   **Amazon SNS topic** and paste the topic ARN. Keep the email alert too.
4. Save.

> Note: this uses the budget's SNS notification (simple and reliable). AWS also
> has "Budget Actions", but for CloudFront the SNS→Lambda path is the clean way
> to actually disable serving.

## 6. Test it safely (do NOT wait for a real overspend)
Test the Lambda directly, then re-enable:
1. Lambda → `budget-killswitch` → **Test** → create a test event (any empty
   `{}` JSON) → **Test**. It should log "Distribution disabled".
2. Check CloudFront: distribution shows **Disabled** / begins disabling.
3. Confirm the site stops serving after it deploys (a few minutes):
   `https://thiruppugazh503.com` should fail.
4. **Re-enable** with the resume script (from a machine with AWS creds):
   ```bash
   bash ops/resume_site.sh
   ```
   or in the console: CloudFront → distribution → **Enable**.
5. Verify the site is back after it re-deploys.

## What happens in real life
- If spend crosses the threshold, the budget publishes to SNS → Lambda disables
  CloudFront → the site goes offline and cost stops.
- You get the email too. When ready, run `ops/resume_site.sh` (or click Enable)
  to bring it back.

## Re-enabling permissions note
`ops/resume_site.sh` needs `cloudfront:GetDistributionConfig` +
`cloudfront:UpdateDistribution`. If you run it as the `thiruppugazh-deploy` user,
add the same policy (`ops/killswitch-lambda-policy.json`) to that user, or run it
with an admin profile.
