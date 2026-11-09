{
    'name': 'Email API Transport',
    'version': '20.0.0.1.0',
    'summary': 'Opt-in MailChannels HTTP transport for transactional mail',
    'author': 'MailChannels',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'external_dependencies': {'python': ['requests']},
    'data': ['security/ir.access.csv', 'views/mail_server.xml'],
    'installable': True,
    'application': False,
    'uninstall_hook': 'uninstall_hook',
}
