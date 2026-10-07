"""Native sales-template/PDF transport acceptance; synthetic records, no provider."""
import base64
from unittest.mock import patch

Server=env['ir.mail_server']
server=Server.create({'name':'Business API fixture','mc_enabled':True,'from_filter':'example.test','sequence':1})
env.company.email='store@example.test'
env.user.email='store@example.test'
customer=env['res.partner'].create({'name':'Quotation Customer','email':'quotation-customer@example.test'})
product=env['product.product'].create({'name':'Fixture consulting','type':'service','list_price':125.0})
order=env['sale.order'].create({'partner_id':customer.id,'order_line':[(0,0,{'product_id':product.id,'product_uom_qty':2,'price_unit':125.0})]})
assert order.amount_total >= 250.0
# Native report generation and template rendering must run, not mocked PDF bytes.
template=env.ref('sale.email_template_edi_sale')
assert template.report_template_ids
env.cr.commit()  # Asset/report server sees the same synthetic company and order.
class Response:
 status_code=202
 def json(self):return {'request_id':'quotation-fixture'}
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=Response()) as post,patch('smtplib.SMTP',side_effect=AssertionError('SMTP fallback')):
 mail_id=template.send_mail(order.id,force_send=False,email_values={'mail_server_id':server.id,'auto_delete':False})
 mail=env['mail.mail'].browse(mail_id)
 assert mail and mail.state=='outgoing'
 assert mail.model=='sale.order' and mail.res_id==order.id
 pdfs=mail.attachment_ids.filtered(lambda a:a.mimetype=='application/pdf')
 assert len(pdfs)==1, 'Expected generated quotation PDF'
 raw=pdfs.raw
 if isinstance(raw,bytes):pdf=raw  # Odoo19
 else:
  with raw.open() as stream:pdf=stream.read()  # Odoo20 BinaryValue
 assert pdf.startswith(b'%PDF-') and len(pdf)>1000
 post.assert_not_called()
 print('PASS_BUSINESS: native quotation template renders real PDF into outgoing queue')
 mail.send(raise_exception=True)
 assert mail.state=='sent' and post.call_count==1
 payload=post.call_args.kwargs['json']
 recipients=[x['email'] for p in payload['personalizations'] for k in ('to','cc','bcc') for x in p.get(k,[])]
 assert recipients==['quotation-customer@example.test']
 assert order.name in payload['subject']
 assert any(order.name in c['value'] for c in payload['content'])
 attachments=payload['attachments']
 assert len(attachments)==1 and base64.b64decode(attachments[0]['content'])==pdf
 assert attachments[0]['filename']==pdfs.name
 print('PASS_BUSINESS: native quotation queue submits intended recipient and byte-identical PDF via API')
 mail.send(raise_exception=True)
 assert post.call_count==1
 print('PASS_BUSINESS: accepted quotation replay makes no second provider request')
print('ODOO_BUSINESS_COMPLETE 3 checks; no live provider requests')
