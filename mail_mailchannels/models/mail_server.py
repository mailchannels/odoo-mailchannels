import hashlib
import json
import os
import re
from urllib.parse import urlsplit

import requests
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.addons.base.models.ir_mail_server import MailDeliveryException

from ..mime import convert

ENDPOINT = 'https://api.mailchannels.net/tx/v1/send'
# Administrator-only system parameter for testing against a non-production Email API host.
ENDPOINT_PARAM = 'mail_mailchannels.api_endpoint'


def _valid_endpoint(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or '').lower()
    return (parts.scheme == 'https' and ':' not in parts.netloc
            and not parts.username and not parts.password
            and not parts.query and not parts.fragment and parts.path.endswith('/send')
            and (host == 'mailchannels.net' or host.endswith('.mailchannels.net')))


def _api_errors(response):
    # The API explains refusals in {"errors": [...]}; show a bounded excerpt, never the request.
    try:
        errors = response.json().get('errors')
    except (ValueError, AttributeError):
        return ''
    if not isinstance(errors, list) or not errors:
        return ''
    return ' ' + ' '.join(str(e) for e in errors[:3])[:300]


class APISession:
    def __init__(self, server, sender):
        self.server = server
        self.from_filter = server.from_filter
        self.smtp_from = sender
        self.mail_server_name = server.display_name

    def quit(self):
        return None

    def send_message(self, message, from_addr, to_addrs):
        payload = convert(message, from_addr, to_addrs)
        self.server._mc_submit(payload, str(message['Message-ID']))


class MailServer(models.Model):
    _inherit = 'ir.mail_server'

    mc_enabled = fields.Boolean('Use MailChannels Email API', groups='base.group_system')
    mc_key_variable = fields.Char('API key environment variable', default='MAILCHANNELS_ODOO_API_KEY',
                                  groups='base.group_system', copy=False)

    def _mc_key(self):
        self.ensure_one()
        name = self.mc_key_variable or ''
        if not re.fullmatch(r'MAILCHANNELS_[A-Z0-9_]*API_KEY', name):
            raise UserError('Configure a MAILCHANNELS_*API_KEY environment variable.')
        key = os.environ.get(name, '')
        if not key or any(c in key for c in '\r\n'):
            raise UserError('MailChannels API key is not configured on the server.')
        return key

    @api.model
    def _connect__(self, host=None, port=None, user=None, password=None, encryption=None,
                   smtp_from=None, ssl_certificate=None, ssl_private_key=None,
                   smtp_debug=False, mail_server_id=None, allow_archived=False):
        if self._disable_send():
            return None
        server = self.env['ir.mail_server']
        if mail_server_id:
            server = self.sudo().browse(mail_server_id)
            self._check_forced_mail_server(server, allow_archived, smtp_from)
        elif not host:
            server, smtp_from = self.sudo()._find_mail_server(smtp_from)
        if server and server.mc_enabled:
            server._mc_key()
            server._mc_endpoint()
            return APISession(server, smtp_from)
        return super()._connect__(host=host, port=port, user=user, password=password,
                                  encryption=encryption, smtp_from=smtp_from,
                                  ssl_certificate=ssl_certificate, ssl_private_key=ssl_private_key,
                                  smtp_debug=smtp_debug, mail_server_id=mail_server_id,
                                  allow_archived=allow_archived)

    def test_smtp_connection(self, autodetect_max_email_size=False):
        if autodetect_max_email_size:
            self.ensure_one()
            if self.mc_enabled:
                raise UserError('MailChannels cannot automatically detect an SMTP size limit. '
                                'Configure attachment handling using the current Email API limits.')
            # Odoo19's Detect Max Limit action expects the native result and side effects.
            return super().test_smtp_connection(autodetect_max_email_size=True)
        for server in self:
            if not server.mc_enabled:
                super(MailServer, server).test_smtp_connection()
                continue
            # This separate validation action never processes business mail or writes a send receipt.
            message = server._build_email__(server._get_test_email_from(), [server._get_test_email_to()],
                                           'MailChannels configuration validation', 'Dry-run only.')
            session = APISession(server, message['From'])
            sender, recipients, message = server._prepare_email_message__(message, session)
            payload = convert(message, sender, recipients)
            try:
                response = server._mc_request(payload, dry_run=True)
            except requests.RequestException:
                raise UserError('MailChannels validation could not complete. No email was sent.') from None
            if response.status_code != 200:
                raise UserError('MailChannels dry-run validation failed (HTTP %s).%s'
                                % (response.status_code, _api_errors(response)))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': 'Validation completed; no email sent.', 'sticky': False}}

    def _get_test_email_to(self):
        # Odoo's default noreply@odoo.com is refused by accounts that may only send to verified
        # addresses (new accounts without a card); the dry-run goes to the signed-in user instead.
        self.ensure_one()
        if self.mc_enabled and self.env.user.email:
            return self.env.user.email
        return super()._get_test_email_to()

    def _mc_endpoint(self):
        # Only base.group_system can read or write ir.config_parameter; unset means production.
        params = self.env['ir.config_parameter'].sudo()
        # Odoo 20 replaced get_param with typed getters.
        value = params.get_str(ENDPOINT_PARAM) if hasattr(params, 'get_str') else params.get_param(ENDPOINT_PARAM)
        url = (value or '').strip() or ENDPOINT
        if not _valid_endpoint(url):
            raise UserError('The MailChannels endpoint override must be an https://*.mailchannels.net/.../send URL. No email was sent.')
        return url

    def _mc_request(self, payload, dry_run=False, endpoint=None):
        return requests.post(endpoint or self._mc_endpoint(), params={'dry-run': 'true'} if dry_run else None,
                             json=payload, headers={'X-Api-Key': self._mc_key(), 'User-Agent': 'MailChannels-Odoo/0.1'},
                             timeout=(5, 30), allow_redirects=False, verify=True)

    def _mc_submit(self, payload, message_id):
        self.ensure_one()
        endpoint = self._mc_endpoint()  # Refuse a bad override before any receipt is reserved.
        body_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        recipients = sorted(item['email'].casefold() for p in payload['personalizations']
                            for kind in ('to', 'cc', 'bcc') for item in p.get(kind, []))
        keys = sorted(hashlib.sha256(json.dumps([self.id, message_id, recipient],
                                               separators=(',', ':')).encode()).hexdigest()
                      for recipient in set(recipients))
        # Separate committed receipts survive rollback of the business transaction.
        # Reserve every recipient atomically; partial overlaps fail closed.
        with self.env.registry.cursor() as cr:
            for key in keys:
                lock = int.from_bytes(bytes.fromhex(key[:16]), 'big', signed=True)
                cr.execute('SELECT pg_advisory_xact_lock(%s)', [lock])
            env = self.env(cr=cr)
            receipts = env['mailchannels.operation'].sudo()
            previous = receipts.search([('operation_key', 'in', keys)])
            if previous:
                if (len(previous) == len(keys) and
                        all(row.state == 'accepted' and row.payload_hash == body_hash for row in previous)):
                    return
                raise MailDeliveryException('MailChannels recipients already have submission records. Review before any resend.')
            # Database uniqueness also protects against stale transaction snapshots.
            rows = receipts.create([{'operation_key': key, 'payload_hash': body_hash,
                                     'message_id': message_id, 'server_reference': self.id,
                                     'state': 'submitting'} for key in keys])
            receipt_ids = rows.ids
            cr.commit()
        state, status, request_id, provider_id = 'unknown', 0, '', ''
        try:
            response = self._mc_request(payload, endpoint=endpoint)
            status = response.status_code
            if status == 202:
                state = 'accepted'
                try:
                    data = response.json()
                    candidate = data.get('request_id', '') if isinstance(data, dict) else ''
                    # Request IDs are base64, so '=', '+' and '/' occur.
                    request_id = candidate if isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9._:=+/-]{1,200}', candidate) else ''
                    results = data.get('results') if isinstance(data, dict) else None
                    # One personalization per submission, so one result carries its Message-ID.
                    if isinstance(results, list) and len(results) == 1 and isinstance(results[0], dict):
                        candidate = results[0].get('message_id', '')
                        if isinstance(candidate, str) and re.fullmatch(r'<[A-Za-z0-9._=+/-]{1,200}@[A-Za-z0-9.-]{1,200}>', candidate):
                            provider_id = candidate
                except (ValueError, TypeError):
                    pass  # HTTP acceptance is not negated by a malformed receipt body.
            elif status in (400, 401, 403, 404, 413, 422, 429):
                state = 'rejected'
        except requests.RequestException:
            pass  # Unknown submission outcome: never automatically retry.
        finally:
            with self.env.registry.cursor() as cr:
                self.env(cr=cr)['mailchannels.operation'].sudo().browse(receipt_ids).write(
                    {'state': state, 'http_status': status, 'request_id': request_id,
                     'provider_message_id': provider_id or False})
                cr.commit()
        if state != 'accepted':
            raise MailDeliveryException('MailChannels submission %s (HTTP %s). Review the receipt before any resend.' % (state, status or 'unknown'))
