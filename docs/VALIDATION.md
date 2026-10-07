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
ODOO_TEST_VERSION=19.0 ODOO_LIFECYCLE_TESTS=1 python3 tests/run.py
ODOO_TEST_VERSION=20.0 ODOO_LIFECYCLE_TESTS=1 python3 tests/run.py
```

The suite includes 30 native checks on19 and29 on20: queue/session routing, recipient
and attachment mapping, native no-send mode, accepted replay, rollback and worker
failure protection, overlapping recipient rejection, concurrent submissions,
sanitized failures, separate configuration dry-run, real password-reset template
and token ownership, and non-superuser ORM/export/method access controls.
Malformed Base64 and duplicate Subject are tested through native `send_email`:
both fail without an HTTP request or submission receipt.

Nine MIME tests cover valid folded Base64; corrupted Base64 bodies/attachments;
unknown transfer encoding; duplicate identity and MIME headers; missing multipart
boundaries; unsupported signed MIME; and Unicode/ISO-8859-1 text, HTML and inline
binary Content-ID preservation. These are not an exhaustive MIME validator.

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
states. This does not validate every browser role, export UI, every business flow,
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
