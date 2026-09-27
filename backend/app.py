"""Minimal contact-only appointment requests; closed until explicitly enabled."""
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
SDK_CONFIG = Config(retries={"total_max_attempts": 3, "mode": "standard"},
                    connect_timeout=2, read_timeout=3)
MAX_BODY_BYTES = 4096
ALLOWED_FIELDS = {"firstName", "lastName", "email", "phone", "preferredContact",
                  "preferredTime", "consent", "website"}
PREFERRED_TIMES = {"morning", "afternoon", "evening", "any"}


@lru_cache(maxsize=1)
def request_table():
    return boto3.resource("dynamodb", config=SDK_CONFIG).Table(os.environ["REQUESTS_TABLE"])


def response(status, message, request_id=None):
    body = {"message": message}
    if request_id:
        body["requestId"] = request_id
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json", "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff"},
            "body": json.dumps(body)}


def text_field(payload, key, maximum, required=True):
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise ValueError("Invalid field type.")
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise ValueError("Missing or oversized field.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Control characters are not allowed.")
    return value


def validate_payload(payload):
    if not isinstance(payload, dict) or set(payload) - ALLOWED_FIELDS:
        raise ValueError("Only contact and scheduling preference fields are accepted.")
    if payload.get("consent") is not True:
        raise ValueError("Contact consent is required.")
    data = {"firstName": text_field(payload, "firstName", 80),
            "lastName": text_field(payload, "lastName", 80),
            "email": text_field(payload, "email", 254, required=False),
            "phone": text_field(payload, "phone", 30, required=False),
            "preferredContact": text_field(payload, "preferredContact", 5),
            "preferredTime": text_field(payload, "preferredTime", 9),
            "consent": True}
    if data["preferredContact"] not in {"email", "phone"}:
        raise ValueError("Select email or phone.")
    if data["preferredTime"] not in PREFERRED_TIMES:
        raise ValueError("Select a scheduling preference.")
    if data["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", data["email"]):
        raise ValueError("Provide a valid email address.")
    if data["phone"]:
        if not re.fullmatch(r"[+()0-9 .-]+", data["phone"]):
            raise ValueError("Provide a valid phone number.")
        if not 10 <= len(re.sub(r"\D", "", data["phone"])) <= 15:
            raise ValueError("Provide a valid phone number.")
    if not data[data["preferredContact"]]:
        raise ValueError("Provide the selected contact method.")
    return data


def parse_body(event):
    raw = event.get("body") or ""
    if not isinstance(raw, str) or len(raw) > MAX_BODY_BYTES * 2:
        raise ValueError("Request body is too large.")
    try:
        body = base64.b64decode(raw, validate=True) if event.get("isBase64Encoded") else raw.encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            raise ValueError("Request body is too large.")
        return json.loads(body.decode("utf-8"))
    except (binascii.Error, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Provide a valid JSON request.") from exc


def handler(event, context):
    # Check before reading or validating any submitted personal information.
    if os.environ.get("INTAKE_ENABLED", "false") != "true":
        return response(503, "Cedar Hedge Counseling is not accepting appointment requests yet.")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method != "POST":
        return response(405, "Method not allowed.")
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "")
    if not allowed_origin or headers.get("origin") != allowed_origin:
        return response(403, "Request origin is not allowed.")
    # Origin checking limits browser access; it is not authentication or bot protection.
    if str(headers.get("content-type", "")).split(";", 1)[0].strip().lower() != "application/json":
        return response(415, "Content-Type must be application/json.")
    try:
        request_id = str(uuid.UUID(str(headers.get("idempotency-key", "")), version=4))
        original_id = str(headers.get("idempotency-key", "")).lower()
        if request_id != original_id:
            raise ValueError("Invalid request ID.")
        payload = parse_body(event)
        data = validate_payload(payload)
        if text_field(payload, "website", 200, required=False):
            return response(400, "Unable to accept this request.")
    except (ValueError, TypeError, AttributeError):
        return response(400, "Check your contact details, consent, and request ID. Do not include health information.")
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    now = int(time.time())
    item = {"requestId": request_id, "createdAt": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "expiresAt": now + int(os.environ.get("RETENTION_DAYS", "90")) * 86400,
            "status": "new", "notificationStatus": "pending", "fingerprint": fingerprint,
            "consentVersion": "contact-request-v1", **data}
    try:
        table = request_table()
        try:
            table.put_item(Item=item, ConditionExpression=Attr("requestId").not_exists())
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            existing = table.get_item(Key={"requestId": request_id}, ConsistentRead=True).get("Item", {})
            if existing.get("fingerprint") != fingerprint:
                return response(409, "Use a new request ID for different contact details.")
    except (ClientError, BotoCoreError):
        # Never log the event, body, exception text, contact details, or SDK wire data.
        LOGGER.error("request_storage_failed")
        return response(503, "We could not save your request. Please try again later.")
    return response(202, "Your request was saved. This does not confirm an appointment.", request_id)
