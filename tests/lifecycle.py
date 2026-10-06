"""Executed by run.py in its disposable, network-isolated database only."""
import hashlib
import json
from unittest.mock import patch
from odoo.exceptions import UserError

params = env['ir.config_parameter'].sudo()
module = env['ir.module.module'].search([('name', '=', 'mail_mailchannels')])


def set_marker(key, value):
    row = params.search([('key', '=', key)])
    if row:
        row.write({'value': value})
    else:
        params.create({'key': key, 'value': value})


def get_marker(key):
    return params.search([('key', '=', key)]).value


def receipt_digest():
    rows = env['mailchannels.operation'].sudo().search([], order='id').read(
        ['operation_key', 'payload_hash', 'message_id', 'server_reference', 'state', 'http_status', 'request_id'])
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def blocked(expected):
    before = receipt_digest()
    try:
        module.button_immediate_uninstall()
    except UserError as exc:
        assert expected in str(exc), str(exc)
        env.cr.rollback()
        env.invalidate_all()
    else:
        raise AssertionError('Uninstall should have been blocked')
    assert module.state == 'installed', module.state
    assert receipt_digest() == before


with patch('requests.post', side_effect=AssertionError('Lifecycle operations must not send')):
    if PHASE == 'seed':
        server = env['ir.mail_server'].create({'name': 'Lifecycle API', 'mc_enabled': True})
        smtp = env['ir.mail_server'].create({'name': 'Lifecycle SMTP', 'smtp_host': 'smtp.example.invalid', 'sequence': 99})
        # Synthetic receipts supplement the real mocked-submission receipts from
        # native.py. No live service is reachable in this disposable fixture.
        for state in ('submitting', 'accepted', 'rejected', 'unknown'):
            env['mailchannels.operation'].sudo().create({
                'operation_key': 'lifecycle-' + state, 'payload_hash': 'fixture-digest',
                'message_id': '<lifecycle-' + state + '@example.invalid>',
                'server_reference': server.id, 'state': state})
        set_marker('fixture.lifecycle.receipts', receipt_digest())
        set_marker('fixture.lifecycle.smtp', str(smtp.id))
        set_marker('fixture.lifecycle.api', str(server.id))
        env.cr.commit()
    elif PHASE == 'verify_upgrade':
        assert module.state == 'installed'
        assert receipt_digest() == get_marker('fixture.lifecycle.receipts')
        server = env['ir.mail_server'].browse(int(get_marker('fixture.lifecycle.api')))
        assert server.active and server.mc_enabled
        smtp = env['ir.mail_server'].browse(int(get_marker('fixture.lifecycle.smtp')))
        assert smtp.active and not smtp.mc_enabled and smtp.smtp_host == 'smtp.example.invalid' and smtp.sequence == 99
    elif PHASE == 'block_receipts':
        blocked('submission receipts exist')
    elif PHASE == 'block_active':
        # TEST-ONLY deletion in a newly created fixture database. This is NOT
        # an operator bypass recipe and must never be used on deployment data.
        env['mailchannels.operation'].sudo().search([]).unlink()
        env.cr.commit()
        blocked('Archive active MailChannels')
    elif PHASE == 'stale_snapshot':
        from odoo.addons.mail_mailchannels.hooks import uninstall_hook
        assert not env['mailchannels.operation'].sudo().search_count([])
        # Establish a snapshot with no receipts, then commit a receipt through
        # another cursor exactly as the transport does. The old snapshot must
        # remain empty so the fresh-cursor guard is necessary for this test.
        with env.registry.cursor() as cr:
            late = env(cr=cr)['mailchannels.operation'].sudo().create({
                'operation_key': 'lifecycle-late', 'payload_hash': 'fixture',
                'message_id': '<late@example.invalid>', 'state': 'submitting'})
            late_id = late.id
            cr.commit()
        assert not env['mailchannels.operation'].sudo().search_count([])
        try:
            uninstall_hook(env)
        except UserError as exc:
            assert 'submission receipts exist' in str(exc)
        else:
            raise AssertionError('A stale snapshot hid a committed receipt')
        env.cr.rollback()
        env.invalidate_all()
        row = env['mailchannels.operation'].sudo().browse(late_id)
        assert row.exists() and row.state == 'submitting'
        row.unlink()  # Synthetic fixture only; never deployment recovery.
        env.cr.commit()
    elif PHASE == 'uninstall':
        assert not env['mailchannels.operation'].sudo().search_count([])
        env['ir.mail_server'].with_context(active_test=False).search([('mc_enabled', '=', True)]).write({'active': False})
        env.cr.commit()
        module.button_immediate_uninstall()
    elif PHASE == 'verify_removed':
        assert module.state == 'uninstalled'
        assert 'mailchannels.operation' not in env.registry
        assert 'mc_enabled' not in env['ir.mail_server']._fields
        api = env['ir.mail_server'].with_context(active_test=False).browse(int(get_marker('fixture.lifecycle.api')))
        assert api.exists() and not api.active
        smtp = env['ir.mail_server'].browse(int(get_marker('fixture.lifecycle.smtp')))
        assert smtp.active and smtp.smtp_host == 'smtp.example.invalid' and smtp.sequence == 99
    else:
        raise AssertionError('Unknown lifecycle phase')
print('LIFECYCLE_PASS: ' + PHASE)
