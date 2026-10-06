#!/usr/bin/env python3
"""Build a version-specific module tree; both versions use this same tested source."""
import argparse
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent

def build(version, destination):
    if version not in ('19.0', '20.0'):
        raise ValueError('Supported build targets: 19.0 and 20.0')
    module=Path(destination)/'mail_mailchannels'
    shutil.copytree(ROOT/'mail_mailchannels', module)
    for name in ('LICENSE', 'COPYING.GPL3', 'README.md'):
        shutil.copy(ROOT/name, module/name)
    manifest=module/'__manifest__.py'
    manifest.write_text(manifest.read_text().replace('20.0.0.1.0',version+'.0.1.0'))
    if version=='19.0':
        manifest.write_text(manifest.read_text().replace('ir.access.csv','ir.model.access.csv'))
        acl=module/'security/ir.access.csv'
        acl.unlink()
        (acl.parent/'ir.model.access.csv').write_text(
            'id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n'
            'access_mc_operation_admin,MailChannels receipts admin,model_mailchannels_operation,base.group_system,1,0,0,0\n')
    return module

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('version', choices=['19.0','20.0'])
    parser.add_argument('destination', type=Path)
    args=parser.parse_args()
    print(build(args.version,args.destination))
