import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import app
import notify


class Conflict(Exception):
    pass


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'INTAKE_ENABLED': 'true', 'ALLOWED_ORIGIN': 'https://cedar.example',
            'RETENTION_DAYS': '90', 'REQUESTS_TABLE': 'test-table'}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.table = MagicMock()
        self.table.meta.client.exceptions.ConditionalCheckFailedException = Conflict
        self.store = patch.object(app, 'request_table', return_value=self.table)
        self.store.start()
        self.addCleanup(self.store.stop)
        self.payload = {'firstName': 'Example', 'lastName': 'Person', 'email': 'test@example.com',
                        'preferredContact': 'email', 'preferredTime': 'morning', 'consent': True}
        self.event = {'requestContext': {'http': {'method': 'POST'}},
                      'headers': {'origin': 'https://cedar.example', 'content-type': 'application/json',
                                  'idempotency-key': '24c66918-4ef7-45ad-b522-d7463b794102'},
                      'body': json.dumps(self.payload)}

    def test_closed_does_not_read_body_or_call_storage(self):
        os.environ['INTAKE_ENABLED'] = 'false'
        self.event['body'] = 'sensitive malformed data'
        self.assertEqual(app.handler(self.event, None)['statusCode'], 503)
        self.table.put_item.assert_not_called()

    def test_missing_flag_is_closed(self):
        del os.environ['INTAKE_ENABLED']
        self.assertEqual(app.handler(self.event, None)['statusCode'], 503)
        self.table.put_item.assert_not_called()

    def test_health_information_fields_rejected(self):
        for field in ('symptoms', 'diagnosis', 'medications', 'notes'):
            self.event['body'] = json.dumps({**self.payload, field: 'sensitive text'})
            self.assertEqual(app.handler(self.event, None)['statusCode'], 400)
        self.table.put_item.assert_not_called()

    def test_wrong_origin_or_missing_origin_rejected(self):
        for origin in ('https://evil.example', ''):
            self.event['headers']['origin'] = origin
            self.assertEqual(app.handler(self.event, None)['statusCode'], 403)
        self.table.put_item.assert_not_called()

    def test_consent_must_be_boolean_true(self):
        for consent in (False, 'true', 1, None):
            self.event['body'] = json.dumps({**self.payload, 'consent': consent})
            self.assertEqual(app.handler(self.event, None)['statusCode'], 400)
        self.table.put_item.assert_not_called()

    def test_success_has_no_contact_data_in_response(self):
        with patch.object(app.time, 'time', return_value=1700000000):
            result = app.handler(self.event, None)
        self.assertEqual(result['statusCode'], 202)
        item = self.table.put_item.call_args.kwargs['Item']
        self.assertEqual(item['status'], 'new')
        self.assertEqual(item['expiresAt'], 1700000000 + 90 * 86400)
        self.assertNotIn('test@example.com', result['body'])
        self.assertNotIn('sourceIp', item)
        self.assertEqual(result['headers']['Cache-Control'], 'no-store')

    def test_matching_retry_does_not_duplicate_request(self):
        app.handler(self.event, None)
        stored = self.table.put_item.call_args.kwargs['Item']
        self.table.put_item.side_effect = Conflict()
        self.table.get_item.return_value = {'Item': stored}
        self.assertEqual(app.handler(self.event, None)['statusCode'], 202)

    def test_idempotency_key_cannot_overwrite_different_request(self):
        self.table.put_item.side_effect = Conflict()
        self.table.get_item.return_value = {'Item': {'fingerprint': 'different'}}
        self.assertEqual(app.handler(self.event, None)['statusCode'], 409)

    def test_store_failure_is_not_reported_as_success_or_logged_with_data(self):
        self.table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'sensitive test@example.com'}}, 'PutItem')
        with self.assertLogs(app.LOGGER, level='ERROR') as captured:
            result = app.handler(self.event, None)
        self.assertEqual(result['statusCode'], 503)
        self.assertNotIn('test@example.com', ''.join(captured.output) + result['body'])

    def test_invalid_json_and_body_limits(self):
        for body in ('[1,2]', 'not json', 'x' * 10000):
            self.event['body'] = body
            self.assertEqual(app.handler(self.event, None)['statusCode'], 400)
        self.table.put_item.assert_not_called()

    def test_base64_body(self):
        self.event['body'] = base64.b64encode(json.dumps(self.payload).encode()).decode()
        self.event['isBase64Encoded'] = True
        self.assertEqual(app.handler(self.event, None)['statusCode'], 202)

    def test_contact_validation(self):
        for change in ({'email': 'invalid'}, {'preferredContact': 'phone'}, {'firstName': 'A\nB'},
                       {'preferredTime': 'whenever'}, {'website': 'spam.example'}):
            self.event['body'] = json.dumps({**self.payload, **change})
            self.assertEqual(app.handler(self.event, None)['statusCode'], 400)
        self.table.put_item.assert_not_called()

    def test_media_type_and_uuid_required(self):
        self.event['headers']['content-type'] = 'text/plain'
        self.assertEqual(app.handler(self.event, None)['statusCode'], 415)
        self.event['headers']['content-type'] = 'application/json'
        self.event['headers']['idempotency-key'] = 'not-a-uuid'
        self.assertEqual(app.handler(self.event, None)['statusCode'], 400)
        self.table.put_item.assert_not_called()


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'NOTIFY_FROM': 'sender@example.com', 'NOTIFY_TO': 'operator@example.com'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.table = MagicMock()
        self.table.get_item.return_value = {'Item': {'firstName': 'Sensitive', 'email': 'patient@example.com',
                                                     'notificationStatus': 'pending', 'expiresAt': 9999999999}}
        self.mail = MagicMock()
        for target, attribute, value in ((notify, 'request_table', self.table), (notify, 'ses', self.mail)):
            patcher = patch.object(target, attribute, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.event = {'Records': [{'eventName': 'INSERT', 'dynamodb': {
            'SequenceNumber': '42', 'Keys': {'requestId': {'S': 'example-id'}}}}]}

    def test_notification_excludes_patient_data(self):
        self.assertEqual(notify.handler(self.event, None), {'batchItemFailures': []})
        sent = repr(self.mail.send_email.call_args)
        self.assertNotIn('patient@example.com', sent)
        self.assertNotIn('Sensitive', sent)
        self.assertNotIn('example-id', sent)
        self.table.update_item.assert_called_once()

    def test_failure_is_retried(self):
        self.mail.send_email.side_effect = ClientError({'Error': {'Code': 'ThrottlingException'}}, 'SendEmail')
        with self.assertLogs(notify.LOGGER, level='ERROR'):
            result = notify.handler(self.event, None)
        self.assertEqual(result, {'batchItemFailures': [{'itemIdentifier': '42'}]})
        self.table.update_item.assert_not_called()

    def test_sent_expired_missing_and_modified_records_do_not_send(self):
        for item in ({'notificationStatus': 'sent'}, {'expiresAt': 1}, None):
            self.table.get_item.return_value = {'Item': item}
            self.assertEqual(notify.handler(self.event, None), {'batchItemFailures': []})
        self.event['Records'][0]['eventName'] = 'MODIFY'
        self.assertEqual(notify.handler(self.event, None), {'batchItemFailures': []})
        self.mail.send_email.assert_not_called()


if __name__ == '__main__':
    unittest.main()
