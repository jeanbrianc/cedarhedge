# Deploy to AWS

## 1. Select the account

Use a dedicated AWS account for this practice if practical, even if it is billed within Brian's AWS organization. The template creates runtime roles and does not need access to unrelated projects. Use your normal AWS CLI login/profile; no credentials belong in this repository.

Required local tools: AWS CLI v2, AWS SAM CLI, Python 3.13, and Node.js for the website syntax check. Docker is an alternative for SAM builds when the matching Python interpreter is unavailable (`sam build --use-container`).

Confirm the intended account first:

```bash
aws sts get-caller-identity
```

Set `AWS_PROFILE` if needed and set `AWS_EXPECTED_ACCOUNT_ID` to the intended 12-digit account ID before uploading the website. The upload script compares it to the active identity.

## 2. Build and deploy the closed practice

From the repository root:

```bash
sam build --template-file template.yaml
sam deploy --guided --stack-name cedarhedge --region us-east-1
```

During guided setup:

- Keep `IntakeEnabled=false`.
- Leave domain, hosted-zone, origin, SES identity, and notification parameters empty for the first preview.
- Allow SAM to create its deployment artifact bucket and the scoped runtime IAM roles.
- Review the CloudFormation change set before executing it.
- Save local settings to `samconfig.toml` if desired; that file is ignored by Git.

The API has one unauthenticated POST route because prospective clients do not have accounts; its Lambda rejects all requests while intake is disabled. There is no anonymous request lookup or update endpoint.

This provisions resources and may incur AWS charges. `sam build`, local tests, and CI do not deploy anything. No AWS deployment has been performed as part of the repository initialization.

After deployment succeeds, upload the website:

```bash
./scripts/publish_site.sh cedarhedge us-east-1
aws cloudformation describe-stacks --stack-name cedarhedge --region us-east-1 \
  --query 'Stacks[0].Outputs' --output table
```

Open the `SiteUrl` output. Check mobile navigation, FAQ expansion, logo/assets, HTTPS, and the opening-soon wording. Verify a POST to `/api/appointment-requests` returns HTTP 503 with the closed-practice message. Use synthetic data only.

The upload script mirrors only `site/` into the stack's website bucket. `--delete` removes obsolete website assets from that bucket; bucket versioning retains prior object versions for 30 days. It never uploads backend code, environment files, or documents.

## 3. Connect the real domain

No domain has been registered or checked for availability. Register the chosen domain in Hunter's ownership and enable renewal protection. Create a public Route 53 hosted zone if one does not exist, and delegate its nameservers through the registrar.

For `cedarhedgecounseling.com`, provide:

- `SiteDomainName`: `cedarhedgecounseling.com`.
- `HostedZoneId`: the actual public hosted-zone ID.

Run `sam deploy --guided` again, preserving other parameter values. Both domain parameters must be supplied together. The stack creates DNS-validated ACM coverage and A/AAAA aliases for the apex and `www`. Keep the entire stack in `us-east-1`; CloudFront requires its ACM certificate there.

ACM validation can remain pending until DNS delegation is correct. The stack does not buy the domain or change registrar nameservers.

## 4. Business email

A mailbox such as `hunter@cedarhedgecounseling.com` is separate from SES. Set up the selected email host, then add its exact verification, MX, SPF, DKIM, and DMARC records. Do not invent these records; use values from that provider. This template deliberately does not overwrite MX/TXT records.

SES is only for outbound application notifications. Verify the sender/domain in SES in `us-east-1`, publish its DKIM records, and confirm send permissions and recipient requirements. SES sandbox accounts can only send to verified recipients, so a verified operator mailbox can be tested before requesting production access.

## 5. Choose how appointments will work

**EHR/portal path:** add a clearly labeled link to the selected portal after Hunter approves launch. Leave `IntakeEnabled=false`; the custom API is unnecessary for this path. No patient information needs to pass through this website.

**Custom request path:** first finish the user-facing form and operator workflow. Then provide all of:

- `AllowedOrigin`: the exact canonical HTTPS website origin, without a trailing slash.
- `NotificationFrom`: the chosen verified sender address.
- `NotificationTo`: the practice mailbox.
- `SesIdentityArn`: the actual same-region SES identity ARN covering the sender.
- `RetentionDays`: the approved contact-request retention period.
- `IntakeEnabled`: `true` only when ready to receive and process requests.

The CloudFormation rules prevent accidental enabling with incomplete configuration. Existing site copy and the frontend's no-form assertion must also be deliberately updated before offering intake. Update the CSP's `form-action 'none'` if a native form is introduced. Use one canonical origin (or implement an explicit allowlist if both apex and www should submit).

## Updates and rollback

Rebuild and deploy backend/infrastructure changes with `sam build` and `sam deploy`. Upload static changes with `scripts/publish_site.sh`. To roll back, check out the previous Git commit, rebuild/deploy its template, and upload its site. Do not directly modify runtime resources outside CloudFormation for routine releases.

For stack validation failures, inspect CloudFormation's deployment validation/events before executing the change set. No account-side validation or live integration testing was performed during repository preparation.

## Costs and retained resources

This template uses standard CloudFront billing, not an automatically enrolled flat-rate bundle. A CloudFront pricing-plan choice can be evaluated separately. Costs include DNS when a zone is provisioned, domain renewal, S3 versions, Lambda/API traffic, DynamoDB storage/PITR, logs, alarms, and optional SES/SQS. Email hosting is a separate subscription. No EC2, RDS, VPC, NAT gateway, or paid support plan is created.

DynamoDB, S3, log groups, and the notification failure queue are retained on stack deletion/replacement. DynamoDB deletion protection is enabled. They can continue to incur charges after a stack is removed; deliberately inventory and dispose of them according to the practice's retention decisions. Never delete patient records as a routine deployment cleanup.
