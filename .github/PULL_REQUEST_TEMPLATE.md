## Summary

What changes, why, and to which source blueprint section / FR ID does it map?

## Scope

- [ ] Documentation only (do not label feature implemented)
- [ ] Application code with test evidence
- [ ] API or database contract
- [ ] Privacy/security/credential or payroll policy (ADR required)

## Audit-critical checklist

- [ ] Every raw scan attempt remains append-only
- [ ] Raw QR in/out values remain write-once and non-deletable
- [ ] Adjustments/rejections require authenticated timekeeper, notes and server timestamp
- [ ] Reviewer authorization/tier flow unchanged or documented
- [ ] Export v1 exact 23 headers, Verified-only payable and employee holds remain valid
- [ ] Timezone, cross-midnight and offline trust cases considered
- [ ] Sensitive photos/employee information not exposed in tests/logs
- [ ] Tests, docs, changelog and migrations updated as relevant

## Evidence

Tests run / screenshots (synthetic data only) / open decisions / rollback considerations:
