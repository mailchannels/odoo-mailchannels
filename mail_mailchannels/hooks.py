from odoo.exceptions import UserError


def uninstall_hook(env):
    # Module removal is maintenance work. Keep the checks and removal in the
    # same transaction; prevent concurrent receipt/configuration writes between
    # the checks and Odoo dropping our table/fields.
    env.cr.execute('LOCK TABLE mailchannels_operation, ir_mail_server IN SHARE ROW EXCLUSIVE MODE')
    # Odoo can already have a REPEATABLE READ snapshot before acquiring these
    # locks. A fresh read cursor sees writers that committed while we waited;
    # the original transaction check also includes its own uncommitted rows.
    # These read locks are compatible with our held SHARE ROW EXCLUSIVE locks.
    with env.registry.cursor() as cr:
        cr.execute('SELECT EXISTS(SELECT 1 FROM mailchannels_operation), '
                   'EXISTS(SELECT 1 FROM ir_mail_server WHERE mc_enabled AND active)')
        committed_receipts, committed_active = cr.fetchone()
    if committed_receipts or env['mailchannels.operation'].sudo().search_count([]):
        raise UserError(
            'MailChannels submission receipts exist. Uninstall would erase duplicate-send protection. '
            'Keep the module installed and archive its outgoing servers. A reviewed receipt migration '
            'and mail-queue retirement plan is required before removal; do not delete receipts to bypass this check.'
        )
    if committed_active or env['ir.mail_server'].sudo().with_context(active_test=False).search_count(
            [('mc_enabled', '=', True), ('active', '=', True)]):
        raise UserError(
            'Archive active MailChannels outgoing servers before uninstalling. '
            'Removing the transport while these servers remain active could route mail through SMTP.'
        )
