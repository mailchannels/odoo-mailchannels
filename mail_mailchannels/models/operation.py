from odoo import fields, models


class MailchannelsOperation(models.Model):
    _name = 'mailchannels.operation'
    _description = 'MailChannels Submission Receipt'
    _order = 'create_date desc'

    _key_unique = models.Constraint('UNIQUE(operation_key)', 'Submission identity must be unique.')

    operation_key = fields.Char(required=True, index=True, readonly=True)
    payload_hash = fields.Char(required=True, readonly=True)
    message_id = fields.Char(required=True, readonly=True)
    server_reference = fields.Integer(readonly=True)
    state = fields.Selection([('submitting', 'Uncertain — submission started'),
                              ('accepted', 'Accepted by API'),
                              ('rejected', 'Rejected'), ('unknown', 'Unknown outcome')],
                             required=True, readonly=True)
    http_status = fields.Integer(readonly=True)
    request_id = fields.Char(readonly=True)
    # No body, API key, recipient list or provider response is stored.
