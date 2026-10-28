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
env.cr.rollback()  # End any snapshot opened by native postcommit hooks.
env.invalidate_all()
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
# The native invoice "Sent" flag also means PDF generated, not email delivery.
# Verify queue/notification/receipt failure state and the real Retry action.
import requests
for outcome, expected in [('reject', 'rejected'), ('timeout', 'unknown')]:
 failed_invoice=invoice.copy({'invoice_date':fields.Date.today()})
 failed_invoice.action_post()
 env.cr.commit()
 env.cr.rollback()  # New request boundary after account customer-rank postcommit write.
 env.invalidate_all()  # Fresh request-like cache after postcommit notification hooks.
 failure_wizard=env['account.move.send.wizard'].with_context(active_model='account.move',active_ids=failed_invoice.ids).create({'move_id':failed_invoice.id,'sending_methods':['email'],'template_id':env.ref('account.email_template_edi_invoice').id})
 response=Response();response.status_code=400
 failure=requests.Timeout('private fixture diagnostic') if outcome=='timeout' else None
 with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=response,side_effect=failure) as post,patch('smtplib.SMTP',side_effect=AssertionError('SMTP fallback')):
  failure_wizard.action_send_and_print()
  mails=env['mail.mail'].search([('model','=','account.move'),('res_id','=',failed_invoice.id)])
  outgoing=mails.filtered(lambda m:m.state=='outgoing')
  if outgoing:outgoing.send()
  assert len(mails)==1 and mails.state=='exception'
  assert post.call_count==1
  assert 'private fixture diagnostic' not in (mails.failure_reason or '')
  notices=mails.mail_message_id.notification_ids.filtered(lambda n:n.res_partner_id==customer)
  assert notices and all(n.notification_status=='exception' for n in notices)
  with env.registry.cursor() as cr:
   receipts=env(cr=cr)['mailchannels.operation'].search([('message_id','=',mails.message_id)])
   assert len(receipts)==1 and receipts.state==expected
  assert failed_invoice.is_move_sent, 'Native flag records PDF generation, not email delivery'
  mails.action_retry()
  assert mails.state=='outgoing'
  mails.send()
  assert mails.state=='exception' and post.call_count==1
  failed_mail_id=mails.id
  env.cr.commit()
  env.cr.rollback()
  env.invalidate_all()
  with env.registry.cursor() as cr:
   persisted=env(cr=cr)['mail.mail'].browse(failed_mail_id)
   assert persisted.exists() and persisted.state=='exception'
   notifications=persisted.mail_message_id.notification_ids.filtered(lambda n:n.res_partner_id.id==customer.id)
   assert notifications and all(n.notification_status=='exception' for n in notifications)
  assert post.call_count==1, 'Postcommit must not resubmit failed invoice mail'
  print('PASS_BUSINESS: invoice '+outcome+' persists failed notification and '+expected+' receipt; native Retry/postcommit make no new request')
print('ODOO_BUSINESS_COMPLETE 7 checks; no live provider requests')

# Synthetic provider IDs and preserved outer headers are fixture assumptions.
import hashlib
import json
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from odoo import release
from odoo.tools import html2plaintext

def evidence(case, **values):
 print('INBOUND_EVIDENCE '+json.dumps(
  {'case':case,'utc':datetime.now(timezone.utc).isoformat(),**values},default=str,sort_keys=True))

def boundary():
 env.cr.commit()  # Run native postcommit callbacks under the transport interceptors.
 env.cr.rollback()
 env.invalidate_all()

incoming_invoice=invoice.copy({'invoice_date':fields.Date.today()})
incoming_invoice.action_post()
assert incoming_invoice.state=='posted' and incoming_invoice.partner_id==customer
assert incoming_invoice.amount_total==250.0
native_template=env.ref('account.email_template_edi_invoice')
incoming_template=native_template.copy({
 'name':'Retained inbound fixture','auto_delete':False,'mail_server_id':server.id})
assert incoming_template!=native_template and not incoming_template.auto_delete
wrong_partner=env['res.partner'].create({
 'name':'Unrelated DSN fixture','email':'unrelated-dsn@example.test'})
Users=env['res.users'].with_context(no_reset_password=True)
groups_field='group_ids' if 'group_ids' in Users._fields else 'groups_id'
inbox_user=Users.create({
 'name':'Inbound inbox fixture','login':'inbound-inbox@example.test',
 'email':'inbound-inbox@example.test','notification_type':'inbox',
 groups_field:[(6,0,[env.ref('base.group_user').id,env.ref('base.group_system').id])]})
assert inbox_user.active and inbox_user.has_group('base.group_system')
assert inbox_user.notification_type=='inbox'
boundary()
incoming_wizard=env['account.move.send.wizard'].with_context(
 active_model='account.move',active_ids=incoming_invoice.ids,mail_notify_force_send=False,
).create({
 'move_id':incoming_invoice.id,'sending_methods':['email'],'template_id':incoming_template.id})
assert incoming_wizard.template_id==incoming_template and incoming_wizard.mail_partner_ids==customer

class IncomingResponse(Response):
 def json(self):return {'request_id':'inbound-acceptance-fixture'}

completed_cases=[]
with (
 patch.object(type(Server),'_disable_send',return_value=False),
 patch('requests.post',return_value=IncomingResponse()) as inbound_post,
 patch('smtplib.SMTP',side_effect=AssertionError('Inbound SMTP fallback')) as smtp,
 patch('smtplib.SMTP_SSL',side_effect=AssertionError('Inbound SMTP_SSL fallback')) as smtp_ssl,
):
 incoming_wizard.action_send_and_print()
 original_mail=env['mail.mail'].search([
  ('model','=','account.move'),('res_id','=',incoming_invoice.id)])
 assert len(original_mail)==1 and original_mail.state=='outgoing'
 assert original_mail.mail_server_id==server
 original=original_mail.mail_message_id
 assert original.model=='account.move' and original.res_id==incoming_invoice.id
 assert original.message_id==original_mail.message_id
 target=original.notification_ids.filtered(lambda n:n.res_partner_id==customer)
 assert len(target)==1 and target.notification_type=='email'
 assert target.mail_mail_id==original_mail and target.mail_message_id==original
 assert target.notification_status=='ready'
 inbound_post.assert_not_called()
 evidence('F0_queue',
  queue=original_mail.read(['id','state','mail_message_id','message_id']),
  notification=target.read(['id','notification_type','notification_status',
   'res_partner_id','mail_message_id','mail_mail_id']))
 original_mail.send(raise_exception=True)
 boundary()
 assert original_mail.exists() and original_mail.state=='sent'
 assert target.notification_status=='sent'
 evidence('F0_sent',notification=target.read(['id','notification_status','failure_type']),
  base_version=env['ir.module.module'].search([('name','=','base')]).installed_version)
 assert target.failure_type is False
 assert inbound_post.call_count==1
 accepted_payload=inbound_post.call_args.kwargs['json']
 references=accepted_payload['headers']['References']
 assert original.message_id in references.split()
 assert not any(k.lower()=='message-id' for k in accepted_payload['headers'])
 assert [r['email'] for p in accepted_payload['personalizations']
  for k in ('to','cc','bcc') for r in p.get(k,[])]==[customer.email_normalized]
 assert incoming_invoice.name in accepted_payload['subject']
 assert accepted_payload['from']['email']=='store@example.test'
 reply_address=accepted_payload['reply_to']['email']
 envelope_address=accepted_payload['envelope_from']['email']
 assert reply_address and envelope_address
 original_ids=[original.id,mail.mail_message_id.id]
 original_message_ids=[original.message_id,mail.message_id]
 receipt_fields=['id','operation_key','payload_hash','message_id','server_reference',
  'state','http_status','request_id','create_uid','create_date','write_uid','write_date']

 def snapshot():
  with env.registry.cursor() as cr:
   fresh=env(cr=cr)
   messages=fresh['mail.message'].search([
    '|','&',('model','=','account.move'),('res_id','=',incoming_invoice.id),
    '&',('model','=','sale.order'),('res_id','=',order.id)],order='id')
   return {
    'invoice':fresh['account.move'].browse(incoming_invoice.id).read([
     'id','name','state','partner_id','currency_id','amount_total','amount_untaxed',
     'amount_residual','is_move_sent']),
    'quotation':fresh['sale.order'].browse(order.id).read([
     'id','name','state','partner_id','currency_id','amount_total','amount_untaxed']),
    'messages':messages.read(['id','message_id','model','res_id','parent_id','author_id',
     'body','attachment_ids','partner_ids','message_type']),
    'notifications':fresh['mail.notification'].search([
     ('mail_message_id','in',messages.ids)],order='id').read([
      'id','mail_message_id','res_partner_id','author_id','notification_type',
      'notification_status','failure_type','failure_reason','mail_mail_id','mail_email_address']),
    'queue':fresh['mail.mail'].search([],order='id').read([
     'id','state','mail_message_id','message_id']),
    'receipts':fresh['mailchannels.operation'].search([
     ('message_id','in',original_message_ids)],order='id').read(receipt_fields),
    'counters':fresh['res.partner'].browse([customer.id,wrong_partner.id]).read([
     'id','email_normalized','message_bounce']),
   }

 accepted=snapshot()
 receipt=[r for r in accepted['receipts'] if r['message_id']==original.message_id]
 assert len(receipt)==1 and receipt[0]['state']=='accepted'
 assert receipt[0]['http_status']==202 and receipt[0]['request_id']=='inbound-acceptance-fixture'
 assert receipt[0]['server_reference']==server.id
 payload_hash=hashlib.sha256(json.dumps(
  accepted_payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 assert receipt[0]['payload_hash']==payload_hash
 assert receipt[0]['operation_key']==hashlib.sha256(json.dumps(
  [server.id,original.message_id,customer.email_normalized],
  separators=(',',':')).encode()).hexdigest()
 evidence('F0',payload=accepted_payload,payload_sha256=payload_hash,
  template_id=incoming_template.id,native_template_id=native_template.id,before=accepted)
 original_mail.send(raise_exception=True)
 boundary()
 assert snapshot()==accepted and inbound_post.call_count==1
 completed_cases.append('F0')
 print('PASS_INBOUND: F0 native retained invoice queue and API acceptance identity')

 for record in (incoming_invoice,order):
  record.message_unsubscribe(partner_ids=record.message_partner_ids.ids)
  record.message_subscribe(partner_ids=[inbox_user.partner_id.id,customer.id])
  assert set(record.message_partner_ids.ids)=={inbox_user.partner_id.id,customer.id}
  follower=record.message_follower_ids.filtered(lambda f:f.partner_id==inbox_user.partner_id)
  assert len(follower)==1 and env.ref('mail.mt_comment') in follower.subtype_ids
 boundary()
 fixed=snapshot()
 unroutable='no-inbound-route@unroutable.invalid'
 assert not env['mail.alias.domain']._find_aliases([unroutable])
 assert not env['mail.alias'].search([('alias_name','=','no-inbound-route')])
 assert not env['mail.alias.domain'].search([('name','=','unroutable.invalid')])
 provider_id='<synthetic-provider-unknown@example.test>'
 assert not env['mail.message'].search([('message_id','=',provider_id)])

 def reply(case, address, refs=None, parent=None, attachment=False):
  message=EmailMessage(policy=policy.SMTP)
  message['From']=customer.email_normalized
  message['To']=address
  message['Message-ID']='<inbound-'+case.lower()+'@example.test>'
  message['Subject']='Re: '+incoming_invoice.name
  if refs is not None:message['References']=refs
  if parent is not None:message['In-Reply-To']=parent
  message.set_content('Native '+case+' reply — café',charset='utf-8')
  if attachment:
   message.add_attachment(b'R1 attachment\x00\xff',maintype='application',
    subtype='octet-stream',filename='native-r1.bin')
  return message.as_bytes()

 def parse(raw):
  return env['mail.thread'].message_parse(message_from_bytes(raw,policy=policy.SMTP))

 def process(case,raw):
  before=snapshot()
  parsed=parse(raw)
  evidence(case+'_input',rfc_base64=base64.b64encode(raw).decode(),
   rfc_sha256=hashlib.sha256(raw).hexdigest(),parsed=parsed,before=before)
  with env.registry.cursor() as gateway_cr:
   result=env(cr=gateway_cr)['mail.thread'].message_process(None,raw)
   gateway_cr.commit()
  boundary()
  after=snapshot()
  assert after['invoice']==fixed['invoice'] and after['quotation']==fixed['quotation']
  assert after['queue']==fixed['queue'] and after['receipts']==fixed['receipts']
  assert ([m for m in after['messages'] if m['id'] in original_ids]
   ==[m for m in fixed['messages'] if m['id'] in original_ids])
  assert inbound_post.call_count==1
  smtp.assert_not_called();smtp_ssl.assert_not_called()
  evidence(case+'_outcome',result=result,after=after)
  return parsed,result,before,after

 def check_reply(case,raw,record,parent):
  parsed,result,before,after=process(case,raw)
  assert parsed['parent_id']==parent.id
  if release.version_info[0]==19:
   assert result==record.id
  else:
   assert result._name==record._name and result.ids==record.ids
  message=env['mail.message'].search([('message_id','=',parsed['message_id'])])
  assert len(message)==1 and message.model==record._name and message.res_id==record.id
  assert message.parent_id==parent and message.author_id==customer
  assert 'Native '+case+' reply — café' in html2plaintext(message.body)
  notice=message.notification_ids
  assert len(notice)==1 and notice.res_partner_id==inbox_user.partner_id
  assert notice.notification_type=='inbox' and notice.notification_status=='sent'
  assert notice.author_id==customer and notice.mail_message_id==message
  assert not notice.mail_mail_id
  assert after['counters']==before['counters']
  assert ([n for n in after['notifications'] if n['mail_message_id'][0] in original_ids]
   ==[n for n in before['notifications'] if n['mail_message_id'][0] in original_ids])
  assert len(after['messages'])==len(before['messages'])+1
  assert len(after['notifications'])==len(before['notifications'])+1
  if case=='R1':
   attachment=message.attachment_ids
   assert len(attachment)==1 and attachment.name=='native-r1.bin'
   raw_attachment=attachment.raw
   if not isinstance(raw_attachment,bytes):
    with raw_attachment.open() as stream:raw_attachment=stream.read()
   assert raw_attachment==b'R1 attachment\x00\xff'
   evidence('R1_attachment',id=attachment.id,name=attachment.name,
    content_base64=base64.b64encode(raw_attachment).decode())
  if case=='R4':
   assert ([m for m in before['messages'] if m['model']=='account.move']
    ==[m for m in after['messages'] if m['model']=='account.move'])
   invoice_message_ids=[m['id'] for m in before['messages'] if m['model']=='account.move']
   assert (
    [n for n in before['notifications'] if n['mail_message_id'][0] in invoice_message_ids]
    ==[n for n in after['notifications'] if n['mail_message_id'][0] in invoice_message_ids])
  completed_cases.append(case)
  print('PASS_INBOUND: '+case+' exact native route, author and sent inbox notification')
  return message

 r1=reply('R1',reply_address,references,provider_id,True)
 check_reply('R1',r1,incoming_invoice,original)
 check_reply('R2',reply('R2',reply_address,parent=original.message_id),incoming_invoice,original)
 parsed,result,before,after=process('R3',r1)
 assert result is False and before==after
 completed_cases.append('R3')
 print('PASS_INBOUND: R3 committed duplicate reply preserves all identities')
 check_reply('R4',reply('R4',unroutable,mail.message_id),order,mail.mail_message_id)
 r5=reply('R5',unroutable,provider_id,provider_id)
 before=snapshot();parsed=parse(r5)
 assert not parsed.get('parent_id')
 evidence('R5_input',rfc_base64=base64.b64encode(r5).decode(),
  rfc_sha256=hashlib.sha256(r5).hexdigest(),parsed=parsed,before=before)
 try:
  with env.registry.cursor() as gateway_cr:
   env(cr=gateway_cr)['mail.thread'].message_process(None,r5)
   gateway_cr.commit()
 except ValueError as error:
  assert 'No possible route' in str(error)
  evidence('R5_refusal',error=str(error))
 else:raise AssertionError('Unmatched references must have no native route')
 boundary()
 assert snapshot()==before
 assert inbound_post.call_count==1
 smtp.assert_not_called();smtp_ssl.assert_not_called()
 evidence('R5_outcome',after=snapshot())
 completed_cases.append('R5')
 print('PASS_INBOUND: R5 unmatched references refuse without route or mutation')

 def dsn(case,recipient,outer_refs=None):
  message=EmailMessage(policy=policy.SMTP)
  message['From']='MAILER-DAEMON@example.test'
  message['To']=envelope_address
  message['Delivered-To']=envelope_address
  message['Message-ID']='<inbound-'+case.lower()+'@example.test>'
  message['Subject']='Fixture delivery failure'
  if outer_refs is not None:message['References']=outer_refs
  message.set_type('multipart/report');message.set_param('report-type','delivery-status')
  explanation=EmailMessage(policy=policy.SMTP)
  explanation.set_content('Fixture delivery failed: mailbox unavailable.',charset='utf-8')
  status=EmailMessage(policy=policy.SMTP);status.set_type('message/delivery-status')
  reporting=EmailMessage(policy=policy.SMTP)
  reporting['Reporting-MTA']='dns; synthetic-provider.example.test'
  failure=EmailMessage(policy=policy.SMTP)
  for name,value in [
   ('Final-Recipient','rfc822; '+recipient),('Action','failed'),('Status','5.1.1'),
   ('Diagnostic-Code','smtp; 550 Fixture mailbox unavailable'),
  ]:failure[name]=value
  status.set_payload([reporting,failure])
  enclosed=EmailMessage(policy=policy.SMTP)
  enclosed['Message-ID']=provider_id;enclosed['References']=references
  enclosed['From']=accepted_payload['from']['email'];enclosed['To']=customer.email_normalized
  enclosed['Reply-To']=reply_address;enclosed['Subject']=accepted_payload['subject']
  enclosed.set_content('Synthetic enclosed original')
  original_part=EmailMessage(policy=policy.SMTP)
  original_part.set_type('message/rfc822');original_part.set_payload([enclosed])
  message.attach(explanation);message.attach(status);message.attach(original_part)
  return message.as_bytes()

 for case,partner,outer in [
  ('D1',customer,None),('D2',wrong_partner,references),
  ('D3',customer,references),('D4',customer,references),
 ]:
  dsn_bytes=positive_dsn if case=='D4' else dsn(case,partner.email_normalized,outer)
  parsed,result,before,after=process(case,dsn_bytes)
  assert parsed['is_bounce'] and parsed['bounced_email']==partner.email_normalized
  assert parsed['bounced_partner']==partner
  if release.version_info[0]==19:
   assert result is False
  else:
   assert result._name=='mail.thread' and result.ids==[]
  assert after['messages']==before['messages'] and after['queue']==before['queue']
  assert not env['mail.message'].search([('message_id','=',parsed['message_id'])])
  for old,new in zip(before['counters'],after['counters']):
   assert old['id']==new['id']
   assert new['message_bounce']==old['message_bounce']+(old['id']==partner.id)
  if case=='D1':
   assert not parsed['bounced_message'] and not parsed.get('parent_id')
  else:
   assert parsed['bounced_message']==original and parsed['parent_id']==original.id
  if case in ('D1','D2'):
   assert target.notification_status=='sent' and after['notifications']==before['notifications']
  else:
   assert target.notification_status=='bounce' and target.failure_type=='mail_bounce'
   assert target.failure_reason==html2plaintext(parsed['body'])
   assert 'Fixture delivery failed: mailbox unavailable.' in target.failure_reason
   assert ([n for n in after['notifications'] if n['id']!=target.id]
    ==[n for n in before['notifications'] if n['id']!=target.id])
   if case=='D4':assert after['notifications']==before['notifications']
   positive_dsn=dsn_bytes
  assert original_mail.state=='sent'
  completed_cases.append(case)
  print('PASS_INBOUND: '+case+' native DSN match/notification/counter semantics')
 boundary()
 smtp.assert_not_called();smtp_ssl.assert_not_called()
 assert inbound_post.call_count==1
 incoming_template.unlink()  # Do not retain a copied template dependency for lifecycle tests.
 boundary()
 evidence('complete',completed_cases=completed_cases)
 print('ODOO_INBOUND_COMPLETE '+str(len(completed_cases))
  +' cases; synthetic native incoming qualification; no live provider requests')
