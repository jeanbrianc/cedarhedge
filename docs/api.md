# Appointment-request API

The public site currently has no form. This documents the backend contract for a future approved intake flow. It is not an appointment-booking calendar.

## POST /api/appointment-requests

Use the website's CloudFront origin. API responses are never cached. The API Gateway origin is also publicly reachable; an Origin header is a browser control, not caller authentication.

Required headers:

- `Content-Type: application/json`
- `Origin`: exact configured `AllowedOrigin`
- `Idempotency-Key`: a new random UUID v4 for a new request; reuse it for a retry with identical data.

Example JSON, using synthetic information:

```json
{
  "firstName": "Example",
  "lastName": "Person",
  "email": "test@example.com",
  "phone": "",
  "preferredContact": "email",
  "preferredTime": "morning",
  "consent": true,
  "website": ""
}
```

`preferredContact` is `email` or `phone`; its matching contact value is required. `preferredTime` is `morning`, `afternoon`, `evening`, or `any`. `website` is an optional empty honeypot. The remaining optional contact method can be blank. The payload is limited to 4 KiB. Names and contact values have length/control-character validation.

Only the documented fields are accepted. Free-text notes, symptoms, diagnoses, medications, attachments, insurance data, and extra fields are rejected. A user can still put sensitive text into a name field, so validation does not make this non-sensitive data.

| HTTP status | Meaning |
| --- | --- |
| 202 | Saved, or identical retry already saved; an appointment is not confirmed. |
| 400 | Invalid data, request ID, consent, payload size, or honeypot. |
| 403 | Missing or unapproved origin. |
| 409 | Request ID already belongs to different data; use a new UUID. |
| 415 | Unsupported content type. |
| 429 | API Gateway throttling. |
| 503 | Intake disabled, or storage unavailable; inspect the generic message. |

Success returns a generic message and request ID, never contact details. Saving is conditional; retries cannot overwrite another request. Storage failures never produce a success response. Email delivery runs independently from DynamoDB Streams so a failed alert does not discard the request.

The consent checkbox in a future UI must explain that this is permission for follow-up, not emergency care, confirmation of an appointment, or establishment of a clinician-client relationship. The stored consent marker is `contact-request-v1`; update the marker when that text changes. No patient response-time commitment is implied.

There is no public read/update/delete API. Operator access requires AWS IAM credentials scoped to the request table and its `by-status` index. See the operating guide.
