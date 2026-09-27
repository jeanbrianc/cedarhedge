"""IAM-authorized operator CLI. Treat show output as sensitive patient information."""
import argparse
import json
import sys
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError


def json_value(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    raise TypeError('Unsupported JSON value')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', required=True)
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--profile', default=None)
    actions = parser.add_subparsers(dest='action', required=True)
    listing = actions.add_parser('list')
    listing.add_argument('--status', choices=['new', 'contacted', 'closed'], default='new')
    actions.add_parser('show').add_argument('request_id')
    status = actions.add_parser('status')
    status.add_argument('request_id')
    status.add_argument('value', choices=['new', 'contacted', 'closed'])
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    table = session.resource('dynamodb').Table(args.table)
    try:
        if args.action == 'list':
            # The index returns keys and status only; contact details require an explicit show.
            for page in table.meta.client.get_paginator('query').paginate(
                    TableName=args.table, IndexName='by-status',
                    KeyConditionExpression=Key('status').eq(args.status), ScanIndexForward=False):
                for item in page.get('Items', []):
                    print(json.dumps(item, default=json_value))
        elif args.action == 'show':
            item = table.get_item(Key={'requestId': args.request_id}, ConsistentRead=True).get('Item')
            if not item or int(item['expiresAt']) <= int(time.time()):
                print('Request not found or expired.', file=sys.stderr)
                return 1
            item.pop('fingerprint', None)
            print(json.dumps(item, indent=2, default=json_value))
        else:
            table.update_item(Key={'requestId': args.request_id},
                              UpdateExpression='SET #status = :status',
                              ExpressionAttributeNames={'#status': 'status'},
                              ExpressionAttributeValues={':status': args.value},
                              ConditionExpression=Attr('requestId').exists() & Attr('expiresAt').gt(int(time.time())))
            print('Status updated.')
        return 0
    except (ClientError, BotoCoreError):
        print('AWS operation failed. Check account, permissions, table, and request ID.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
