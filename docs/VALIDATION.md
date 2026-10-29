# Validation coverage

This is a development preview, not an Odoo Apps release. All provider requests in
these tests are mocked. No real account, delivered email or reply/bounce flow has
been validated.

`tests/run.py` builds and installs the same version-specific module a maintainer
would install. It uses digest-pinned Odoo 19 and 20 images (20260926 builds) and
PostgreSQL 16 on a Docker internal network with no published ports. Exact digests
are in the runner. It installs `mail` and `auth_signup`, exercises the native ORM
and mail queue through `odoo shell`, and removes the disposable resources, including
the PostgreSQL container's anonymous data volume.

Run both versions with full lifecycle coverage:

```sh
ODOO_TEST_VERSION=19.0 ODOO_LIFECYCLE_TESTS=1 ODOO_BUSINESS_TESTS=1 python3 tests/run.py
ODOO_TEST_VERSION=20.0 ODOO_LIFECYCLE_TESTS=1 ODOO_BUSINESS_TESTS=1 python3 tests/run.py
```

The suite includes 54 native checks on19 and53 on20: queue/session routing, the
administrator-only HTTPS `*.mailchannels.net` endpoint override, recipient
and attachment mapping, native no-send mode, accepted replay, rollback and worker
failure protection, overlapping recipient rejection, concurrent submissions,
sanitized failures, separate configuration dry-run, real password-reset template
and token ownership, and non-superuser ORM/export/method access controls.
Malformed Base64 and duplicate Subject are tested through native `send_email`:
both fail without an HTTP request or submission receipt.

Twelve MIME tests cover valid folded Base64; corrupted Base64 bodies/attachments;
unknown transfer encoding; duplicate identity and MIME headers; missing multipart
boundaries; unsupported signed MIME; and Unicode/ISO-8859-1 text, HTML and inline
binary Content-ID preservation. Three additional cases verify obsolete empty
recipient-list slots, envelope filtering and retained rejection of invalid recipient
and sender-header defects. These are not an exhaustive MIME validator.

Seven lifecycle phases cover fixture setup, exact receipt/configuration
preservation through a same-version module upgrade, real uninstall refusal when
receipts exist, refusal when an API server remains active, a late committed receipt
hidden from the original repeatable-read snapshot, clean unused-fixture removal,
and verification that API servers remain archived while normal SMTP configuration
is unchanged. Expected refusal paths log registry-load errors; the test requires
installed state and receipts to remain intact afterward.

Lifecycle tests deliberately remove synthetic receipts in a disposable database
to reach the empty-installation case. This is not a production recovery procedure.
Used installations need a reviewed archive/migration and old-queue retirement plan.
Major-version migrations, arbitrary third-party uninstall hooks and complete
company/role/browser/export acceptance remain outside this coverage.

## Shared administration across companies

The native suite creates a second synthetic company and four real identities: a
Settings administrator and an internal user with export permission, each allowed
only company A or company B. It asserts user identity, groups, sole allowed company,
actual `env.company` and non-superuser mode before exercising access.

Both administrators read and export the same existing global receipts and outgoing
server configuration. The existing API server is ownerless; native selection for
`store@example.test` returns that same server in both company contexts. Both internal
users are denied configuration discovery/read/export/write and validation, with a
native AccessError and no provider call. Receipt search/read/export/create/write/delete
are denied to both internal users; administrators cannot create/write/delete receipts.
The existing public-user checks remain, and the shared receipt set, receipt contents
and server configuration are unchanged after the denials. No extra mail submission
is created for these company checks.

These expectations come from the exact installed 19.0-20260926 and 20.0-20260926
core/mail models and security definitions in the runner's pinned images. Neither
`ir.mail_server` nor `mailchannels.operation` has a company field in this fixture;
Settings access and the receipt read grant have no company restriction. Company
selection therefore does not partition shared configuration or receipt metadata.
Use separate Odoo deployments with separate databases when administrators must be
isolated from another company's mail metadata. Named key variables select worker credentials;
they do not establish company access boundaries.

This checks shared Settings administration, not complete company isolation, browser
company switching, deployment or Odoo.sh provisioning.

## Native personal outgoing servers

Fourteen additional native checks exercise a real internal owner and a different
Settings administrator, both without superuser mode. A higher-priority personal API
server matches the owner's normalized email and SMTP username. Ordinary default
lookup and default API sessions still select the shared ownerless server; personal
servers are also excluded from unmatched-sender fallback. The native queue has a
separate creator-based selection path: a mail.message created by the owner can use
that personal server when a Settings administrator processes its mail.mail queue.
The synthetic owner explicitly shares the mail.message with that administrator and
the test asserts native read access; Settings membership alone does not grant access
to every user's messages. The queue still targets only the intended buyer.
A deliberate negative control verifies that queue creation rejects a forced personal
server when its mail.message creator is a different user, before any HTTP/SMTP call.

Both identities can force the active personal server for the matching sender. Tests
assert the exact APISession/server/smtp_from, provider sender and envelope, intended
recipient, one mocked request, unchanged Message-ID/References and an accepted
receipt independently read from another cursor with the exact server_reference.
The owner-created queue also asserts its selected batch/server/smtp_from, sent state,
payload, request count and durable receipt. Native mail.mail access is Settings-only;
the internal owner is not granted queue-management permission by this fixture.

Wrong sender, archived server, archived server with allow_archived=True, and stale
owner association each fail before HTTP, SMTP or receipt creation in both caller
contexts. A stale SMTP username is applied to the fixture and the real computed
owner association is invalidated and checked; no native policy method is mocked.
Settings-admin queue attempts cover the same ineligible states. Only requests.post
is mocked and SMTP/SMTP_SSL are blocked for these cases; the real no-send state,
selection and forced-server guards remain active.

The installed 19/20 mail guard compares the normalized sender with from_filter,
requires an active personal server even when allow_archived=True, and verifies that
its owner currently associates with that server. It does not compare the caller uid
with the owner uid: the different Settings administrator and native queue may process
that matching sender identity. These tests preserve that native policy; they do not
establish caller-based privacy, company isolation, personal-server setup UI, provider
credentials/domain acceptance, rate-limit boundaries or every third-party queue path.
Production transport and access-control behavior are unchanged.

### Odoo 20 personal setup browser check

On 2026-10-10 UTC (2026-10-09 in America/Vancouver), source
`792c964431c8eecce9737f7f1b2909190d254c1c` was installed through the existing
`tests/run.py --review-port 18197` in the pinned Odoo 20.0-20260926 fixture.
Initialization passed 50 native checks and 12 MIME cases. Business/lifecycle and
Odoo 19 checks were not rerun. The Docker network was internal, cron was disabled,
and no Test Connection, send, reset or provider-account action was invoked.

The regular Settings administrator was uid 2, not superuser uid 1. The selected
owner was the runner's ordinary internal/export user uid 11, distinct from the
native suite's personal owner uid 10. Fixture preparation set only uid 11's
synthetic email and `base_setup.default_external_email_server=True`; it did not
seed a personal server association. That parameter is the native **Use Custom
Email Servers** General Settings field and makes the Preferences selector visible.
Configuring that setting through the browser was outside this bounded check.

In the actual new outgoing-server form with `debug=1`, select **Owner** while
MailChannels is off, then enter the exact owner email in **User email** (the native
`smtp_user`) and leave that field before enabling MailChannels. Set the matching
FROM filter and `MAILCHANNELS_ODOO_API_KEY` variable name, then save in API mode.
The API form hides the native authentication section and Connection notebook,
including Owner/User email; no intermediate SMTP-mode save was performed.
The initial rapid input sequence entered Username before selecting Owner and
saved without that username. Its failed persisted assertion is retained: owner
was uid 11 but `smtp_user=False` and `outgoing_mail_server_id=False`. A single
browser retry entered User email after the selected owner, left the field with
Tab, then enabled MailChannels and saved. This input-order observation is not a
diagnosed production defect or a reason to change native policy.

Reload showed the saved API form. An independent native ORM read asserted record
5 active, MailChannels enabled, variable name only, Owner uid 11, username and
FROM filter equal to the owner's email, and empty SMTP host/password. The owner's
computed `outgoing_mail_server_id` was exactly 5. Desktop 1280×720 and narrow
390×844 captures show readable fields, with narrow scroll width 390. This is
bounded rendering evidence, not an accessibility signoff.

The owner's native user-menu **My Preferences** showed Default/Gmail/Outlook and
selected **Default**. There is no MailChannels choice, key field or personal API
setup control there. The installed compute maps native `smtp_authentication=login`
to `outgoing_mail_server_type=default` despite the valid linked API server; the
widget's connection button requires a non-default type, so it was absent. A direct
full-page Preferences route without a record ID attempted user creation and showed
Access Error; the user-menu entry successfully opened the current owner's record.
No Preferences option was changed or saved. The same owner was denied record 5's
transport page and the submission-receipt page with Access Error and no protected
data rendered. The tested forms showed no API credential value or credential-entry
control; only the administrator's environment-variable-name control was present.

The browser tab, tunnel, web/database containers, internal network, named filestore
and attributable PostgreSQL anonymous volume were removed. Final inventories had
no added container/network/volume IDs and the loopback port was closed; pre-existing
resources were preserved. Source-bound logs, seed/read scripts, screenshots, UI
phase times and hashes are retained in the coordinated MAR-207 evidence package.
This check establishes one Odoo 20 administrator workflow and one owner role only.
Full role/company and export matrices, accessibility, provider
and deployment acceptance, retention/reconciliation/retirement, incoming replies
and bounces, Odoo.sh, publisher setup and Apps/release gates remain open.

On 2026-10-10 in America/Vancouver, the same bounded procedure passed on pinned
Odoo 19.0-20260926 using source `5e9b7af3dcda9fbb087c0d3f141e5ac4a7d8ff2b`.
Initialization passed 51 native checks and 12 MIME cases; business/lifecycle and
Odoo 20 were not rerun. Browser sessions verified Settings administrator uid 2
and ordinary internal/export owner uid 11 without Settings administration.
Only the synthetic email and custom-email setting were seeded, with no owner link.
Selecting Owner, entering User email and leaving it with Tab while MailChannels
was off, then enabling API mode and saving once produced server 6. Reload and
native readback verified the exact owner association, matching username/FROM
filter, API variable name, MailChannels enabled, and empty SMTP host/password.
The owner's user-menu Preferences showed Default/Gmail/Outlook with Default
selected and no MailChannels setup or connection button; no option was changed
or saved. The same owner was denied server 6 and the receipt action 143.
Desktop 1280×720 and narrow 390×844 views were inspected with scroll width 390;
the native owner email input truncates visually at narrow width. This is bounded
rendering evidence, not full visual or accessibility signoff. The tested tab and
owned fixture resources were removed; an initial refused-connection temporary
tab could not be selected for closing under the browser data-URL policy and was
left unmarked for automatic end-of-turn cleanup. MAR-216 retains logs, native
source snapshots, screenshots, failed attempts, hashes and cleanup observations.

### Native global custom-email setting browser check

On 2026-10-10 in America/Vancouver, fresh pinned Odoo 19.0-20260926 and
20.0-20260926 fixtures used unchanged runtime source `5e9b7af3dcda9fbb087c0d3f141e5ac4a7d8ff2b`.
Initialization passed 51/50 native checks respectively and 12 MIME cases each.
Read-only native checks proved `base_setup.default_external_email_server` initially
absent and the ordinary owner's `has_external_mail_server` false. Unlike the earlier
personal-server fixtures, this check did not seed the global parameter.

Actual Settings administrator uid 2 checked **Use Custom Email Servers** in native
General Settings, saved and reloaded on each version. The checked browser control,
raw `True` parameter written by uid 2 and ordinary uid 11's computed visibility agreed.
The ordinary internal/export owner's user-menu Preferences showed no mail selector
beforehand and Default/Gmail/Outlook with Default selected afterward. No selector
choice or Preferences save was made; the owner remained without a linked mail server.

The administrator unchecked the setting, saved and reloaded. Odoo 19 removed the
parameter row; Odoo 20 retained raw `False`, whose typed getter and owner compute
returned false. This restores the initial effective setting, not a byte-identical database.
Two native settings saves per version and their uid 2 records/HTTP request paths are
retained with desktop 1280×720 and narrow 390×844 screenshots, browser UIDs and
installed settings/user/widget sources in MAR-217. Server records and receipt counts
stayed unchanged. Owned fixture resources and tabs were removed. This global setting
does not establish company isolation, MailChannels configuration through Preferences,
full accessibility, live-provider or production acceptance; existing release gates remain.

See [publishing requirements](PUBLISHING.md) for the remaining release gates.

Two form regressions use Odoo's actual `Form` helper: an API server saves without
an SMTP host, while an ordinary SMTP server still requires it. ORM create alone
missed this view-level defect. Odoo19/20 browser save/reload and desktop/narrow
rendering were also checked; the receipt list renders acceptance/unknown/rejected
states. This earlier review does not validate every browser role, export UI, every business flow,
all version-specific browser behavior or a real provider. Use the README browser-review mode
to reproduce these checks without external provider traffic.

Odoo19/20 internal-user browser/RPC check: the user has base internal-user and export
permissions, but not Settings administration. Direct configuration and receipt
pages display Access Error. Session-authenticated RPC denies configuration read,
export and connection-test invocation, plus receipt search/read and export.
Protected configuration fields are omitted by fields_get. Each denied RPC has
HTTP200 and an odoo.exceptions.AccessError payload, with no result. This is a
specific deny-path check, not complete browser role/company/export acceptance.

Size-detection regression: the old override raised TypeError when Odoo19’s
inherited Detect Max Limit action passed autodetect_max_email_size. API-mode
invocation now raises a clear UserError before HTTP/SMTP access on19/20. On19,
a mock of the native SMTP method confirms both the keyword and returned action
are preserved for ordinary SMTP servers. The19builder hides the SMTP-only button
for API servers;20has no such base-view control. The numerical SMTP limit itself
is not validated against a real server, and API payload-size acceptance remains
part of provider-limit testing.

Odoo20 browser follow-up used the unchanged implementation at 8d2aaff9b66cc96572dc08c8c0f46b504e251616.
The native user-menu Log out action switched sessions; GET /web/session/logout
returns Method Not Allowed on this fixture. An administrator positive control
read the configured API server before the restricted-user checks. Both denied
pages were captured and visually inspected. The fresh fixture passed29native
and9MIME checks; no lifecycle rerun was needed for this browser-only review.

## Native quotation and posted invoice

`ODOO_BUSINESS_TESTS=1` installs the native Sales app in the disposable database.
Seven checks render its quotation email template and actual PDF report, process
that mail through the native queue, replay the accepted mail, and exercise the
Send Invoice wizard for a posted customer invoice. Invoice acceptance also checks
that native chatter retains the intended customer and generated PDF. The test verifies
only the intended customer is targeted and the API attachment matches the generated
PDF byte for byte, including filename. SMTP is blocked and requests.post is mocked.
An internal-only Odoo asset server and shared temporary filestore support the real
renderer; report/storage failures fail the harness. No container port is published.
The filestore volume, server, database and network are removed by the runner.

This validates the template/queue boundary, not the Send by Email browser composer,
a PDF visual review, full invoice accounting/localization coverage, salesman permission matrix,
chatter notifications, marketing suppression, receipt reconciliation or live delivery.

The native Odoo19 invoice wizard initially failed before API submission because
its To header includes an empty comma-separated list slot. The mapper now accepts
only Python's ObsoleteHeaderDefect for an empty address-list entry on To/Cc/Bcc.
All other header/body defects remain rejected; no new envelope recipient is inferred.
The posted-invoice test reproduces the original failure and passes with this fix.
The synthetic company/journal validates dispatch, not fiscal localization or full
accounting, role, browser or live-provider behavior.

Invoice failure checks cover HTTP400 rejection and transport timeout. They require
committed native queue/recipient-notification states and durable rejected/unknown
receipts, then exercise Odoo's actual Retry action and confirm no second request, including
postcommit callbacks. Independent database reads verify the failed states persist.
The invoice's is_move_sent flag stays true because Odoo also uses it for generated
PDFs; it is not an acceptance or delivery indicator. Browser rendering of failure
notifications, deliberate new-message resend and reconciliation workflows remain
separate release gates.

The combined failure fixture ends the snapshot opened around each synthetic
invoice-creation commit and invalidates the cache before simulating the next
request. Odoo20's accounting postcommit hook updates customer rank through another
cursor; reusing the original shell snapshot caused a serialization conflict. This
fixture correction does not disable the hook or change production transaction rules.

## Native incoming replies and DSNs

The same business suite adds synthetic native incoming qualification on the
digest-pinned Odoo 19/20 images. A separate posted invoice uses the actual Send
Invoice wizard and a copied native template with auto_delete disabled. The test
observes its outgoing queue, original message/customer notification, one mocked
HTTP202 request and committed acceptance receipt, then keeps the sent mail for
replay. Original References, recipient, subject, sender identities, payload and
operation hashes are checked; the API payload has no custom Message-ID.

Ten cases process retained RFC bytes through native message_process with fresh
gateway cursors. They cover retained References with an unmatched synthetic
provider In-Reply-To, original-Odoo-ID-only In-Reply-To, duplicate reply, known
quotation reference and unmatched-reference refusal. Positive replies check the
exact invoice/quotation, parent, customer author, UTF-8 body and R1 attachment.
A native Settings user configured for inbox notifications follows both records;
the exact sent inbox notification is checked. This controlled follower set creates
no new email queue, HTTP request, SMTP or SMTP_SSL call, including postcommit work.
The no-route recipient is verified absent from aliases and alias domains; this
does not qualify catchall delivery or every follower/notification policy.
The gateway returns the exact record ID on Odoo19 and the exact model/recordset
IDs on Odoo20. Unrouted DSNs return False on19 and an empty mail.thread recordset
on20; duplicate replies return False on both. Assertions check these native values
without converting the return type.

Multipart/report DSNs cover an unknown rewritten enclosed ID with only enclosed
References, a real known wrong Final-Recipient partner, preserved outer References,
and repetition of the same positive DSN. Enclosed References alone do not match
the original. Outer References match the original notification only when the
recipient also matches; it becomes bounce/mail_bounce with the native plain-text
reason. The native fallback to a sole notification partner when no recipient
partner is found remains a limit; the wrong-recipient fixture deliberately uses a
known unrelated partner. Stock email-wide bounce counters increment even without
an original-message match, and a repeated DSN increments again. DSNs are not
stored as ordinary chatter, so this is not a DSN idempotence guarantee.

Every case checks committed original/sibling messages, notifications, queue,
business/customer/financial identity and complete relevant receipt fields before
and after. Receipts, including their timestamps, remain API acceptance evidence
and are unchanged by replies or bounces. Fresh ORM reads expose a cleared
failure_type as False on both versions; Odoo19's native sender writes an empty
string before that read. No handler, parser, router or notification implementation
is replaced. The copied template is removed after the cases so it does not block
the inherited lifecycle fixture's normal server retirement.

Synthetic provider IDs and original-reference preservation are fixture assumptions,
not observed provider behavior. Real provider rewriting/outer DSN shape, clients
trimming References, alias/catchall delivery configuration, account/domain dry-run
and separately authorized received-mail/reply/bounce tests remain release gates.
No provider delivery or header-preservation result is claimed.

## Receipt list and CSV export

On 2026-10-09 UTC, source commit `919a7213667897aef904809b25b1503928e94e6b`
was installed in fresh pinned Odoo 19/20 review fixtures. The native checks passed
(30 on 19, 29 on 20, plus 12 MIME cases each). A regular settings administrator
session (uid 2, not the superuser uid 1) selected all 14 synthetic receipts, opened
**Actions → Export**, retained the six list fields and added **Operation Key** and
**Payload Hash**, selected CSV and invoked the native Export button.

Both native `/web/export/csv` responses returned HTTP 200 with a CSV attachment.
The captured CSV had 14 rows, accepted/unknown/rejected display labels, 14 unique
64-character operation hashes and valid payload hashes. The available field list
and selected export contained no API key, recipient-list or message-body field;
the exported data contained none of the fixture credential, recipient, subject,
body or attachment markers. Message and provider IDs remain operational metadata
and can be sensitive in a real installation.

Repeat with the README review runner on each supported version. In the receipt
list, select the records, use Actions → Export and choose the fields above. Leave
**I want to update data (import-compatible export)** off on 19, or **Updatable
fields only** off on 20. Choose CSV. Export is for inspection; do not import or
modify receipts as a reconciliation or retry mechanism.

The fixture internal user (uid 8, export permission, no Settings administrator
role) could not open the receipt list: Access Error, zero receipt rows. A direct
session-authenticated POST to the CSV route for known receipt ID 1 also returned
AccessError, no CSV attachment and no receipt data on both versions. The native
route uses HTTP 500 for this permission exception; distinguish it from a valid
HTTP 200 CSV attachment rather than assuming every response is a download.

Evidence was collected through T3 browser DOM interaction and an observational
XHR load listener on the actual native download response; no controller or
request/response result was mocked. Screenshot capture failed, so this does not
establish visual, physical keyboard, assistive-technology or OS file-save
acceptance. On the private HTTP review origin, Odoo 20's optional tour module
reported a missing Clipboard API; its dialogs were dismissed before export. This
is not evidence of a production HTTPS failure or a module transport fix.
That CSV-only check did not validate XLSX, export templates or grouped/paginated large exports.
Complete role/company coverage, reconciliation/retention and production deployment remain unverified.
No real provider call, delivered email, release or Apps publication occurred.

### Native XLSX export

On 2026-10-10 in America/Vancouver, MAR-219 used unchanged runtime source
`5e9b7af3dcda9fbb087c0d3f141e5ac4a7d8ff2b` in fresh pinned Odoo
19.0-20260926 and 20.0-20260926 review fixtures. Initialization passed 51/50
native checks respectively and 12 MIME cases each; business/lifecycle checks
were not repeated. Regular Settings administrator uid 2 selected all 17 current
synthetic receipts in each native list, opened Actions → Export, kept the six
list fields and added Operation Key and Payload Hash. Import-compatible/updatable
fields stayed off. The selected format was XLSX on 19 and Excel Workbook (.xlsx)
on 20. Native list/dialog screenshots and DOM evidence were inspected and retained.

Each actual `/web/export/xlsx` POST returned HTTP 200 with an XLSX attachment.
An observational loopback relay retained the exact response bytes without changing
the native request or response. Every selected header and cell was compared with
an independently captured ORM snapshot in the exact requested record-ID order.
Created on uses the browser's America/Vancouver context and the installed native
Datetime export's second precision. Both workbooks contain all accepted/rejected/
unknown fixture rows, 17 unique operation hashes and 17 valid payload hashes.
Available/selected fields and workbook XML contain no credential, recipient-list
or body field; specific fixture credential, recipient, subject, body and attachment
markers are absent. This is a bounded fixture check, not a general DLP claim.

The same browser authenticated ordinary internal/export user uid 11 without
Settings administration. The native receipt page showed Access Error. A small
synthetic HTML form then posted known receipt ID 1 to the actual XLSX HTTP route
with that browser session and native CSRF token. Both versions returned HTTP 500
with AccessError, no attachment/workbook and no fixture receipt identifiers/hashes
or tested sensitive markers. This form tests the native route; it is not a native
export dialog available to the denied user. Before/after receipt snapshots agree.

The initial verifier retained a failed microsecond expectation; installed native
Datetime conversion establishes the second precision used by the corrected check.
Odoo 20's user-menu logout returned Method Not Allowed; its native login form
successfully switched identities, confirmed by native session information.
Owned tabs, observers, tunnels, containers, networks and volumes were removed.
Evidence and hashes are retained in the coordinated MAR-219 validation package.
No OS Downloads/file-save, complete role/company/accessibility, templates/grouped/
large export, provider, production/Odoo.sh, release or Apps acceptance is claimed.
