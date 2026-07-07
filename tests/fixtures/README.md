# Test Fixture Policy

Only synthetic or fully sanitized files may be committed under `tests/fixtures/`.

Keep structure, not identity:

- Do not commit real customer names.
- Do not commit real email addresses.
- Do not commit real addresses.
- Do not commit real order numbers, Tan numbers, invoice numbers, payment details, or mailbox exports.
- Do not commit generated production outputs.

Use synthetic workbooks for rule tests, and use a small number of sanitized fixtures only when structure matters. Real business files are for local manual verification only.
