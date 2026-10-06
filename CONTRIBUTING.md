# Contributing

Use Docker on Linux and run both native suites in `docs/VALIDATION.md`. Keep all
provider calls mocked and use synthetic addresses/data only. Do not add a real API
key, customer database or email content to tests, commits or CI secrets.

Preserve native Odoo server selection and no-send mode, recipient privacy, and
receipt-based duplicate protection. Unknown outcomes must not cause blind retries
or SMTP fallback. Add regression coverage for changed transport behavior and
update the supported/unsupported scope in the README and release handoff.
