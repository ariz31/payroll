# Contributing to SiteGuard QR

Thank you for helping document and build the project. This repository is presently a **specification baseline**; do not claim to have tested an application until implementation/test evidence exists.

## Before opening a change

1. Read [README](README.md), [PRD](docs/product/PRD.md), [security/privacy](docs/engineering/SECURITY_PRIVACY.md) and [open decisions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md).
2. Link changes to requirement IDs (e.g., FR-011) and source sections; distinguish **required**, **proposed** and **implemented** behavior.
3. For payroll calculations, time interpretation, QR credential protocol, raw evidence schema, privacy/retention or approval routing, propose an ADR before changing the contract.

## Pull request expectations

- Small, reviewable scope, descriptive title and summary of affected requirements.
- Tests/fixtures for behavior; if docs-only, spellcheck links, examples, table headers and consistency.
- No production secrets, real employee images/records, passwords or signing key material.
- DB changes include migration/rollback discussion and evidence that raw journals and raw punch fields remain protected.
- API changes include an updated contract and generated OpenAPI once real routes exist.
- Any payroll export schema change preserves **v1 exactly** or introduces a separately versioned v2 with consumer migration.
- Before calling a feature “implemented”, provide source, test evidence, deployment support and known limitations.

## Code review checklist

- [ ] Requirements and source traceability updated
- [ ] Signed token/device auth and role boundaries preserved
- [ ] Immutable event ledger and write-once raw punch invariants protected
- [ ] Timezone, overnight and rounding cases tested
- [ ] Three-tier finalization and mandatory notes enforced
- [ ] CSV/XLSX remains 23-column v1 and hold logic works
- [ ] Sensitive image/data use and logging reviewed
- [ ] Documentation and changelog updated
- [ ] No “passing tests” or “production ready” claim without evidence

## Suggested commit conventions

`docs:` documentation improvements; `feat:` approved behavior; `fix:` regression fix; `test:` verification; `security:` security control; `chore:` maintenance. Breaking contract changes require explicit migration guidance.

## License and conduct

A license has **not** been selected. Do not assume publicly visible code/docs may be reused under a permissive license. Discuss code of conduct/governance with project owner if external contributions begin.
