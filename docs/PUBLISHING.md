# Company publisher and release handoff

No existing Odoo Apps publisher account is assumed. Support is
[dev@mailchannels.com](mailto:dev@mailchannels.com); a named release operator and
company-controlled publisher account still need to be assigned. This repository
has no release tag and has not been submitted to Odoo Apps.

1. Establish a company-controlled Odoo account and inspect the
   [Apps upload route](https://apps.odoo.com/apps/upload) and
   [vendor guidelines](https://apps.odoo.com/apps/vendor-guidelines). Complete
   publisher ownership/contact and agreement requirements through the company.
2. Establish isolated self-hosted/Odoo.sh acceptance environments for both 19.0
   and 20.0. Standard Odoo Online cannot install this Python module. Provision
   credentials through the host environment; confirm that every intended worker
   receives the correct secret and that company/server boundaries are appropriate.
3. Complete the release gates below and rerun the pinned native suites. Create
   version-specific branches or repositories with the built `mail_mailchannels`
   addon at the root expected by the Apps scanner. The development root must not
   be registered for Odoo 19 directly: `build.py` adapts its access-control format.
   Preserve technical name `mail_mailchannels` across versions.
4. Prepare actual UI screenshots, a product icon and `static/description/index.html`.
   The manifest's short title is **Email API Transport**; identify MailChannels and
   the required external account/service and possible service charges accurately.
   Follow current limits on promotional/external links; do not copy this GitHub
   README into Apps description HTML. No screenshots or production claims are
   supplied by the fixture tests.
5. Register the reviewed Git repository/branch in Apps, resolve scanner/reviewer
   feedback, and verify the public version pages, downloads, clean installation
   and update path. Repository registration alone is not acceptance.

## Remaining release gates

- Complete receipt reconciliation, retention and retirement of used installations.
  Do not delete receipts to unlock a send or uninstall. Archive API servers and
  retain the module until a reviewed migration/retirement plan is implemented.
- Finish invoice PDF, sales/chatter, notifications and marketing workflows;
  preserve native permissions and suppression/unsubscribe behavior. Password
  reset has native mocked coverage but no received-mail/browser completion test.
- Resolve known BCC-only and virtual-To-only limitations. Verify MIME/provider
  size limits and additional supported formats. The mapper is not SMTP-equivalent.
- Validate UI, RPC, multi-company isolation and actual Odoo.sh secret provisioning.
  Masked UI fields alone do not establish credential isolation.
- Validate domain authorization, envelope sender and incoming alias/catchall
  configuration. The API generates Message-ID; this transport preserves the
  original in References. Test actual reply threading, including clients that
  trim References, and actual bounce routing before claiming compatibility.
- Perform an explicitly authorized real-account dry-run, then separately
  authorized delivery/reply/bounce testing. A connection test must not mark
  business mail sent. HTTP acceptance is not inbox delivery.
- Validate historic schema/cross-major migrations and production backup/restore
  procedures. Tests cover same-version module refresh and normal uninstall only.

Do not publish this preview as production-ready while these gates remain open.
