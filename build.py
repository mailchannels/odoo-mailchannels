#!/usr/bin/env python3
"""Build a version-specific module tree; both versions use this same tested source."""
import argparse
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
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
        # This SMTP-only action exists in19, but was removed from the20 base view.
        view=module/'views/mail_server.xml'
        tree=ET.parse(view)
        arch=tree.find("./record[@id='mail_server_form']/field[@name='arch']")
        if arch is None:
            raise ValueError('Expected mail server form architecture missing')
        xpath=ET.SubElement(arch,'xpath',{'expr':"//button[@name='action_retrieve_max_email_size']",'position':'attributes'})
        ET.SubElement(xpath,'attribute',{'name':'invisible'}).text='mc_enabled'
        tree.write(view,encoding='unicode')
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
