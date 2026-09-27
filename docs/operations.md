# Operating the request backend

## Intended state

The practice is prelaunch. `IntakeEnabled=false` is the default, and the published website has no contact or intake form. Treat the backend as a tested foundation requiring live AWS validation and an agreed operating workflow before use with patients.

The infrastructure and software do not establish HIPAA compliance by themselves. Resolve the practice's applicable agreements, account/provider responsibilities, access controls, and retention decisions before collecting patient data. Avoid personal email forwarding or copying request payloads into logs, tickets, analytics, or GitHub.

## Operator access

Use individually assigned AWS identities with MFA/SSO and narrowly scoped permissions. The server's execution roles are not operator accounts.

The CLI needs `dynamodb:Query` on the table's `by-status` index, plus `dynamodb:GetItem` and `dynamodb:UpdateItem` on the table. Scope those actions to the actual output ARNs and the authorized operator identity. Do not give the operator an administrator policy merely to review requests.

Set `REQUESTS_TABLE` from the deployed stack's `RequestsTableName` output, then:

```bash
python scripts/requests.py --table "$REQUESTS_TABLE" list
python scripts/requests.py --table "$REQUESTS_TABLE" show "$REQUEST_ID"
python scripts/requests.py --table "$REQUESTS_TABLE" status "$REQUEST_ID" contacted
python scripts/requests.py --table "$REQUESTS_TABLE" status "$REQUEST_ID" closed
```

`list` returns only IDs, times, and status. `show` displays contact details in your terminal; do not run it in CI, shared logs, screen recordings, or copied support transcripts. There is no staff web dashboard yet. Agree on who reviews requests and how often before enabling intake.

## Notifications and failures

Only new records trigger an alert. The stream contains keys, not contact data. The notifier reads the protected record to check expiration/notification status, sends a generic message to the operator, and marks it sent. Email contains no patient name, address, phone, request ID, or health detail.

Transient send/update failures return the failed sequence number for retry. After five retries or one hour, failed stream-batch metadata is sent to the encrypted failure queue. Stream delivery is at least once: a crash after sending but before marking the record can duplicate an alert. Do not interpret notification count as request count.

The retained failure queue stores metadata, not the complete request payload. Review the request table through authorized access to reconcile records whose `notificationStatus` is pending. The queue expires after 14 days; monitor it and investigate promptly. Correct SES identity/permissions/sandbox problems before reprocessing synthetic test requests.

CloudWatch alarms cover Lambda errors, HTTP 5xx, and the failure queue. Alarm actions are intentionally unset until the operations destination is selected. Connect them to a monitored destination before opening intake. The 5xx alarm can also fire when someone probes the deliberately disabled endpoint.

## Privacy and retention

- Private S3 bucket with CloudFront origin access control and HTTPS-only access.
- DynamoDB encryption, deletion protection, point-in-time recovery, and default 90-day TTL.
- Contact data is not written to application logs. API access logs contain request ID, route, and status only, with 30-day retention.
- No attachments, clinical free text, analytics, browser persistence, or full patient portal.
- Reads and status updates require IAM; there is no public lookup route.
- API Gateway throttling is a basic global control. Origin checks and honeypots are not strong anti-bot protection. Test abuse handling and decide on WAF/CAPTCHA or an EHR-hosted flow before launch. AWS HTTP APIs do not support direct WAF association; any edge protection must account for the direct API origin too.
- TTL removal is asynchronous. `show` and status updates reject expired records, but list results may include expired IDs until deletion. DynamoDB PITR can preserve older data within its recovery window; align live and backup retention with practice policy.
- If formal records-access auditing is required, configure the relevant CloudTrail data events and access reviews; this starter does not create an account-wide trail or compliance program.

## Further IAM review

The SAM template scopes runtime database operations to the created table, notification delivery to the configured SES identity/sender/recipient, and stream-failure delivery to the created queue. SAM generates Lambda execution roles and stream-read permissions. Baseline Lambda logging uses the standard execution-role policy.

To independently generate baseline SDK action policies from the actual Python code using AWS IAM Policy Autopilot:

```bash
uvx iam-policy-autopilot@latest generate-policies \
  "$PWD/backend/app.py" "$PWD/backend/notify.py" "$PWD/scripts/requests.py" \
  --service-hints dynamodb sesv2 --pretty
```

Include the real account and region flags when known. Static analysis does not replace reviewing the resource ARNs, conditions, or trigger permissions supplied by CloudFormation.

## Source references

- https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-httpapi.html
- https://docs.aws.amazon.com/lambda/latest/dg/python-package.html
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-metrics.html
- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
- https://aws.amazon.com/compliance/hipaa-compliance/
