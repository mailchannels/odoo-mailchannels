# Validation coverage

This is a development preview, not an Odoo Apps release. All provider requests in
these tests are mocked. No real account, delivered email or reply/bounce flow has
been validated.

`tests/run.py` builds and installs the same version-specific module a maintainer
would install. It uses digest-pinned Odoo 19 and 20 images (20260926 builds) and
PostgreSQL 16 on a Docker internal network with no published ports. Exact digests
are in the runner. It installs `mail` and `auth_signup`, exercises the native ORM
and mail queue through `odoo shell`, and removes the disposable resources.

Run both versions with full lifecycle coverage:

```sh
ODOO_TEST_VERSION=19.0 ODOO_LIFECYCLE_TESTS=1 ODOO_BUSINESS_TESTS=1 python3 tests/run.py
ODOO_TEST_VERSION=20.0 ODOO_LIFECYCLE_TESTS=1 ODOO_BUSINESS_TESTS=1 python3 tests/run.py
```

The suite includes 30 native checks on19 and29 on20: queue/session routing, recipient
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
Major-version migrations, arbitrary third-party uninstall hooks, complete browser role/export UI and
multi-company acceptance remain outside this coverage.

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
XLSX, export templates, grouped/paginated large exports, complete role/company
coverage, reconciliation/retention and production deployment remain unverified.
No real provider call, delivered email, release or Apps publication occurred.
