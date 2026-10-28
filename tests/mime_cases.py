"""MIME regressions run inside each native Odoo image; no transport calls."""
import base64
import unittest
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

from odoo.addons.mail_mailchannels.mime import convert, InvalidMessage


def parsed(headers=b'', body=b'Hello'):
    return BytesParser(policy=policy.compat32).parsebytes(
        b'From: sender@example.test\r\nTo: recipient@example.test\r\n'
        b'Message-ID: <mime@example.test>\r\nSubject: MIME fixture\r\n' + headers + b'\r\n' + body)


def convert_fixture(message):
    return convert(message, 'sender@example.test', ['recipient@example.test'])


class MimeCases(unittest.TestCase):
    def address_message(self, to):
        msg = EmailMessage()
        msg['From'] = 'sender@example.test'
        msg['To'] = to
        msg['Message-ID'] = '<address-list@example.test>'
        msg.set_content('Hello')
        return msg

    def test_empty_recipient_slots_keep_envelope_restriction(self):
        msg = self.address_message(',recipient@example.test,,other@example.test,')
        self.assertTrue(msg['To'].defects)
        payload = convert_fixture(msg)
        self.assertEqual(payload['personalizations'], [{'to': [{'email': 'recipient@example.test'}]}])

    def test_empty_slots_do_not_permit_invalid_recipient(self):
        msg = self.address_message(',recipient@example.test,broken-address')
        with self.assertRaises(InvalidMessage):
            convert_fixture(msg)

    def test_empty_sender_slot_still_rejected(self):
        msg = self.address_message('recipient@example.test')
        msg.replace_header('From', ',sender@example.test')
        with self.assertRaises(InvalidMessage):
            convert_fixture(msg)

    def test_valid_folded_base64(self):
        msg = parsed(b'Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n', b'SGVs\r\n bG8=')
        self.assertEqual(convert_fixture(msg)['content'], [{'type': 'text/plain', 'value': 'Hello'}])

    def test_corrupt_base64_body(self):
        for body in (b'SGVsbG8', b'SGVs!!!bG8=', b'A', b'SGVsbG8=AAAA'):
            with self.subTest(body=body), self.assertRaises(InvalidMessage):
                convert_fixture(parsed(b'Content-Type: text/plain\r\nContent-Transfer-Encoding: base64\r\n', body))

    def test_corrupt_base64_attachment(self):
        msg = parsed(b'Content-Type: multipart/mixed; boundary=b\r\n',
                     b'--b\r\nContent-Type: text/plain\r\n\r\nHello\r\n--b\r\n'
                     b'Content-Type: application/pdf\r\nContent-Disposition: attachment; filename=fixture.pdf\r\n'
                     b'Content-Transfer-Encoding: base64\r\n\r\nSGVsbG8\r\n--b--\r\n')
        with self.assertRaises(InvalidMessage):
            convert_fixture(msg)

    def test_unknown_transfer_encoding(self):
        with self.assertRaises(InvalidMessage):
            convert_fixture(parsed(b'Content-Transfer-Encoding: x-unknown\r\n'))

    def test_duplicate_envelope_and_identity_headers(self):
        for header in (b'From: other@example.test', b'To: other@example.test',
                       b'Subject: hidden subject', b'Message-ID: <other@example.test>'):
            with self.subTest(header=header), self.assertRaises(InvalidMessage):
                convert_fixture(parsed(header + b'\r\n'))

    def test_duplicate_mime_headers(self):
        for headers in (b'Content-Type: text/plain\r\nContent-Type: text/html\r\n',
                        b'Content-Transfer-Encoding: base64\r\nContent-Transfer-Encoding: 8bit\r\n'):
            with self.subTest(headers=headers), self.assertRaises(InvalidMessage):
                convert_fixture(parsed(headers))

    def test_missing_boundary(self):
        with self.assertRaises(InvalidMessage):
            convert_fixture(parsed(b'Content-Type: multipart/mixed; boundary=missing\r\n'))

    def test_signed_mime_rejected(self):
        with self.assertRaises(InvalidMessage):
            convert_fixture(parsed(b'Content-Type: multipart/signed; boundary=b\r\n',
                                   b'--b\r\nContent-Type: text/plain\r\n\r\nHello\r\n--b--\r\n'))

    def test_valid_charset_and_inline_binary(self):
        msg = EmailMessage()
        msg['From'] = 'sender@example.test'
        msg['To'] = 'recipient@example.test'
        msg['Message-ID'] = '<unicode@example.test>'
        msg['Subject'] = 'Résumé ✓'
        msg.set_content('café', charset='iso-8859-1')
        msg.add_alternative('<p>café<img src="cid:logo"></p>', subtype='html')
        msg.get_payload()[1].add_related(b'\x00\xffPNG fixture', maintype='image', subtype='png', cid='<logo>', filename='logo.png')
        payload = convert_fixture(msg)
        self.assertEqual(payload['subject'], 'Résumé ✓')
        self.assertEqual(payload['content'][0]['value'], 'café\n')
        self.assertIn('cid:logo', payload['content'][1]['value'])
        self.assertEqual(payload['attachments'][0]['content_id'], 'logo')
        self.assertEqual(base64.b64decode(payload['attachments'][0]['content']), b'\x00\xffPNG fixture')


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MimeCases))
if not result.wasSuccessful():
    raise AssertionError('MIME regressions failed')
print('MIME_CASES_PASS: ' + str(result.testsRun))
