from odoo import models
from odoo.tools.mail import decode_message_header, unfold_references


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _get_bounced_message_data(self, message, message_dict):
        bounced_message, reference_ids = super()._get_bounced_message_data(message, message_dict)
        if bounced_message:
            return bounced_message, reference_ids
        # A DSN quotes the Message-ID MailChannels assigned; translate it through our receipts.
        quoted = [ref.strip() for ref in unfold_references(decode_message_header(message, 'Message-Id'))]
        if not quoted:
            return bounced_message, reference_ids
        receipts = self.env['mailchannels.operation'].sudo().search(
            [('provider_message_id', 'in', quoted)], order='id desc', limit=1)
        if receipts:
            original = self.env['mail.message'].search(
                [('message_id', '=', receipts.message_id)], order='create_date DESC, id DESC', limit=1)
            if original:
                return original, list(reference_ids or []) + [receipts.message_id]
        return bounced_message, reference_ids
