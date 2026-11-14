# Documentation index

**Status:** initial deployable **static preview** plus specification baseline (2026-11-14). The preview is **not** the full timekeeping application; all domain services remain unimplemented. **Authority:** supplied *SiteGuard QR — Complete Technical & Commercial Blueprint*, pp. 1–7. “Required” means required by that blueprint; “proposed” means a recommended design to implement; “open” means an unresolved decision. Avoid describing an unbuilt feature as live.

## Start here

| Audience | Reading order |
| --- | --- |
| Product owner | [PRD](product/PRD.md) → [Functional specification](specs/FUNCTIONAL_SPECIFICATION.md) → [Roadmap](product/ROADMAP.md) → [Open decisions](engineering/DECISIONS_AND_OPEN_QUESTIONS.md) |
| Backend engineer | [Architecture](architecture/SYSTEM_ARCHITECTURE.md) → [Business rules](specs/BUSINESS_RULES.md) → [Data model](architecture/DATA_MODEL.md) → [API](api/API_CONTRACT.md) → [Tests](engineering/TEST_PLAN.md) |
| Frontend engineer | [Functional specification](specs/FUNCTIONAL_SPECIFICATION.md) → [Workflow & roles](specs/WORKFLOW_AND_ROLES.md) → [QR/offline](specs/QR_SECURITY_AND_OFFLINE.md) → [API](api/API_CONTRACT.md) |
| Security / privacy reviewer | [Security & privacy](engineering/SECURITY_PRIVACY.md) → [QR/offline](specs/QR_SECURITY_AND_OFFLINE.md) → [Deployment](engineering/DEPLOYMENT_OPERATIONS.md) |
| Payroll integrator | [Export contract](specs/PAYROLL_EXPORT.md) → [Business rules](specs/BUSINESS_RULES.md) → [Tests](engineering/TEST_PLAN.md) |
| Operations / vendor | [Deployment & operations](engineering/DEPLOYMENT_OPERATIONS.md) → [Commercial overview](commercial/COMMERCIAL_OVERVIEW.md) |

## Document register

- **Product:** [PRD](product/PRD.md), [Roadmap](product/ROADMAP.md).
- **Design:** [System architecture](architecture/SYSTEM_ARCHITECTURE.md), [Data model](architecture/DATA_MODEL.md).
- **Normative feature requirements:** [Functional specification](specs/FUNCTIONAL_SPECIFICATION.md), [Business rules](specs/BUSINESS_RULES.md), [QR and offline](specs/QR_SECURITY_AND_OFFLINE.md), [Workflow](specs/WORKFLOW_AND_ROLES.md), [Payroll export](specs/PAYROLL_EXPORT.md).
- **Proposed interfaces:** [REST API](api/API_CONTRACT.md).
- **Engineering:** [Development](engineering/DEVELOPMENT.md), [Vercel preview deploy](engineering/VERCEL_DEPLOYMENT.md), [Operations](engineering/DEPLOYMENT_OPERATIONS.md), [Security/privacy](engineering/SECURITY_PRIVACY.md), [Tests](engineering/TEST_PLAN.md), [Decisions](engineering/DECISIONS_AND_OPEN_QUESTIONS.md).
- **Business context:** [Commercial overview](commercial/COMMERCIAL_OVERVIEW.md).
- **Governance:** [Contributing](../CONTRIBUTING.md), [Security reporting](../SECURITY.md), [Changelog](../CHANGELOG.md).

## Requirement traceability

| Source section | Main docs |
| --- | --- |
| §1 Architecture and immutable captures | Architecture, Data model, Security |
| §2 Configuration defaults | Business rules, Functional spec |
| §3 Badge, kiosk, pairing, anomaly computation | QR/offline, Business rules |
| §4 Three-tier approvals | Workflow, Data model |
| §5 23-column handoff and gating | Payroll export |
| §6 Six reference cases | Test plan |
| §7 Pricing and GTM | Commercial overview |

## Documentation change rules

1. Preserve the **exact** 23 export column names/order, unless the owner explicitly approves a versioned new schema.
2. Never relax the immutable raw-evidence / non-destructive adjustment invariant.
3. Mark hypothetical endpoints, tables, environment variables, CLI commands and hosting topology as **proposed** until implemented and tested.
4. Update tests, traceability, API contract and change log whenever a norm changes.
5. Record source ambiguities and decisions in [Decisions](engineering/DECISIONS_AND_OPEN_QUESTIONS.md); do not silently assume a legal payroll interpretation.
