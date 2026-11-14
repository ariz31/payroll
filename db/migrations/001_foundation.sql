CREATE TABLE organizations (
    id uuid PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    name text NOT NULL
);

CREATE TABLE sites (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id text NOT NULL,
    name text NOT NULL,
    timezone text NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    radius_m integer NOT NULL CHECK (radius_m BETWEEN 10 AND 50000),
    active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, id)
);

CREATE TABLE staff (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    login text NOT NULL,
    name text NOT NULL,
    password_hash text,
    role text NOT NULL CHECK (role IN ('admin', 'foreman', 'engineer', 'timekeeper', 'auditor', 'employee')),
    site_id text,
    scope_code text,
    employee_id text,
    active boolean NOT NULL DEFAULT true,
    UNIQUE (org_id, login),
    UNIQUE (org_id, id),
    FOREIGN KEY (org_id, site_id) REFERENCES sites(org_id, id),
    CHECK (role <> 'employee' OR employee_id IS NOT NULL),
    CHECK (role NOT IN ('foreman','engineer') OR site_id IS NOT NULL),
    CHECK (scope_code IS NULL OR role IN ('foreman','engineer'))
);

CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    staff_id uuid NOT NULL REFERENCES staff(id),
    expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_by_staff ON sessions(staff_id);
CREATE INDEX sessions_by_expiry ON sessions(expires_at);

CREATE TABLE attempt_limits (
    bucket text NOT NULL,
    window_start bigint NOT NULL,
    count integer NOT NULL,
    PRIMARY KEY (bucket, window_start)
);
CREATE INDEX attempt_limits_by_time ON attempt_limits(window_start);

CREATE TABLE control_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    actor_id uuid REFERENCES staff(id),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    action text NOT NULL,
    object_id text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX control_audit_by_org ON control_audit(org_id, id DESC);

CREATE FUNCTION forbid_evidence_edits() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Evidence in % is append-only', TG_TABLE_NAME USING ERRCODE = '23514';
END
$$;

CREATE TRIGGER control_audit_immutable
    BEFORE UPDATE OR DELETE OR TRUNCATE ON control_audit
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();
