CREATE TABLE policy_versions (
    org_id uuid NOT NULL REFERENCES organizations(id),
    version integer NOT NULL,
    settings jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (org_id, version)
);
CREATE TRIGGER policy_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON policy_versions
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();

ALTER TABLE sites ADD COLUMN evidence_mode text NOT NULL DEFAULT 'off'
    CHECK (evidence_mode IN ('off','optional','required'));
ALTER TABLE sites ADD COLUMN evidence_notice text NOT NULL DEFAULT '';
ALTER TABLE sites ADD COLUMN evidence_days integer NOT NULL DEFAULT 30 CHECK (evidence_days BETWEEN 1 AND 90);

CREATE TABLE employees (
    org_id uuid NOT NULL REFERENCES organizations(id),
    id text NOT NULL,
    name text NOT NULL,
    department text NOT NULL,
    cost_code text NOT NULL,
    crew text NOT NULL,
    shift_type text NOT NULL CHECK (shift_type IN ('Day Shift','Night Shift')),
    active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, id)
);
CREATE TABLE assignments (
    org_id uuid NOT NULL,
    employee_id text NOT NULL,
    site_id text NOT NULL,
    PRIMARY KEY (org_id, employee_id, site_id),
    FOREIGN KEY (org_id, employee_id) REFERENCES employees(org_id,id),
    FOREIGN KEY (org_id, site_id) REFERENCES sites(org_id,id)
);
ALTER TABLE staff ADD CONSTRAINT staff_employee
    FOREIGN KEY (org_id, employee_id) REFERENCES employees(org_id,id);

CREATE TABLE badges (
    org_id uuid NOT NULL,
    id uuid NOT NULL,
    employee_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('DYN','STC')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    revoked_at timestamptz,
    PRIMARY KEY (org_id,id),
    FOREIGN KEY (org_id, employee_id) REFERENCES employees(org_id,id)
);
CREATE UNIQUE INDEX badge_active_mode ON badges(org_id,employee_id,mode) WHERE revoked_at IS NULL;

CREATE TABLE terminals (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    code text NOT NULL,
    name text NOT NULL,
    site_id text NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    active boolean NOT NULL DEFAULT true,
    credential_hash text NOT NULL,
    generation integer NOT NULL DEFAULT 1,
    last_sequence bigint NOT NULL DEFAULT 0,
    last_hash text NOT NULL DEFAULT '',
    UNIQUE (org_id,code),
    FOREIGN KEY (org_id,site_id) REFERENCES sites(org_id,id)
);

CREATE TABLE shifts (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    employee_id text NOT NULL,
    site_id text NOT NULL,
    work_date date NOT NULL,
    timezone text NOT NULL,
    name text NOT NULL,
    department text NOT NULL,
    cost_code text NOT NULL,
    crew text NOT NULL,
    shift_type text NOT NULL CHECK (shift_type IN ('Day Shift','Night Shift')),
    policy_version integer NOT NULL,
    raw_in timestamptz,
    raw_out timestamptz,
    in_event uuid,
    out_event uuid,
    terminal_code text NOT NULL,
    adjusted_in timestamptz,
    adjusted_out timestamptz,
    stage text NOT NULL DEFAULT 'foreman' CHECK (stage IN ('foreman','engineer','timekeeper','verified','disputed')),
    verified_by text,
    verified_at timestamptz,
    notes text,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (org_id,employee_id,work_date),
    FOREIGN KEY (org_id,employee_id) REFERENCES employees(org_id,id),
    FOREIGN KEY (org_id,site_id) REFERENCES sites(org_id,id),
    CHECK ((raw_in IS NULL) = (in_event IS NULL) AND (raw_out IS NULL) = (out_event IS NULL)),
    CHECK (COALESCE(adjusted_out,raw_out) > COALESCE(adjusted_in,raw_in)),
    CHECK (COALESCE(adjusted_out,raw_out) - COALESCE(adjusted_in,raw_in) < interval '24 hours'),
    CHECK ((adjusted_in IS NULL AND adjusted_out IS NULL AND stage NOT IN ('verified','disputed'))
        OR (COALESCE(length(btrim(notes)),0) > 0 AND verified_by IS NOT NULL AND verified_at IS NOT NULL))
);
CREATE INDEX shifts_by_scope ON shifts(org_id,site_id,work_date);
CREATE INDEX shifts_by_work_date ON shifts(org_id,work_date,employee_id);

CREATE TABLE scan_audit (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    terminal_id uuid NOT NULL REFERENCES terminals(id),
    terminal_code text NOT NULL,
    site_id text NOT NULL,
    employee_id text,
    client_event_id uuid NOT NULL,
    generation integer NOT NULL,
    sequence bigint,
    event_hash text NOT NULL,
    qr_digest text NOT NULL,
    received_at timestamptz NOT NULL,
    reported_at timestamptz NOT NULL,
    effective_at timestamptz,
    latitude double precision,
    longitude double precision,
    accuracy_m double precision,
    result text NOT NULL,
    reason text NOT NULL,
    shift_id uuid REFERENCES shifts(id) DEFERRABLE INITIALLY DEFERRED,
    work_date date,
    chain_advanced boolean NOT NULL,
    material_hash text,
    UNIQUE (terminal_id,client_event_id),
    UNIQUE (terminal_id,generation,sequence)
);
CREATE INDEX audit_by_scope ON scan_audit(org_id,site_id,received_at DESC);
CREATE INDEX audit_by_terminal ON scan_audit(terminal_id,received_at DESC);
CREATE INDEX audit_by_employee ON scan_audit(org_id,employee_id,effective_at DESC)
    WHERE result IN ('ACCEPTED_IN','ACCEPTED_OUT');
ALTER TABLE shifts ADD FOREIGN KEY (in_event) REFERENCES scan_audit(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE shifts ADD FOREIGN KEY (out_event) REFERENCES scan_audit(id) DEFERRABLE INITIALLY DEFERRED;
CREATE TRIGGER scan_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON scan_audit
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();

CREATE TABLE dynamic_uses (
    org_id uuid NOT NULL,
    badge_id uuid NOT NULL,
    step bigint NOT NULL,
    PRIMARY KEY (org_id,badge_id,step),
    FOREIGN KEY (org_id,badge_id) REFERENCES badges(org_id,id)
);

CREATE TABLE scan_evidence (
    event_id uuid PRIMARY KEY REFERENCES scan_audit(id),
    sealed bytea NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE TABLE profile_evidence (
    org_id uuid NOT NULL,
    employee_id text NOT NULL,
    sealed bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (org_id,employee_id),
    FOREIGN KEY (org_id,employee_id) REFERENCES employees(org_id,id)
);

CREATE FUNCTION protect_shift_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(OLD.id, OLD.org_id, OLD.employee_id, OLD.site_id, OLD.work_date, OLD.timezone,
           OLD.name, OLD.department, OLD.cost_code, OLD.crew, OLD.shift_type, OLD.terminal_code)
       IS DISTINCT FROM
       ROW(NEW.id, NEW.org_id, NEW.employee_id, NEW.site_id, NEW.work_date, NEW.timezone,
           NEW.name, NEW.department, NEW.cost_code, NEW.crew, NEW.shift_type, NEW.terminal_code)
       OR (OLD.raw_in IS NOT NULL AND ROW(NEW.raw_in, NEW.in_event) IS DISTINCT FROM ROW(OLD.raw_in, OLD.in_event))
       OR (OLD.raw_out IS NOT NULL AND ROW(NEW.raw_out, NEW.out_event) IS DISTINCT FROM ROW(OLD.raw_out, OLD.out_event))
    THEN
        RAISE EXCEPTION 'Raw shift evidence is write-once' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER shift_identity BEFORE UPDATE ON shifts FOR EACH ROW EXECUTE FUNCTION protect_shift_identity();
CREATE TRIGGER shift_no_delete BEFORE DELETE OR TRUNCATE ON shifts
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();

CREATE FUNCTION confirm_raw_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.in_event IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM scan_audit WHERE id=NEW.in_event AND org_id=NEW.org_id AND employee_id=NEW.employee_id
        AND shift_id=NEW.id AND result='ACCEPTED_IN' AND effective_at=NEW.raw_in))
    OR (NEW.out_event IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM scan_audit WHERE id=NEW.out_event AND org_id=NEW.org_id AND employee_id=NEW.employee_id
        AND shift_id=NEW.id AND result='ACCEPTED_OUT' AND effective_at=NEW.raw_out)) THEN
        RAISE EXCEPTION 'A raw punch must reference an accepted scan' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER raw_evidence_fk AFTER INSERT OR UPDATE ON shifts
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION confirm_raw_evidence();
