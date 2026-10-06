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

The suite includes 26 native checks per version: queue/session routing, recipient
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
Major-version migrations, arbitrary third-party uninstall hooks, browser/RPC and
multi-company acceptance remain outside this coverage.

See [publishing requirements](PUBLISHING.md) for the remaining release gates.
