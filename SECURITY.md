# Security policy

**Project status:** documentation only. There is not yet a running application, a deployed endpoint or a supported release.

## Reporting a vulnerability

If/when an application is published, **do not post working exploits, credentials, QR signing keys, employee attendance data or gate camera images in public issues**. Prefer GitHub's **private vulnerability reporting** option on the repository's Security tab if the owner enables it. If it is not enabled, request a private reporting channel from the repository maintainer without disclosing exploit details.

No security response email, SLA, bounty program or vulnerability disclosure safe-harbor terms have been designated. Do not invent or assume any.

## Priorities for future implementation

- Badge signing/replay protection and terminal enrollment
- Offline clock trust and integrity
- Immutable scan evidence and raw punch DB triggers
- Reviewer RBAC/segregation of duties
- Protection of gate images and exported employee records
- Dependency security, key rotation, audit trails and recovery

See [Security and privacy design requirements](docs/engineering/SECURITY_PRIVACY.md) and [Open decisions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md).

## Supported versions

None. A version support matrix and vulnerability response process must be published before public production use.
