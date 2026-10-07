#!/usr/bin/env python3
"""Install and exercise the module in native Odoo, with no external network."""
import argparse, os, pathlib, subprocess, sys, tempfile, time, uuid
from review_tunnel import open_tunnel
parser=argparse.ArgumentParser()
parser.add_argument('--review-port',type=int,help='Keep disposable UI on this loopback port until Ctrl-C')
options=parser.parse_args()
if options.review_port is not None and not 1024 <= options.review_port <= 65535:
 parser.error('Review port must be between 1024 and 65535')
if options.review_port and os.environ.get('ODOO_LIFECYCLE_TESTS')=='1':
 parser.error('Browser review cannot follow lifecycle uninstall tests')
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build import build
version=os.environ.get('ODOO_TEST_VERSION','20.0')
if version not in ('20.0','19.0'): raise ValueError('Supported fixtures: 20.0, 19.0')
IMAGES={'20.0':'odoo@sha256:cdd83e8359b3e8c357895d476396c05021fed9975bf420f353bab25fcaed1533','19.0':'odoo@sha256:dd9013e669caaa23d26765dc55814655eaeecca7cfc2c265dbabae913bce22fd'}
POSTGRES='postgres@sha256:1a6ab3f5345eb6dbe04a1349529caabdb0ab09293a09590fad07b2246bfa4b54'
network='visibility-odoo-'+uuid.uuid4().hex[:8];db=network+'-db'
web=network+'-web';tunnel=None
def run(*args, **kwargs):
 p=subprocess.run(args,text=True,capture_output=True,timeout=300,**kwargs)
 if p.returncode: raise RuntimeError(p.stdout+p.stderr)
 return p.stdout+p.stderr
with tempfile.TemporaryDirectory(prefix='visibility-odoo-') as folder:
 addons=pathlib.Path(folder)
 build(version,addons)
 os.chmod(addons,0o755)
 try:
  run('docker','network','create','--internal',network)
  run('docker','run','-d','--name',db,'--network',network,'-e','POSTGRES_USER=odoo','-e','POSTGRES_PASSWORD=fixture-only','-e','POSTGRES_DB=postgres',POSTGRES)
  for i in range(60):
   if subprocess.run(['docker','exec',db,'pg_isready','-U','odoo'],capture_output=True).returncode==0:break
   time.sleep(1)
  else:raise RuntimeError('PostgreSQL not ready')
  base=['docker','run','--rm','-i','--network',network,'-v',str(addons)+':/mnt/extra-addons:ro','-v',str(ROOT/'tests')+':/tests:ro','-e','MAILCHANNELS_ODOO_API_KEY=fixture-api-key','--entrypoint','odoo',IMAGES[version]]
  args=['--db_host='+db,'--db_user=odoo','--db_password=fixture-only','-d','fixture','--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons','--max-cron-threads=0','--no-http']
  print(run(*base,*args,'-i','mail_mailchannels,auth_signup','--without-demo=True','--stop-after-init'),flush=True)
  result=run(*base,'shell',*args,input=(ROOT/'tests/native.py').read_text())
  if 'RESULT:' not in result:raise RuntimeError('Native test completion marker missing: '+result)
  print(result,flush=True)
  if os.environ.get('ODOO_LIFECYCLE_TESTS') == '1':
   lifecycle=(ROOT/'tests/lifecycle.py').read_text()
   for phase in ('seed','verify_upgrade','block_receipts','block_active','stale_snapshot','uninstall','verify_removed'):
    if phase=='verify_upgrade':
     print(run(*base,*args,'-u','mail_mailchannels','--stop-after-init'),flush=True)
    result=run(*base,'shell',*args,input='PHASE='+repr(phase)+'\n'+lifecycle)
    if 'LIFECYCLE_PASS: '+phase not in result:raise RuntimeError('Lifecycle completion marker missing: '+result)
    print(result,flush=True)
  print('NATIVE_ODOO_TESTS_COMPLETE '+version,flush=True)
  if options.review_port:
   seed="""env.ref('base.user_admin').write({'login':'browser-admin@example.test','password':'Local-Odoo-Fixture-12345!'})
Users=env['res.users'].with_context(no_reset_password=True)
groups_field='group_ids' if 'group_ids' in Users._fields else 'groups_id'
reader=Users.create({'name':'Browser internal fixture','login':'browser-reader@example.test','password':'Local-Odoo-Reader-12345!',groups_field:[(6,0,[env.ref('base.group_user').id,env.ref('base.group_allow_export').id])]})
assert not reader.has_group('base.group_system')
server=env['ir.mail_server'].create({'name':'Browser API fixture','mc_enabled':True,'from_filter':'example.test'})
env.cr.commit()
print('BROWSER_SERVER_ID='+str(server.id))
print('BROWSER_ACTIONS='+repr([(x.id,x.res_model) for x in env['ir.actions.act_window'].search([('res_model','in',['ir.mail_server','mailchannels.operation'])])]))
"""
   print(run(*base,'shell',*args,input=seed),flush=True)
   command=base.copy();command[2:2]=['--name',web,'-d']
   webargs=[arg for arg in args if arg!='--no-http']
   run(*command,*webargs,'--http-interface=127.0.0.1','--http-port=8069','--db-filter=^fixture$','--no-database-list')
   for i in range(90):
    check=subprocess.run(['docker','exec',web,'python3','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8069/web/login',timeout=2)"],capture_output=True)
    if check.returncode==0:break
    time.sleep(1)
   else:raise RuntimeError('Browser fixture not ready: '+run('docker','logs',web))
   tunnel=open_tunnel(web,options.review_port)
   print('BROWSER_READY http://127.0.0.1:'+str(options.review_port)+'/web/login?debug=1',flush=True)
   print('Synthetic login: browser-admin@example.test / Local-Odoo-Fixture-12345!; Ctrl-C cleans up.',flush=True)
   print('Internal user with export permission: browser-reader@example.test / Local-Odoo-Reader-12345!',flush=True)
   try:
    while True:time.sleep(1)
   except KeyboardInterrupt:pass
 finally:
  if tunnel:tunnel.shutdown();tunnel.server_close()
  subprocess.run(['docker','rm','-f',web],capture_output=True)
  subprocess.run(['docker','rm','-f',db],capture_output=True)
  subprocess.run(['docker','network','rm',network],capture_output=True)
