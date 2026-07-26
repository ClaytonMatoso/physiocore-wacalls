# Phase 0 — WaCalls characterization evidence

This branch does not redesign WaCalls and must not be deployed as a product release. It pins and records the behavior of source commit `2ce896ad31fe2915ef0d599c83c62dc966eda7b9` so the PhysioCore Academy migration can distinguish intentional changes from regressions.

## Evidence produced

The workflow `Phase 0 WaCalls Characterization` verifies:

- the legacy Go packages compile and pass focused offline tests;
- authentication currently uses one active opaque token per user and stores that token verbatim;
- expired and rotated tokens are rejected;
- message upsert preserves downloaded/uploaded media metadata;
- message identity is scoped by `(session_id, message_id)`;
- session records preserve owner and generated integration-token behavior, including legacy unowned rows;
- the normal HTTP API defaults to same-origin CORS while the SSE path currently emits a wildcard header;
- the storage abstraction defaults to single-writer SQLite in WAL mode and rejects MySQL/MariaDB;
- the React application still builds from its lockfile;
- every source file in the immutable pre-audit commit is inventoried with SHA-256, size, module, migration decision and target location;
- Go and npm dependency trees are captured for the license and supply-chain review.

## Deliberate limitations

- Tests never connect to a real WhatsApp account and never scan a QR Code.
- No real token, session, message, phone number, media or customer data is used.
- WhatsApp network behavior will be validated later in an isolated homologation environment with dedicated test numbers.
- Passing characterization tests means the observed legacy behavior was recorded; it does not mean that behavior is safe or approved for the Academy Platform.

## Artifact names

The workflow uploads `phase0-wacalls-evidence`, containing:

- `wacalls-file-inventory.csv`;
- `wacalls-inventory-summary.json`;
- `wacalls-frontend-characterization.json`;
- `wacalls-go-modules.json`;
- `wacalls-npm-tree.json`;
- `wacalls-source-snapshot.txt`.

The private Academy repository consumes these outputs as audit evidence. The inventory is generated from the pinned commit, not from the audit branch, so audit-only files cannot contaminate the baseline.
