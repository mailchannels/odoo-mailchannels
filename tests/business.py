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
# Posted invoice through the native send wizard, including report and chatter.
Account=env['account.account']
def account(code,name,kind):
 values={'code':code,'name':name,'account_type':kind}
 if 'company_ids' in Account._fields:values['company_ids']=[(6,0,[env.company.id])]
 else:values['company_id']=env.company.id
 if kind=='asset_receivable':values['reconcile']=True
 return Account.create(values)
receivable=account('MC1100','Fixture receivable','asset_receivable')
income=account('MC4000','Fixture revenue','income')
customer.property_account_receivable_id=receivable
journal=env['account.journal'].create({'name':'Fixture invoices','code':'MCINV','type':'sale','company_id':env.company.id,'default_account_id':income.id})
from odoo import fields
invoice=env['account.move'].create({'move_type':'out_invoice','partner_id':customer.id,'journal_id':journal.id,'invoice_date':fields.Date.today(),'invoice_line_ids':[(0,0,{'name':'Fixture consulting invoice','quantity':2,'price_unit':125.0,'account_id':income.id})]})
invoice.action_post()
assert invoice.state=='posted' and invoice.amount_total==250.0
# This is a synthetic company, not a claim of fiscal/localization coverage.
env.cr.commit()
wizard=env['account.move.send.wizard'].with_context(active_model='account.move',active_ids=invoice.ids).create({'move_id':invoice.id,'sending_methods':['email'],'template_id':env.ref('account.email_template_edi_invoice').id})
assert wizard.mail_partner_ids==customer
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=Response()) as post,patch('smtplib.SMTP',side_effect=AssertionError('SMTP fallback')):
 wizard.action_send_and_print()
 assert invoice.is_move_sent
 # Some native paths enqueue for the cron rather than immediately dispatching.
 queued=env['mail.mail'].search([('model','=','account.move'),('res_id','=',invoice.id),('state','=','outgoing')])
 if queued:queued.send(raise_exception=True)
 assert post.call_count==1, 'Invoice must generate exactly one provider request'
 payload=post.call_args.kwargs['json']
 recipients=[x['email'] for p in payload['personalizations'] for k in ('to','cc','bcc') for x in p.get(k,[])]
 assert recipients==['quotation-customer@example.test']
 assert invoice.name in payload['subject']
 pdfs=invoice.message_ids.attachment_ids.filtered(lambda a:a.mimetype=='application/pdf')
 assert len(pdfs)==1
 raw=pdfs.raw
 if isinstance(raw,bytes):pdf=raw
 else:
  with raw.open() as stream:pdf=stream.read()
 assert pdf.startswith(b'%PDF-') and len(pdf)>1000
 attachments=payload['attachments']
 assert len(attachments)==1 and base64.b64decode(attachments[0]['content'])==pdf
 assert attachments[0]['filename']==pdfs.name
 print('PASS_BUSINESS: posted invoice send wizard preserves customer and native PDF through API')
 notices=invoice.message_ids.filtered(lambda m:customer in m.partner_ids and m.message_type=='comment')
 assert notices and any(pdfs in m.attachment_ids for m in notices)
 print('PASS_BUSINESS: native invoice chatter retains intended customer and generated document')
print('ODOO_BUSINESS_COMPLETE 5 checks; no live provider requests')
