import os
import uuid
from email.message import EmailMessage
from unittest.mock import patch
import requests
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.addons.mail_mailchannels.mime import convert, InvalidMessage

Server=env['ir.mail_server']
server=Server.create({'name':'Fixture API','mc_enabled':True,'from_filter':'example.test'})
env.cr.commit()
assert os.environ['MAILCHANNELS_ODOO_API_KEY']=='fixture-api-key'
checks=[]
def check(name):
 checks.append(name)
 print('PASS: '+name)
def message():
 m=EmailMessage();m['From']='Store <store@example.test>';m['To']='buyer@example.test';m['Message-ID']='<'+uuid.uuid4().hex+'@example.test>';m['Subject']='Invoice ✓';m['Reply-To']='catchall@example.test';m.set_content('Body');return m
class Response:
 status_code=202
 def json(self):return {'request_id':'fixture-request'}

with patch.object(type(Server),'_disable_send',return_value=False), patch('requests.post',return_value=Response()) as post:
 m=message();m['Cc']='accounts@example.test';m['Bcc']='hidden@example.test';m['Return-Path']='bounce@example.test'
 m.add_alternative('<p>Body</p>',subtype='html');m.add_attachment(b'PDF fixture',maintype='application',subtype='pdf',filename='invoice.pdf')
 original=m['Message-ID']
 assert Server.send_email(m,mail_server_id=server.id)==original
 payload=post.call_args.kwargs['json'];assert payload['envelope_from']['email']=='bounce@example.test'
 assert payload['personalizations'][0]['bcc']==[{'email':'hidden@example.test'}]
 assert payload['personalizations'][0]['cc'][0]['email']=='accounts@example.test'
 assert original in payload['headers']['References'] and 'Message-ID' not in payload['headers']
 assert payload['attachments'][0]['filename']=='invoice.pdf' and len(payload['content'])==2
 assert post.call_args.kwargs['allow_redirects'] is False and post.call_args.kwargs['verify'] is True
 check('native send preserves ID, references, envelope, CC/BCC, HTML and PDF')
 # Real queue opens and closes our API session; no SMTP socket may be opened.
 mail=env['mail.mail'].create({'subject':'Queued','body_html':'<p>Queue</p>','email_from':'store@example.test','email_to':'buyer@example.test','mail_server_id':server.id,'auto_delete':False})
 with patch('smtplib.SMTP',side_effect=AssertionError('SMTP must not be used')):
  mail.send(raise_exception=True)
 assert mail.state=='sent' and post.call_count==2
 check('real mail.mail queue uses API session, no SMTP')
 # A second attempt of the same message/recipient set must use the stored receipt.
 mail.send(raise_exception=True)
 assert post.call_count==2
 check('accepted mail replay is deduplicated')
 m=message();first_id=m['Message-ID'];Server.send_email(m,mail_server_id=server.id)
 count=post.call_count;env.cr.rollback()
 # Restore a fresh MIME instance with the same identity after transaction rollback.
 m2=message();m2.replace_header('Message-ID',first_id)
 Server.send_email(m2,mail_server_id=server.id)
 assert post.call_count==count
 check('committed submission receipt survives caller rollback')

with patch.object(type(Server),'_disable_send',return_value=False), patch('requests.post',side_effect=requests.Timeout('fixture private detail')) as post:
 m=message()
 for attempt in range(2):
  try:Server.send_email(m,mail_server_id=server.id)
  except MailDeliveryException as exc:assert 'private detail' not in str(exc) and 'fixture-api-key' not in str(exc)
  else:raise AssertionError('Timeout must not report success')
 assert post.call_count==1
 check('unknown timeout is not resent and exception is sanitized')

with patch.object(type(Server),'_disable_send',return_value=True), patch('requests.post') as post:
 m=message();assert Server.send_email(m,mail_server_id=server.id)==m['Message-ID'];post.assert_not_called()
 check('native no-send guard is preserved')

for status,expected in [(400,'rejected'),(429,'rejected'),(503,'unknown'),(302,'unknown')]:
 response=Response();response.status_code=status
 with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=response) as post:
  m=message()
  for attempt in range(2):
   try:Server.send_email(m,mail_server_id=server.id)
   except MailDeliveryException:pass
   else:raise AssertionError('Failure returned success')
  assert post.call_count==1
  with env.registry.cursor() as cr:
   receipt=env(cr=cr)['mailchannels.operation'].search([('message_id','=',m['Message-ID'])]);assert receipt.state==expected
 check('HTTP %s stored as %s without retry' % (status,expected))

with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post') as post:
 m=message()
 session=Server._connect__(mail_server_id=server.id,smtp_from='store@example.test')
 try:Server.with_context(send_smtp_skip_to=['buyer@example.test']).send_email(m,mail_server_id=server.id,smtp_session=session)
 except AssertionError:pass
 else:raise AssertionError('Blocked recipient accepted')
 post.assert_not_called()
 check('Odoo recipient block list remains effective')

m=message();m.replace_header('To','virtual@example.test')
try:convert(m,'store@example.test',['actual@example.test'])
except InvalidMessage:pass
else:raise AssertionError('Virtual recipient must not be sent')
check('unsupported virtual-To-only envelope fails before sending')

public=env.ref('base.public_user')
try:env['mailchannels.operation'].with_user(public).search_read([],['request_id'])
except Exception as exc:
 from odoo.exceptions import AccessError
 assert isinstance(exc,AccessError)
else:raise AssertionError('Public access to receipts')
check('receipt ACL denies public users')


# Reuse of any previously accepted recipient blocks a partial overlap, even if
# another recipient is new. No subset of a changed message is silently resent.
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=Response()) as post:
 m=message();Server.send_email(m,mail_server_id=server.id)
 m2=message();m2.replace_header('Message-ID',m['Message-ID']);m2['Cc']='second@example.test'
 try:Server.send_email(m2,mail_server_id=server.id)
 except MailDeliveryException:pass
 else:raise AssertionError('Partial overlap must require review')
 assert post.call_count==1
 check('per-recipient receipts prevent changed-envelope overlap resend')

# Administrator-only endpoint override: default production, HTTPS *.mailchannels.net only.
from odoo.exceptions import UserError
Param=env['ir.config_parameter'].sudo()
set_endpoint=lambda v:Param.set_str('mail_mailchannels.api_endpoint',v) if hasattr(Param,'set_str') else Param.set_param('mail_mailchannels.api_endpoint',v)
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=Response()) as post:
 Server.send_email(message(),mail_server_id=server.id)
 assert post.call_args.args[0]=='https://api.mailchannels.net/tx/v1/send'
 set_endpoint('https://alb-test.dev.mailchannels.net/tx/v1/send')
 Server.send_email(message(),mail_server_id=server.id)
 assert post.call_args.args[0]=='https://alb-test.dev.mailchannels.net/tx/v1/send' and post.call_count==2
 receipts=env['mailchannels.operation'].sudo().search_count([])
 for bad in ('http://alb-test.dev.mailchannels.net/tx/v1/send','https://example.test/tx/v1/send',
             'https://evilmailchannels.net/tx/v1/send','https://user@api.mailchannels.net/tx/v1/send',
             'https://api.mailchannels.net:8443/tx/v1/send','https://api.mailchannels.net/tx/v1/send?x=1',
             'https://api.mailchannels.net/tx/v1','https://api.mailchannels.net:bad/tx/v1/send',
             'https://api.mailchannels.net:443/tx/v1/send','https://api.mailchannels.net:/tx/v1/send'):
  set_endpoint(bad)
  try:Server.send_email(message(),mail_server_id=server.id)
  except UserError:pass
  else:raise AssertionError('Endpoint override must be refused: '+bad)
 assert post.call_count==2 and env['mailchannels.operation'].sudo().search_count([])==receipts
 set_endpoint(False)
 Server.send_email(message(),mail_server_id=server.id)
 assert post.call_args.args[0]=='https://api.mailchannels.net/tx/v1/send'
 check('endpoint override is HTTPS mailchannels.net only, refused before receipts, default production')
from odoo.exceptions import AccessError
try:env['ir.config_parameter'].with_user(env.ref('base.public_user')).search([('key','=','mail_mailchannels.api_endpoint')])
except AccessError:check('endpoint override parameter is not readable by non-administrators')
else:raise AssertionError('Non-administrators must not read the endpoint parameter')

response=Response();response.status_code=200
with patch('requests.post',return_value=response) as post:
 server.test_smtp_connection()
 assert post.call_args.kwargs['params']=={'dry-run':'true'}
 check('configuration validation uses dry-run, not queue delivery')
env.user.email='validator@example.test'
refused=Response();refused.status_code=403
refused.json=lambda:{'errors':['Can only send to verified email addresses. Unverified recipients: x@example.test']}
with patch('requests.post',return_value=refused) as post:
 try:server.test_smtp_connection()
 except UserError as e:assert 'HTTP 403' in str(e) and 'verified email addresses' in str(e),str(e)
 else:raise AssertionError('A refused dry-run must raise')
 assert [p['email'] for p in post.call_args.kwargs['json']['personalizations'][0]['to']]==['validator@example.test']
 check('dry-run goes to the signed-in user and explains API refusals')

with patch('requests.post') as post,patch.dict(os.environ,{'MAILCHANNELS_ODOO_API_KEY':''}):
 with patch.object(type(Server),'_disable_send',return_value=False):
  try:Server.send_email(message(),mail_server_id=server.id)
  except Exception as exc:
   from odoo.exceptions import UserError
   assert isinstance(exc,UserError)
  else:raise AssertionError('Missing credential accepted')
 post.assert_not_called()
 check('missing server key fails before any API call')

# Simulate a worker crash after durable reservation, before response handling.
class WorkerCrash(BaseException):pass
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',side_effect=WorkerCrash()):
 m=message()
 try:Server.send_email(m,mail_server_id=server.id)
 except WorkerCrash:pass
 else:raise AssertionError('Crash simulation not triggered')
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post') as post:
 try:Server.send_email(m,mail_server_id=server.id)
 except MailDeliveryException:pass
 else:raise AssertionError('Crash outcome was resent')
 post.assert_not_called()
 check('worker failure after reservation cannot trigger a second submission')

from concurrent.futures import ThreadPoolExecutor
import threading
entered=threading.Event();release=threading.Event()
m=message();payload=convert(m,'store@example.test',['buyer@example.test'])
def slow_response(*args,**kwargs):
 entered.set()
 if not release.wait(15):raise AssertionError('Concurrency fixture timed out')
 return Response()
def submit_worker():
 with env.registry.cursor() as cr:
  env(cr=cr)['ir.mail_server'].browse(server.id)._mc_submit(payload,m['Message-ID'])
with patch('requests.post',side_effect=slow_response) as post,ThreadPoolExecutor(max_workers=2) as pool:
 first=pool.submit(submit_worker)
 try:
  assert entered.wait(15)
  second=pool.submit(submit_worker)
  try:second.result(timeout=15)
  except MailDeliveryException:pass
  else:raise AssertionError('Concurrent worker was allowed to resubmit')
 finally:release.set()
 first.result(timeout=15)
 assert post.call_count==1
 check('concurrent workers issue one API call')

# Exercise the real auth_signup business flow, including template rendering and
# native default-server selection. Never print reset URLs or transient tokens.
from html import unescape
from urllib.parse import urlparse, parse_qs
import re
env.company.email='store@example.test'
user=env['res.users'].with_context(no_reset_password=True).create({
 'name':'Reset Fixture', 'login':'reset-fixture@example.test',
 'email':'reset-fixture@example.test', 'company_id':env.company.id,
 'company_ids':[(6,0,[env.company.id])]})
with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post',return_value=Response()) as post,patch('smtplib.SMTP',side_effect=AssertionError('SMTP fallback')):
 user.action_reset_password()
 assert post.call_count==1, 'Password reset must make exactly one API call'
 payload=post.call_args.kwargs['json']
 assert payload['subject']=='Password reset'
 recipients=[x['email'] for p in payload['personalizations'] for k in ('to','cc','bcc') for x in p.get(k,[])]
 assert recipients==['reset-fixture@example.test'], 'Reset email must target only the account owner'
 html=next(c['value'] for c in payload['content'] if c['type']=='text/html')
 links=[unescape(x) for x in re.findall(r'href=["\']([^"\']+)',html)]
 reset_links=[x for x in links if '/web/reset_password' in x]
 assert reset_links, 'Rendered reset link missing'
 token=parse_qs(urlparse(reset_links[0]).query).get('token',[''])[0]
 assert token, 'Reset token missing'
 partner=env['res.partner']._signup_retrieve_partner(token,check_validity=True,raise_exception=True)
 assert partner==user.partner_id, 'Reset token not bound to intended user'
 with env.registry.cursor() as cr:
  receipt=env(cr=cr)['mailchannels.operation'].search([('request_id','=','fixture-request')])
  assert receipt and not any(token in str(row.read()[0]) for row in receipt), 'Reset token leaked into receipts'
 check('native password-reset template and valid owner-bound link use API without SMTP')

# ORM access/export checks use real users, not the superuser fixture identity.
from odoo.exceptions import AccessError, UserError, ValidationError
Users=env['res.users'].with_context(no_reset_password=True)
groups_field='group_ids' if 'group_ids' in Users._fields else 'groups_id'
def access_user(login,group,company):
 return Users.create({'name':login,'login':login+'@example.test','email':login+'@example.test',
  'company_id':company.id,'company_ids':[(6,0,[company.id])],
  groups_field:[(6,0,[env.ref(group).id,env.ref('base.group_allow_export').id])]})

def denied(fn):
 try:
  with env.cr.savepoint():fn()
 except AccessError:return
 raise AssertionError('Expected native access denial')

receipts=env['mailchannels.operation']
rows=receipts.search([],order='id')
assert rows
receipt_fields=['operation_key','payload_hash','message_id','server_reference','state',
 'http_status','request_id','create_uid','create_date','write_uid','write_date']
config_fields=['name','active','sequence','from_filter','owner_user_id','smtp_host','smtp_port',
 'smtp_user','smtp_pass','smtp_encryption','mc_enabled','mc_key_variable']
receipt_snapshot=rows.read(receipt_fields)
receipt_export=rows.export_data(['state','message_id','request_id'])['datas']
config_snapshot=server.read(config_fields)
config_export=server.export_data(['mc_enabled','mc_key_variable'])['datas']
assert not server.owner_user_id
assert 'company_id' not in Server._fields and 'company_id' not in receipts._fields
company_b=env['res.company'].create({'name':'Access Company B'})
for label,company in (('company A',env.company),('company B',company_b)):
 reader=access_user('receipt-reader-'+str(company.id),'base.group_user',company)
 admin=access_user('receipt-admin-'+str(company.id),'base.group_system',company)
 contexts=[]
 for role,is_admin in ((reader,False),(admin,True)):
  role_env=env(user=role,context=dict(env.context,allowed_company_ids=[company.id]))
  assert role_env.uid==role.id and role_env.user==role and not role_env.su
  assert role.has_group('base.group_user') and role.has_group('base.group_allow_export')
  assert role.has_group('base.group_system')==is_admin
  assert role.company_id==company and role.company_ids.ids==[company.id]
  assert role_env.context['allowed_company_ids']==[company.id]
  assert role_env.companies.ids==[company.id] and role_env.company==company
  contexts.append(role_env)
 check(label+' identities have sole allowed company, intended roles and non-sudo context')
 reader_env,admin_env=contexts
 restricted=server.with_env(reader_env)
 assert not {'mc_enabled','mc_key_variable'}.intersection(restricted.fields_get())
 denied(lambda:restricted.search([]))
 for fields in (['mc_enabled'],['mc_key_variable']):
  denied(lambda:restricted.read(fields))
  denied(lambda:restricted.export_data(fields))
 denied(lambda:restricted.write({'mc_enabled':False}))
 denied(lambda:restricted.write({'mc_key_variable':'MAILCHANNELS_OTHER_API_KEY'}))
 with patch('requests.post') as post:
  denied(lambda:restricted.test_smtp_connection())
  post.assert_not_called()
 scoped=rows.with_env(reader_env)
 denied(lambda:scoped.search([]))
 denied(lambda:scoped.search_read([],['request_id']))
 denied(lambda:scoped.read(['state','message_id','request_id']))
 denied(lambda:scoped.export_data(['state','message_id','request_id']))
 denied(lambda:scoped.create({'operation_key':'forged','payload_hash':'forged','state':'accepted'}))
 denied(lambda:scoped.write({'state':'rejected'}))
 denied(lambda:scoped.unlink())
 check(label+
       ' internal export user cannot access configuration, validate or access/mutate receipts')
 admin_rows=receipts.with_env(admin_env).search([],order='id')
 assert admin_rows.ids==rows.ids and admin_rows.read(receipt_fields)==receipt_snapshot
 assert admin_rows.export_data(['state','message_id','request_id'])['datas']==receipt_export
 admin_server=server.with_env(admin_env)
 assert admin_server.read(config_fields)==config_snapshot
 assert admin_server.export_data(['mc_enabled','mc_key_variable'])['datas']==config_export
 selected,sender=Server.with_env(admin_env)._find_mail_server('store@example.test')
 assert selected.id==server.id and sender=='store@example.test' and not selected.owner_user_id
 denied(lambda:admin_rows.write({'state':'rejected'}))
 denied(lambda:admin_rows.unlink())
 denied(lambda:admin_rows.create({
  'operation_key':'forged','payload_hash':'forged','state':'accepted'}))
 assert 'fixture-api-key' not in str(admin_server.read(['mc_key_variable','mc_enabled']))
 check(label+
       ' settings admin reads/exports same shared receipts/config and selects ownerless server')

scoped=rows.with_user(public)
denied(lambda:scoped.read(['state','message_id','request_id']))
try:scoped.export_data(['state','message_id','request_id'])
except UserError:pass
else:raise AssertionError('Public export was allowed')
denied(lambda:scoped.write({'state':'rejected'}))
denied(lambda:scoped.unlink())
check('non-admin cannot discover/read/export/write transport configuration')
check('non-admin cannot invoke provider configuration validation')
check('internal/public users cannot read/export/change/delete receipts')
check('settings admin can inspect/export receipts but cannot forge/change/delete them')
check('admin configuration exposes key variable name only, not credential')
rows.invalidate_recordset();server.invalidate_recordset()
assert receipts.search([],order='id').ids==rows.ids
assert rows.read(receipt_fields)==receipt_snapshot and server.read(config_fields)==config_snapshot
check('company access denials leave shared receipt set, contents and server configuration '
      'unchanged')

# Personal-server policy is sender/owner-association based, not caller-uid based.
from odoo.addons.mail_mailchannels.models.mail_server import APISession
from odoo.tools import email_normalize
owner=access_user('personal-owner','base.group_user',env.company)
owner_env=env(user=owner,context=dict(env.context,allowed_company_ids=[env.company.id]))
personal=Server.create({'name':'Personal API fixture','mc_enabled':True,'sequence':1,
 'from_filter':owner.email_normalized,'smtp_user':owner.email,'owner_user_id':owner.id})
owner.invalidate_recordset(['outgoing_mail_server_id','outgoing_mail_server_type'])
assert owner.outgoing_mail_server_id==personal and personal.active
# Durable receipts use another cursor and must see the real caller identities.
env.cr.commit()
for label,actor_env,is_admin in (('personal owner',owner_env,False),
                               ('Settings admin',admin_env,True)):
 assert not actor_env.su and actor_env.uid==actor_env.user.id
 assert actor_env.user.has_group('base.group_user')
 assert actor_env.user.has_group('base.group_system')==is_admin
 assert (actor_env.uid==owner.id)==(not is_admin)
 actor=Server.with_env(actor_env)
 assert not actor._disable_send()
 sender='Personal Owner <'+owner.email+'>'
 with patch('requests.post') as post, \
      patch('smtplib.SMTP',side_effect=AssertionError('Unexpected SMTP')) as smtp, \
      patch('smtplib.SMTP_SSL',side_effect=AssertionError('Unexpected SMTP SSL')) as ssl:
  selected,selected_sender=actor._find_mail_server(sender)
  assert selected.id==server.id and selected_sender==sender and not selected.owner_user_id
  default_session=actor._connect__(smtp_from=sender)
  assert isinstance(default_session,APISession)
  assert default_session.server.id==server.id and default_session.smtp_from==sender
  assert not actor._filter_mail_servers_fallback(personal)
  selected,_=actor._find_mail_server('unmatched@other.test',personal)
  assert selected is None
  post.assert_not_called();smtp.assert_not_called();ssl.assert_not_called()
 check(label+' default lookup/session and fallback exclude higher-priority personal server')
 with patch('requests.post',return_value=Response()) as post, \
      patch('smtplib.SMTP',side_effect=AssertionError('Unexpected SMTP')) as smtp, \
      patch('smtplib.SMTP_SSL',side_effect=AssertionError('Unexpected SMTP SSL')) as ssl:
  session=actor._connect__(mail_server_id=personal.id,smtp_from=sender)
  assert isinstance(session,APISession) and session.server.id==personal.id
  assert session.smtp_from==sender and session.from_filter==owner.email_normalized
  assert session.server.owner_user_id.id==owner.id
  assert email_normalize(sender)==personal.from_filter
  post.assert_not_called()
  m=message();m.replace_header('From',sender)
  original=m['Message-ID']
  assert actor.send_email(m,mail_server_id=personal.id)==original
  assert post.call_count==1
  payload=post.call_args.kwargs['json']
  assert payload['from']=={'email':owner.email,'name':'Personal Owner'}
  assert payload['envelope_from']['email']==owner.email
  assert payload['personalizations']==[{'to':[{'email':'buyer@example.test'}]}]
  assert payload['subject']=='Invoice ✓' and original in payload['headers']['References']
  with env.registry.cursor() as cr:
   receipt=env(cr=cr)['mailchannels.operation'].search([('message_id','=',original)])
   assert len(receipt)==1 and receipt.server_reference==personal.id
   assert receipt.state=='accepted' and receipt.http_status==202
   assert receipt.request_id=='fixture-request'
  smtp.assert_not_called();ssl.assert_not_called()
 check(label+' matched identity opens exact personal API session and sends with durable receipt')
 for case,values,mail_from,allow_archived in (
  ('wrong sender',{},'store@example.test',False),
  ('archived',{'active':False},sender,False),
  ('archived even when allowed',{'active':False},sender,True),
  ('stale owner association',{'smtp_user':'stale@example.test'},sender,False),
 ):
  personal.write(values)
  owner.invalidate_recordset(['outgoing_mail_server_id','outgoing_mail_server_type'])
  if case=='stale owner association':assert not owner.outgoing_mail_server_id
  m=message();m.replace_header('From',mail_from)
  identities=[str(m['Message-ID'])]
  with patch('requests.post') as post, \
       patch('smtplib.SMTP',side_effect=AssertionError('Unexpected SMTP')) as smtp, \
       patch('smtplib.SMTP_SSL',side_effect=AssertionError('Unexpected SMTP SSL')) as ssl:
   for operation in (
    lambda:actor._connect__(mail_server_id=personal.id,smtp_from=mail_from,
                           allow_archived=allow_archived),
    lambda:actor.send_email(m,mail_server_id=personal.id),
   ):
    try:operation()
    except UserError:pass
    else:raise AssertionError('Ineligible personal server reached API transport: '+case)
   if is_admin:
    owned_message=env['mail.message'].with_env(owner_env).create({
     'subject':'Denied personal queue','body':'<p>Denied</p>','email_from':mail_from,
     'message_type':'email','partner_ids':[(4,admin_env.user.partner_id.id)]})
    assert owned_message.create_uid.id==owner.id
    owned_message.with_env(actor_env).check_access('read')
    queue=env['mail.mail'].with_env(actor_env).create({'mail_message_id':owned_message.id,
     'email_to':'buyer@example.test','mail_server_id':personal.id,'auto_delete':False})
    identities.append(queue.message_id)
    try:queue.send(raise_exception=True)
    except MailDeliveryException:pass
    else:raise AssertionError('Ineligible personal server reached queued submission: '+case)
   post.assert_not_called();smtp.assert_not_called();ssl.assert_not_called()
  with env.registry.cursor() as cr:
   assert not env(cr=cr)['mailchannels.operation'].search_count([('message_id','in',identities)])
  personal.write({'active':True,'smtp_user':owner.email})
  owner.invalidate_recordset(['outgoing_mail_server_id','outgoing_mail_server_type'])
  assert owner.outgoing_mail_server_id==personal
  check(label+' '+case+' fails before HTTP/SMTP and receipt creation')

with patch('requests.post') as post, \
     patch('smtplib.SMTP',side_effect=AssertionError('Unexpected SMTP')) as smtp, \
     patch('smtplib.SMTP_SSL',side_effect=AssertionError('Unexpected SMTP SSL')) as ssl:
 try:
  with env.cr.savepoint():
   env['mail.mail'].with_env(admin_env).create({'subject':'Wrong creator',
    'body_html':'<p>Denied</p>','email_from':owner.email,'email_to':'buyer@example.test',
    'mail_server_id':personal.id,'auto_delete':False})
 except ValidationError:pass
 else:raise AssertionError('Queue creator constraint allowed another personal owner')
 post.assert_not_called();smtp.assert_not_called();ssl.assert_not_called()
check('Settings queue creation rejects personal server when message creator differs from owner')

# Native queues allow the mail.message creator's personal server; Settings processes it.
owned_message=env['mail.message'].with_env(owner_env).create({
 'subject':'Owner queue','body':'<p>Personal queue</p>','email_from':owner.email,
 'message_type':'email','partner_ids':[(4,admin_env.user.partner_id.id)]})
assert owned_message.create_uid.id==owner.id
owned_message.with_env(admin_env).check_access('read')
queue=env['mail.mail'].with_env(admin_env).create({'mail_message_id':owned_message.id,
 'email_to':'buyer@example.test','auto_delete':False})
assert not queue.mail_server_id and queue.mail_message_id.create_uid.id==owner.id
batches=list(queue._split_by_mail_configuration())
print('PERSONAL_QUEUE_SELECTION: '+repr({'batches':batches,'personal_server_id':personal.id,
 'owner_email':owner.email,'queue_email_from':queue.email_from,
 'creator_id':queue.mail_message_id.create_uid.id,'processor_id':queue.env.uid,
 'processor_su':queue.env.su}))
assert len(batches)==1 and batches[0][0]==personal.id
assert batches[0][2]==owner.email and batches[0][3]==(queue.id,)
with patch('requests.post',return_value=Response()) as post, \
     patch('smtplib.SMTP',side_effect=AssertionError('Unexpected SMTP')) as smtp, \
     patch('smtplib.SMTP_SSL',side_effect=AssertionError('Unexpected SMTP SSL')) as ssl:
 queue.send(raise_exception=True)
 assert queue.state=='sent' and post.call_count==1
 payload=post.call_args.kwargs['json']
 assert payload['from']['email']==owner.email and payload['envelope_from']['email']==owner.email
 assert payload['personalizations']==[{'to':[{'email':'buyer@example.test'}]}]
 assert payload['subject']=='Owner queue' and queue.message_id in payload['headers']['References']
 with env.registry.cursor() as cr:
  receipt=env(cr=cr)['mailchannels.operation'].search([('message_id','=',queue.message_id)])
  assert len(receipt)==1 and receipt.server_reference==personal.id
  assert receipt.state=='accepted' and receipt.http_status==202
  assert receipt.request_id=='fixture-request'
 smtp.assert_not_called();ssl.assert_not_called()
check('Settings queue selects owner-created personal identity and stores exact server receipt')

from email.parser import BytesParser
from email import policy
for label, extra, body in (
 ('malformed-base64', b'Content-Type: text/plain\r\nContent-Transfer-Encoding: base64\r\n', b'SGVsbG8'),
 ('duplicate-subject', b'Subject: private-fixture-marker\r\n', b'Hello'),
):
 ident='<'+uuid.uuid4().hex+'@example.test>'
 raw=(b'From: store@example.test\r\nTo: buyer@example.test\r\nSubject: Fixture\r\nMessage-ID: '+ident.encode()+b'\r\n'+extra+b'\r\n'+body)
 malformed=BytesParser(policy=policy.compat32).parsebytes(raw)
 with patch.object(type(Server),'_disable_send',return_value=False),patch('requests.post') as post:
  try:Server.send_email(malformed,mail_server_id=server.id)
  except (InvalidMessage, MailDeliveryException) as exc:
   assert 'private-fixture-marker' not in str(exc) and 'fixture-api-key' not in str(exc)
  else:raise AssertionError('Malformed MIME reached submission')
  post.assert_not_called()
 with env.registry.cursor() as cr:
  assert not env(cr=cr)['mailchannels.operation'].search_count([('message_id','=',ident)])
 check(label+' fails before provider call and receipt creation')

# Exercise the inherited browser form, not just ORM create (which ignores view required).
from odoo.tests import Form
api_form=Form(Server)
api_form.name='API form regression'
api_form.mc_enabled=True
api_record=api_form.save()
assert not api_record.smtp_host
check('API form saves without unused SMTP host')
smtp_form=Form(Server)
smtp_form.name='SMTP form control'
try:
 smtp_form.save()
except AssertionError:
 pass
else:
 raise AssertionError('Normal SMTP form lost its host requirement')
check('normal SMTP form still requires SMTP host')

# Odoo19's inherited Detect Max Limit action passes this keyword to the override.
with patch('requests.post') as post, patch('smtplib.SMTP') as smtp:
 try:
  server.test_smtp_connection(autodetect_max_email_size=True)
 except UserError as exc:
  assert 'cannot automatically detect' in str(exc)
 else:
  raise AssertionError('API transport claimed SMTP size detection')
 post.assert_not_called()
 smtp.assert_not_called()
check('API size autodetection refuses clearly before network access')
if hasattr(Server, 'action_retrieve_max_email_size'):
 from odoo.addons.base.models.ir_mail_server import IrMail_Server
 plain=Server.create({'name':'SMTP size control','smtp_host':'smtp.example.test'})
 expected={'type':'ir.actions.client','tag':'fixture-smtp-size-result'}
 with patch.object(IrMail_Server,'test_smtp_connection',autospec=True,return_value=expected) as upstream:
  assert plain.action_retrieve_max_email_size()==expected
  assert upstream.call_args.kwargs=={'autodetect_max_email_size':True}
 check('Odoo19 SMTP size detection preserves upstream argument and result')

print('RESULT: %s checks; no live API requests or email sent.' % len(checks))
env.cr.rollback()

# Exercise parser behavior on the actual Python/Odoo runtime, not a host shim.
exec(compile(open('/tests/mime_cases.py').read(), '/tests/mime_cases.py', 'exec'))
