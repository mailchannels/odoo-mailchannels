# Email API Transport for Odoo

Unreleased development preview for Odoo 20.0 and 19.0 on self-hosted Odoo or Odoo.sh. It is not published to Odoo Apps and is not production-ready. Standard Odoo Online cannot install this Python module.

The module adds an opt-in MailChannels transport to outgoing mail servers. It preserves Odoo's server selection, prepared envelope and no-send guard, uses the HTTPS Email API, and keeps the original Odoo message ID for threading while passing it in References. API acceptance is not delivery confirmation.

## Build and install

Build into a new directory outside this source tree:

```sh
python build.py 20.0 /tmp/mailchannels-odoo-20
python build.py 19.0 /tmp/mailchannels-odoo-19
```

The builder uses the correct version-specific access-control format: Odoo 20 `ir.access` versus Odoo 19 `ir.model.access`. Copy the resulting `mail_mailchannels` directory into that version's custom addons path, update the apps list, and install **Email API Transport**. Do not install the Odoo 20 source tree directly on Odoo 19.

Provision the API key through the server's secret-management/environment mechanism, using `MAILCHANNELS_ODOO_API_KEY` or another dedicated `MAILCHANNELS_*API_KEY` name. Never put the key in source, a module manifest, screenshots or a browser form. The model stores only the environment-variable name. All workers must receive the same intended configuration. Separate servers can use different named variables.

As an administrator, configure an outgoing mail server and enable **Use MailChannels Email API**. Configure its normal FROM filter/priority carefully. For API servers, the form hides SMTP authentication/connection controls and does not require an SMTP host. The SMTP host, port, encryption and password settings are not used: HTTPS always verifies TLS, uses a fixed provider URL and does not follow redirects. Normal mail servers remain on their existing transport.

Odoo19’s **Detect Max Limit** action is SMTP-specific. It is hidden for API servers, and direct API-mode invocation raises a clear error without a network request. Ordinary SMTP servers retain native size detection. Configure attachment handling against the current Email API limits; SMTP SIZE negotiation cannot discover them.

The connection test on an API server calls the provider's **dry-run** endpoint with the current test sender/recipient; it sends no email and does not mark queued business messages as sent. Configure authorized visible and envelope sender domains, including SPF/Domain Lockdown and DKIM as appropriate. Successful local fixtures do not establish that your account/domain is ready.

## Submission receipts and retries

Technical → Email → **MailChannels Submission Receipts** is administrator-readable. Each recipient has a hashed operation key based on server ID, the original Odoo message ID and recipient. Receipts contain a payload digest, original ID, server reference, acceptance state, HTTP status and optional provider request ID. They do not store the key, body, recipient list or raw provider response. Message IDs and provider IDs may still be sensitive operational metadata.

Receipts are committed in a separate database transaction before network submission so a rollback of Odoo business state cannot erase the fact that submission started. Database uniqueness and locks prevent two workers reserving the same recipient identity. If the receipt cannot be committed, no API call occurs.

- An accepted identical operation returns success without another API call.
- An accepted recipient overlapping a changed envelope or payload blocks the whole retry.
- Rejected operations are retained and require review before deliberately creating a new outgoing message.
- Timeouts, redirects, 5xx responses, process failure or uncertain persistence outcomes must be treated as potentially submitted. They cannot be automatically reset or resent.

There is intentionally no receipt-delete/reset button. Do not delete these records to make retries work. Review provider evidence before any replacement message. A full operator reconciliation workflow and bounded retention policy remain release requirements. Changing server IDs, copying databases or deleting historical receipts can defeat deduplication; operational migrations need a reviewed plan.

Uninstall is blocked while any submission receipts exist, including rejected or
uncertain records. Archive the MailChannels outgoing servers and leave the module
installed when retiring this transport. Do not remove receipts to bypass the guard:
removal needs a reviewed archive/migration and retirement plan for old queued mail.
The module also blocks uninstall while any MailChannels server remains active,
even if no receipts exist, to prevent accidental conversion to SMTP. A never-used
installation can be removed after its API servers are archived; unrelated SMTP
servers remain available. Run module maintenance with mail workers stopped and a
verified database backup. Database/superuser modifications outside the normal
uninstall process can bypass these safeguards.

Odoo's native status may say “sent” following HTTP 202. This means provider acceptance only. The separate receipt explicitly says “Accepted by API”; delivery/bounce reconciliation remains a release requirement.

## Supported mapping and limits

The current mapper covers one visible From, one Reply-To, text/plain and text/html bodies, named attachments, inline Content-ID attachments, envelope sender, To/CC/BCC intersection with Odoo's validated envelope, References/In-Reply-To and unsubscribe headers. It never inserts virtual displayed recipients into the delivery envelope. Marketing classification can be explicitly supplied through `X-MailChannels-Transactional: false`; this is not a complete Odoo Marketing integration.

Messages with no deliverable visible To, unsupported multipart types, duplicate body types, unnamed attachments, unsupported text encodings or malformed classification fail before submission. This includes some BCC-only and virtual-To-only workflows. These are known compatibility gaps, not supported cases. Do not enable this transport globally until the site's actual mail flows have passed validation. Arbitrary custom MIME headers, encryption/signatures, all marketing workflows and complete SMTP equivalence are not claimed.

The converter also rejects parser-reported MIME defects, duplicate identity or
MIME headers, unknown transfer encodings and malformed Base64 before creating a
receipt or calling the provider. Valid Base64 line whitespace, charset decoding
and inline binary attachments are covered by native-runtime regression tests.
This is not a complete MIME validator or proof of every message format; the
remaining workflow and provider-limit checks still apply.

Current incoming-mail/alias/catchall configuration remains necessary. Real received headers, chatter replies and bounces have not been verified. Provider Message-ID is not writable; the implementation relies on References and needs real-client reply tests before release.

## Validation

From this repository root:

```sh
docker pull odoo:20.0
docker pull odoo:19.0
docker pull postgres:16
python tests/run.py
ODOO_TEST_VERSION=19.0 python tests/run.py
```

Set `ODOO_LIFECYCLE_TESTS=1` on either command to additionally exercise a native
same-version module upgrade, refused uninstall with receipts, refused uninstall
with an active API server, and removal of an unused/archived fixture. These tests
use a disposable database and delete synthetic receipts only to reach the empty
installation scenario; that test step is not an operator recovery procedure.

The runner builds the same version-specific module used for installation, creates a disposable PostgreSQL/Odoo environment on an internal Docker network, installs the real module and exercises ORM/queue behavior through `odoo shell`. Requests are mocked; no external API/email traffic is permitted. Containers, network and temporary addon files are removed afterwards. Exact image digests are pinned in `tests/run.py`; see [validation coverage](docs/VALIDATION.md).

Remaining release gates: browser settings/ACL/export validation, invoice/sales/chatter/marketing application scenarios, incoming reply and bounce tests, MIME edge cases, receipt reconciliation/retention UX, used-installation retirement and cross-major migration policy, Odoo.sh secret-provisioning validation, publisher account setup, real account dry-run, separately authorized delivery and Apps review.

Support owner: dev@mailchannels.com (confirmed by MailChannels). A company Odoo Apps publisher account still needs to be established. This local beta is not yet published or production-ready.

Native password reset is now exercised on Odoo 19 and 20 with auth_signup installed: actual template/queue/default-server selection, one mocked API POST, no SMTP, correct recipient and valid owner-bound reset link; reset token absent from receipts. See [validation coverage](docs/VALIDATION.md). Browser reset and actual delivery are still unverified.

Native ORM/export acceptance passes on both versions as part of the native checks. An ordinary internal user with export permission cannot discover/read/export/write transport configuration or read/export/change/delete receipts, and cannot invoke configuration validation. A non-superuser settings admin can read/export receipts but cannot create, change or delete them. See [validation coverage](docs/VALIDATION.md). The internal-user browser/RPC deny paths also pass on both versions; the administrator receipt CSV export and native HTTP export deny path also pass on both versions. Complete role/company, visual/accessibility and broader export validation remain.

Publisher setup and submission requirements: [Odoo Apps handoff](docs/PUBLISHING.md).
Source publication is not an Odoo Apps release or production acceptance.

### Disposable browser review

Run `python3 tests/run.py --review-port 18190` (optionally with
`ODOO_TEST_VERSION=19.0`). After the native checks pass, open the printed loopback
URL and use the printed synthetic admin or internal-user login. The internal user
has export permission but no Settings administrator role. The database contains only fixture mail
and receipts. The web server uses the same Docker internal network; a loopback
`docker exec` relay exposes the UI without publishing container ports. Ctrl-C
removes the web/database containers, network and temporary module build.
Do not combine browser mode with lifecycle tests, which uninstall the module.

Do not enter real credentials or click Test Connection expecting a working live
service: the fixture key is synthetic and the server has no internet route.
Odoo19/20 browser review verified save/reload of an API server without SMTP host
and readable desktop/narrow configuration; the receipt list was inspected on20.
On19/20, the internal-user session is denied both protected pages and direct RPC
read/export/test actions, and protected fields are absent from field metadata.
RPC denials have HTTP200 with an AccessError payload; HTTP status alone is not
a success check. Administrator receipt CSV exports on both versions retain all14synthetic
receipts and the selected fields; the internal-user CSV HTTP route is also denied.
See docs/VALIDATION.md for reproduction and limits. Complete role/company, visual/
accessibility, broader export, business flows and live-provider acceptance remain open.

For native quotation-template, posted-invoice wizard and real PDF transport checks, add
`ODOO_BUSINESS_TESTS=1` to the test command. This installs Sales and starts an
internal-only asset server with shared disposable attachment storage. The check
compares the rendered PDFs with the API attachments, checks native invoice chatter,
and verifies accepted quotation replay
without a second request. It does not establish complete sales/invoice/browser
or live-delivery acceptance. CI enables this alongside the lifecycle suite.

Do not use the invoice's native **Sent** label as proof of API acceptance or
email delivery: Odoo sets it when the PDF is generated, including on email
failure. Check the email queue and recipient notification together with the
MailChannels submission receipt. Rejected/unknown receipts block the same
message's Retry action from making another API request. Do not create a new
message or delete receipts to bypass that protection; reconcile the original
outcome first. The current receipt screen is not a complete reconciliation UI.
