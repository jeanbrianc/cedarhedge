# Cedar Hedge Counseling

Website and AWS foundation for **Hunter Lumsden, LMSW**, a Michigan telehealth psychotherapy practice.

The current site uses Open Sans, Hunter's supplied Cedar Hedge logo, and the approved practice copy. It remains in its **opening-soon state**: no form, no appointment requests, no confirmed insurers or rates.

## Run the website

No frontend dependencies or build step are required. From this repository:

```bash
python3 -m http.server 8000 --directory site
```

Open http://localhost:8000. If you prefer npm, `npm run dev` does the same thing; `npm install` is not needed.

## Included

- `site/`: complete static website and image assets.
- `template.yaml`: AWS SAM/CloudFormation for private S3 hosting, CloudFront, optional domain/DNS/ACM, API Gateway, Lambda, DynamoDB, optional SES notifications, retries, and monitoring.
- `backend/`: contact-only appointment-request endpoint, **disabled by default**, plus generic email notifications.
- `scripts/requests.py`: IAM-authorized operator access to request records and statuses. There is no public record-reading API or staff dashboard.
- `scripts/publish_site.sh`: upload to the website bucket of a selected AWS stack, with an account-ID check.
- `.github/workflows/ci.yml`: backend tests, site checks, shell/JavaScript checks, and infrastructure schema validation. CI does not deploy.

## AWS deployment

Follow [the deployment guide](docs/deployment.md). Deploy the stack in **us-east-1** so an optional CloudFront certificate is created in the correct region. Initial deployment works on an AWS-generated CloudFront address; registering a domain is a separate step.

The code is prepared for AWS, but committing it does not create AWS resources, purchase a domain, configure a mailbox, or activate intake. The existing ChatGPT-hosted preview is independent and remains available.

## Validate locally

Python 3.12 or 3.13 is suitable for local tests; the Lambda runtime is Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/check_site.py
node --check site/script.js
bash -n scripts/publish_site.sh
cfn-lint template.yaml --regions us-east-1
```

The Python SDK and its dependencies are pinned and packaged with Lambda. Update these pins deliberately as part of routine dependency maintenance.

## Scheduling scope

This is an **appointment-request backend**, not a calendar or EHR. It can save minimal contact information and alert the practice for manual follow-up. It does not reserve appointment slots, manage clinical records, take payments, or deliver telehealth visits.

Hunter has not chosen his EHR. Connecting the site's eventual booking button to that portal remains the preferred launch path. If a custom form is chosen, finish its UX, operating procedures, and abuse controls before enabling the endpoint. See [the API contract](docs/api.md) and [operating notes](docs/operations.md).

## Assets and practice details

- Logo supplied by Hunter; retained as `site/assets/cedar-hedge-logo.jpeg`.
- Shoreline is an original generated Northern Michigan-inspired image, not an actual practice location.
- Headshot is pending; initials are used instead of a fabricated photo.
- Adult-focused; final age eligibility, rates, credentialed insurers, contact details, and opening date are pending.
- No physical office address is published.
- `noindex, nofollow` remains enabled until a deliberate public launch.
