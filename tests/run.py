#!/usr/bin/env python3
"""Install and exercise the module in native Odoo, with no external network."""
import os, pathlib, subprocess, sys, tempfile, time, uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build import build
version=os.environ.get('ODOO_TEST_VERSION','20.0')
if version not in ('20.0','19.0'): raise ValueError('Supported fixtures: 20.0, 19.0')
IMAGES={'20.0':'odoo@sha256:cdd83e8359b3e8c357895d476396c05021fed9975bf420f353bab25fcaed1533','19.0':'odoo@sha256:dd9013e669caaa23d26765dc55814655eaeecca7cfc2c265dbabae913bce22fd'}
POSTGRES='postgres@sha256:1a6ab3f5345eb6dbe04a1349529caabdb0ab09293a09590fad07b2246bfa4b54'
network='visibility-odoo-'+uuid.uuid4().hex[:8];db=network+'-db'
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
 finally:
  subprocess.run(['docker','rm','-f',db],capture_output=True)
  subprocess.run(['docker','network','rm',network],capture_output=True)
