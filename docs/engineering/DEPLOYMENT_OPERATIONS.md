# Deployment and operations runbook (pre-implementation)

**Status:** planned controls; **no deployable system or verified commands exist yet**. Use this as an operational readiness specification.

## 1. Target environments

| Environment | Purpose | Data |
| --- | --- | --- |
| Local | Developer integration with fixture badges/sites | Synthetic only |
| Test/CI | Automated contract, security and migration tests | Synthetic/obfuscated |
| Staging | Full flow / realistic hardware and recovery rehearsal | Synthetic or specifically approved de-identified |
| Production | Audited attendance and handoff | Real data only after privacy, policy and security sign-off |

The commercial blueprint also mentions **private cloud/on-premise** for enterprise/government customers. Hosting topology, regional residency, network segmentation, SSO and disaster recovery infrastructure must be designed per buyer.

## 2. Proposed deployment topology

- TLS reverse proxy / API gateway → FastAPI stateless workers, authenticated kiosk and workbench.
- Isolated PostgreSQL 16, with separate migration/admin role and least-privileged application role; encrypted backups.
- Secure object store for optional gate snapshots with tightly scoped signed access and retention policies.
- Managed key store for badge keys, device credentials, at-rest encryption and rotation.
- Queue/outbox reconciliation workers if required; absence of network must not mean silent scan loss.
- Audit/metrics logs collected centrally with restricted read/write access and defined retention.

This layout is illustrative, not a choice of cloud service or actual architecture.

## 3. Configuration requirements

| Setting | Example semantics | Never default blindly |
| --- | --- | --- |
| Site timezone | IANA zone, e.g., `Asia/Manila` | Assuming server UTC/local timezone |
| Geofence | Site center + radius in meters | Arbitrary radius or spoofable location |
| Shift templates | 08:00–17:00 and 22:00–07:00 | Applying same rules to every contract |
| Debounce | 300s | Removing raw duplicate attempts |
| QR window | 30s and ±1 drift | Disabling replay checks |
| Review policy | `auto_verify_ok_scans = false` | Auto-approving exceptions |
| Secrets | Managed key references | Keys in .env committed to Git |
| Offline time policy | Max age, clock skew, attestation | Accepting stale tokens blindly |
| Image retention | Approved role/purpose/duration | Indefinite staff-photo storage |
| Export recipients | Authorized timekeepers/payroll only | Public URLs/email attachments |

Use config versions, actor, effective date and audit events. Secrets should never be returned from generic config reads.

## 4. Production readiness gates

- [ ] Threat model signed off; QR strength and static cloning risk assessed.
- [ ] Employee/site/org scope and reviewer permissions tested against horizontal and vertical escalation.
- [ ] Database triggers/grants block raw modification and audit deletion, even in concurrent and retry cases.
- [ ] Database/PITR restore rehearsal with corruption and rollback; immutable history preserved.
- [ ] Auth and signing keys rotated with overlapping validation policy; revoked badges invalidated.
- [ ] Device inventory, kiosk recovery, time drift, offline backlog and storage exhaustion tested.
- [ ] Ingestion latency and throughput measured on actual rugged kiosk hardware.
- [ ] Monitoring, on-call ownership and incident severity/runbooks defined.
- [ ] Gate camera notice, lawful basis, retention, employee rights and processor arrangements approved.
- [ ] Golden CSV/XLSX, pending/hold rules and payroll consumer import verified.
- [ ] Government Form 48 formatting/required signatories confirmed if enabled.
- [ ] No test tokens, default passwords, customer data or unredacted images in repository/logs.

## 5. Monitoring and alert targets (proposed)

| Signal | Interpretation / response |
| --- | --- |
| scan ingestion failed or DB timeout | Stop claiming “recorded”; retry idempotently |
| offline outbox depth/oldest age | Investigate network/device, protect from storage overflow |
| device clock skew / sequence gap | Quarantine affected events, require supervision |
| invalid signature and replay spike | Investigate abuse, check badge/device compromise |
| geofence mismatch spike | Review site GPS accuracy/spoofing/terminal relocation |
| raw trigger protection rejection | Security incident or code defect |
| exception backlog/aging | Escalate pending tier approvals before pay period cutoff |
| export row count/hold mismatch | Block payroll release and reconcile |
| photo access unusual activity | Investigate least-privilege breach |
| backup/PITR failure | Escalate data integrity risk |

**SLOs, RPO, RTO and alert numerical thresholds are unapproved**. Establish them during pilot readiness; blueprint only suggests sub-second kiosk feedback as design goal.

## 6. Routine operations (planned)

- **Daily:** device connectivity, outbox backlog, clock drift, failed scans, reviewer queue and backup health.
- **Before period close:** outstanding Missing Out/late/high OT queue; foreman/engineer/timekeeper sign-offs; status, verified totals and hold employee list.
- **At export:** show pending counts, save immutable export receipt/checksum, verify role, restrict file access, document secure delivery and confirm downstream HOLD enforcement.
- **After export:** preserve versioned historical snapshot; corrections create revised export and reconciliation record.
- **Periodic:** review access logs, revoke leavers’ badges and terminals, rotate credentials, test restores, review photo retention and secure deletion policies.

## 7. Incident playbooks (to implement)

**Clock skew / offline tampering:** isolate terminal, preserve local event chain and server journal, stop silent ingestion, reconcile with physical controls, document decisions and approved overrides.

**Unauthorized raw update:** trigger blocks, alert, preserve DB logs and forensic chain, review grants and affected ledger sequence; do not modify raw data during remediation.

**Payroll mismatch:** suspend handoff/release, compare period export receipt against verified-only sums and hold list, create corrected export revision after audited re-review.

**Credential exposure:** revoke device/badge keys, rotate safely, review replay windows and affected records, notify stakeholders under incident response policy.

**Sensitive image breach:** revoke access, preserve access audit, assess notification duties and apply approved incident response process. Specific legal deadlines must be determined by counsel.

## 8. Backup and data lifecycle

Append-only business immutability does not mean data can never be deleted under all legal circumstances. Determine statutory retention, legal holds, recovery targets, deletion workflow and audit-preserving archival design before deployment. Production backup encryption, access-control testing and actual restore tests are mandatory.
