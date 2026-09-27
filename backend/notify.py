"""Notify the operator without copying patient information into email or logs."""
import logging
import os
import time
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import BotoCoreError, ClientError

from app import SDK_CONFIG, request_table

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


@lru_cache(maxsize=1)
def ses():
    return boto3.client("sesv2", config=SDK_CONFIG)


def handler(event, context):
    failures = []
    for record in event.get("Records", []):
        if record.get("eventName") != "INSERT":
            continue
        sequence = record["dynamodb"]["SequenceNumber"]
        request_id = record["dynamodb"]["Keys"]["requestId"]["S"]
        try:
            table = request_table()
            item = table.get_item(Key={"requestId": request_id}, ConsistentRead=True).get("Item")
            if not item or item.get("notificationStatus") == "sent" or int(item["expiresAt"]) <= int(time.time()):
                continue
            ses().send_email(
                FromEmailAddress=os.environ["NOTIFY_FROM"],
                Destination={"ToAddresses": [os.environ["NOTIFY_TO"]]},
                Content={"Simple": {
                    "Subject": {"Data": "New Cedar Hedge appointment request", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": "A new request is available in the protected request store. "
                                               "Use your authorized AWS access to review it. "
                                               "No patient information is included in this notification.", "Charset": "UTF-8"}}}},
            )
            table.update_item(Key={"requestId": request_id},
                              UpdateExpression="SET notificationStatus = :sent",
                              ExpressionAttributeValues={":sent": "sent"},
                              ConditionExpression=Attr("requestId").exists())
        except (ClientError, BotoCoreError):
            LOGGER.error("request_notification_failed")
            failures.append({"itemIdentifier": sequence})
    # Stream delivery is at least once; a crash after SES sends can duplicate an alert.
    return {"batchItemFailures": failures}
