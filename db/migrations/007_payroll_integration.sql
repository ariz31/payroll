CREATE TABLE payroll_integrations (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    name text NOT NULL,
    site_id text,
    credential_hash text NOT NULL,
    created_by uuid NOT NULL REFERENCES staff(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    revoked_at timestamptz,
    FOREIGN KEY (org_id,site_id) REFERENCES sites(org_id,id)
);
CREATE INDEX integrations_by_org ON payroll_integrations(org_id,created_at DESC);
