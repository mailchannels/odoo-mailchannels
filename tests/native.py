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

response=Response();response.status_code=200
with patch('requests.post',return_value=response) as post:
 server.test_smtp_connection()
 assert post.call_args.kwargs['params']=={'dry-run':'true'}
 check('configuration validation uses dry-run, not queue delivery')

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
from odoo.exceptions import AccessError, UserError
Users=env['res.users'].with_context(no_reset_password=True)
groups_field='group_ids' if 'group_ids' in Users._fields else 'groups_id'
def access_user(login,group):
 return Users.create({'name':login,'login':login+'@example.test','email':login+'@example.test',groups_field:[(6,0,[env.ref(group).id])]})
reader=access_user('receipt-reader','base.group_user')
admin=access_user('receipt-admin','base.group_system')
reader.write({groups_field:[(4,env.ref('base.group_allow_export').id)]})
assert not reader.has_group('base.group_system') and admin.has_group('base.group_system')
assert not env(user=admin).su

def denied(fn):
 try:
  with env.cr.savepoint():fn()
 except AccessError:return
 raise AssertionError('Expected native access denial')

restricted=server.with_user(reader)
assert not {'mc_enabled','mc_key_variable'}.intersection(restricted.fields_get())
for fields in (['mc_enabled'],['mc_key_variable']):
 denied(lambda:restricted.read(fields))
 denied(lambda:restricted.export_data(fields))
denied(lambda:restricted.write({'mc_enabled':False}))
denied(lambda:restricted.write({'mc_key_variable':'MAILCHANNELS_OTHER_API_KEY'}))
assert server.mc_enabled and server.mc_key_variable=='MAILCHANNELS_ODOO_API_KEY'
check('non-admin cannot discover/read/export/write transport configuration')

with patch('requests.post') as post:
 denied(lambda:restricted.test_smtp_connection())
 post.assert_not_called()
check('non-admin cannot invoke provider configuration validation')

receipts=env['mailchannels.operation']
row=receipts.search([],limit=1)
assert row
for role in (reader,public):
 scoped=row.with_user(role)
 denied(lambda:scoped.read(['state','message_id','request_id']))
 if role==reader:
  denied(lambda:scoped.export_data(['state','message_id','request_id']))
 else:
  try:scoped.export_data(['state','message_id','request_id'])
  except UserError:pass
  else:raise AssertionError('Public export was allowed')
 denied(lambda:scoped.write({'state':'rejected'}))
 denied(lambda:scoped.unlink())
check('internal/public users cannot read/export/change/delete receipts')

admin_row=row.with_user(admin)
assert admin_row.read(['state','request_id'])
assert admin_row.export_data(['state','request_id'])['datas']
denied(lambda:admin_row.write({'state':'rejected'}))
denied(lambda:admin_row.unlink())
denied(lambda:receipts.with_user(admin).create({'operation_key':'forged','payload_hash':'forged','state':'accepted'}))
check('settings admin can inspect/export receipts but cannot forge/change/delete them')
assert 'fixture-api-key' not in str(server.with_user(admin).read(['mc_key_variable','mc_enabled']))
check('admin configuration exposes key variable name only, not credential')

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
