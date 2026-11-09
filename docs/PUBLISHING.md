# Company publisher and release handoff

A company-controlled Odoo publisher account exists. No repository is registered
and no publisher terms are accepted yet; terms that commit the company need company
approval before registration. This repository has no release tag and has not been
submitted to Odoo Apps. Support follows the public
policy in the README: this project is supported by the MailChannels team on a
best-effort basis; file an issue at
https://github.com/mailchannels/odoo-mailchannels/issues for project support.
MailChannels customers with service-operation problems should use
https://support.mailchannels.com/.

Release operator: Deniz Gunay, with Scott McKay as backup (decided 2026-11-09,
MAR-40). The operator builds the release branches, tags, registers the repository
and answers Apps review.

1. Establish a company-controlled Odoo account and inspect the
   [Apps upload route](https://apps.odoo.com/apps/upload) and
   [vendor guidelines](https://apps.odoo.com/apps/vendor-guidelines). Complete
   publisher ownership/contact and agreement requirements through the company.
2. Establish isolated self-hosted/Odoo.sh acceptance environments for both 19.0
   and 20.0. Standard Odoo Online cannot install this Python module. Provision
   credentials through the host environment; confirm that every intended worker
   receives the correct secret. Settings administrators share receipt metadata and
   ownerless outgoing-server configuration across companies; company selection and
   named key variables do not isolate them. Use separate Odoo deployments with
   separate databases when that administrator boundary is required.
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

## First release decision

Decided 2026-11-09 (MAR-40): production-account acceptance is the only gate that
must close before the first tag. Run the live suite against an authorized
production MailChannels account on Odoo 19 and 20: connection dry-run, delivery
with Reply-To and Return-Path kept, a reply routed to the original record and a
real DSN marking the notification bounced. The other gates below ship as known
limitations.

Production-account acceptance passed on 2026-11-09 on Odoo 19 and 20 (main
d30b8ce), using a MailChannels production test account and a dedicated test domain.
Test Connection completed its dry-run without writing receipts. One notification per version
was accepted and delivered with Reply-To and Return-Path kept and Odoo's IDs in
References. A reply sent through the production API threaded onto the original
record, and a real DSN marked the notification bounced. The first tag no longer
waits on any gate. List them in the release notes and the Apps description, and do not
describe the module as covering them.

## Known limitations and remaining gates


- Complete receipt reconciliation, retention and retirement of used installations.
  Do not delete receipts to unlock a send or uninstall. Archive API servers and
  retain the module until a reviewed migration/retirement plan is implemented.
- Finish complete invoice/sales/chatter, notifications and marketing workflows;
  the native quotation template and posted-invoice Send Invoice wizard have mocked
  PDF/recipient/chatter coverage, not full accounting/browser acceptance. Preserve
  native permissions and suppression/unsubscribe behavior. Password
  reset has native mocked coverage but no received-mail/browser completion test.
- Resolve known BCC-only and virtual-To-only limitations. Verify MIME/provider
  size limits and additional supported formats. The mapper is not SMTP-equivalent.
- Validate the intended deployment/administrator boundary, remaining company/role
  UI and RPC behavior, personal-server setup/management UI and actual Odoo.sh secret
  provisioning.
  Native two-company checks establish shared Settings administration, not company isolation.
  Native personal-server checks cover selection and forced-send eligibility, including
  queue processing by a different Settings administrator; they do not establish
  caller-based privacy or full personal-server setup acceptance.
  Masked UI fields alone do not establish credential isolation.
- Validate domain authorization, envelope sender and incoming alias/catchall
  configuration. The API generates Message-ID; this transport preserves the
  original in References. Test actual reply threading, including clients that
  trim References, and actual bounce routing before claiming compatibility.
  Synthetic native incoming qualification on pinned Odoo19/20 images covers
  retained reply References, preserved outer DSN References and DSNs that quote
  only the MailChannels Message-ID, which the receipt maps to the original. Stock
  single-partner fallback and repeated DSN bounce-counter increments remain
  limits. This does not establish real provider delivery or header preservation.
- Authorized live testing against a MailChannels test environment passed on
  Odoo 19 and 20: connection dry-run, delivery with Reply-To and Return-Path kept
  and Odoo IDs in References, a reply routed to the original record, and a real
  DSN marking the notification bounced through the stored MailChannels
  Message-ID. Production-account acceptance passed on 2026-11-09 (see above). A connection test must not mark
  business mail sent. HTTP acceptance is not inbox delivery. Odoo's invoice Sent
  flag can mean only PDF generation; operators must check queue/notification and
  receipt state, and reconcile an unknown outcome before creating a replacement.
- Validate historic schema/cross-major migrations and production backup/restore
  procedures. Tests cover same-version module refresh and normal uninstall only.

The first release may ship with the items above as documented limitations; do
not call it complete for those workflows.
