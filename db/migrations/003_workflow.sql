CREATE TABLE approval_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    shift_id uuid NOT NULL REFERENCES shifts(id),
    actor_id uuid REFERENCES staff(id),
    actor_name text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    request_id uuid NOT NULL,
    action text NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    before_state jsonb NOT NULL,
    after_state jsonb NOT NULL,
    request_digest text NOT NULL,
    UNIQUE (shift_id,request_id)
);
CREATE INDEX approval_by_scope ON approval_audit(org_id,shift_id,id DESC);
CREATE TRIGGER approval_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON approval_audit
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();

CREATE TABLE payroll_exports (
    id uuid PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES organizations(id),
    site_id text,
    period text NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    revision integer NOT NULL,
    format text NOT NULL CHECK (format IN ('csv','xlsx')),
    actor_id uuid NOT NULL REFERENCES staff(id),
    actor_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    digest text NOT NULL,
    signed_receipt text NOT NULL,
    snapshot jsonb NOT NULL,
    artifact bytea NOT NULL,
    UNIQUE (org_id,period,revision)
);
ALTER TABLE payroll_exports ADD FOREIGN KEY (org_id,site_id) REFERENCES sites(org_id,id);
CREATE INDEX payroll_exports_by_org ON payroll_exports(org_id,period,revision DESC);
CREATE TRIGGER payroll_exports_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON payroll_exports
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();

CREATE FUNCTION review_shift(
    target uuid, actor uuid, request uuid, expected_version integer, decision text, reason text,
    adjustment_in timestamptz, adjustment_out timestamptz, digest text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE
    s public.shifts%ROWTYPE;
    u public.staff%ROWTYPE;
    existing public.approval_audit%ROWTYPE;
    previous jsonb;
    next_stage text;
    setting jsonb;
    current_in timestamptz;
    current_out timestamptz;
    start_at timestamptz;
    end_at timestamptz;
    clean boolean := false;
BEGIN
    SELECT * INTO STRICT s FROM public.shifts WHERE id=target FOR UPDATE;
    IF actor IS NOT NULL THEN
        SELECT * INTO u FROM public.staff WHERE id=actor AND org_id=s.org_id AND active;
        IF u.id IS NULL OR (u.site_id IS NOT NULL AND u.site_id<>s.site_id)
           OR (u.role='foreman' AND u.scope_code IS NOT NULL AND u.scope_code<>s.crew)
           OR (u.role='engineer' AND u.scope_code IS NOT NULL AND u.scope_code<>s.cost_code) THEN
            RAISE EXCEPTION 'Reviewer is out of scope' USING ERRCODE='42501';
        END IF;
    END IF;
    SELECT * INTO existing FROM public.approval_audit WHERE shift_id=target AND request_id=request;
    IF existing.id IS NOT NULL THEN
        IF existing.actor_id IS DISTINCT FROM actor OR existing.request_digest <> digest THEN
            RAISE EXCEPTION 'Review request conflicts with earlier action' USING ERRCODE='40001';
        END IF;
        RETURN s.version;
    END IF;
    IF s.version<>expected_version THEN
        RAISE EXCEPTION 'Shift version changed' USING ERRCODE='40001';
    END IF;
    IF length(btrim(coalesce(reason,''))) < 1 THEN
        RAISE EXCEPTION 'Review requires a reason' USING ERRCODE='23514';
    END IF;

    SELECT settings INTO setting FROM public.policy_versions WHERE org_id=s.org_id AND version=s.policy_version;
    start_at := (s.work_date + COALESCE((setting->>CASE WHEN s.shift_type='Day Shift' THEN
        'day_start' ELSE 'night_start' END)::time, CASE WHEN s.shift_type='Day Shift' THEN time '08:00' ELSE time '22:00' END))
        AT TIME ZONE s.timezone;
    end_at := (s.work_date + CASE WHEN s.shift_type='Night Shift' THEN 1 ELSE 0 END
        + COALESCE((setting->>CASE WHEN s.shift_type='Day Shift' THEN 'day_end' ELSE 'night_end' END)::time,
            CASE WHEN s.shift_type='Day Shift' THEN time '17:00' ELSE time '07:00' END))
        AT TIME ZONE s.timezone;
    IF s.raw_in IS NOT NULL AND s.raw_out IS NOT NULL THEN
        clean := (s.shift_type='Night Shift' OR s.raw_in <= start_at + make_interval(
            mins=>COALESCE((setting->>'late_grace_minutes')::integer,5)))
            AND EXTRACT(epoch FROM s.raw_out-s.raw_in)/3600
                - COALESCE((setting->>'break_mins')::numeric,60)/60
                - COALESCE((setting->>'regular_hours')::numeric,8) <= COALESCE((setting->>'high_ot_hours')::numeric,2);
    END IF;

    next_stage := CASE
        WHEN decision='endorse' AND u.role='foreman' AND s.stage='foreman'
            AND (s.raw_out IS NOT NULL OR clock_timestamp() >= end_at + make_interval(
                 mins=>COALESCE((setting->>'missing_out_grace_minutes')::integer,60))) THEN 'engineer'
        WHEN decision='request_evidence' AND u.role='foreman' AND s.stage='foreman' THEN 'foreman'
        WHEN decision IN ('cost_approve','cost_reject') AND u.role='engineer' AND s.stage='engineer' THEN 'timekeeper'
        WHEN decision='return_foreman' AND u.role='engineer' AND s.stage='engineer' THEN 'foreman'
        WHEN decision='return_engineer' AND u.role='timekeeper' AND s.stage='timekeeper' THEN 'engineer'
        WHEN decision='verify' AND u.role='timekeeper' AND s.stage='timekeeper' THEN 'verified'
        WHEN decision='reject' AND u.role='timekeeper' AND s.stage='timekeeper' THEN 'disputed'
        WHEN decision='bulk_verify' AND u.role='timekeeper' AND s.stage='foreman' AND clean THEN 'verified'
        WHEN decision='auto_verify' AND actor IS NULL AND s.stage='foreman' AND clean
            AND COALESCE((setting->>'auto_verify_ok_scans')::boolean,false)
            AND NOT EXISTS (SELECT 1 FROM public.approval_audit WHERE shift_id=target)
            THEN 'verified'
        WHEN decision='reopen' AND u.role='timekeeper' AND s.stage IN ('verified','disputed') THEN 'foreman'
        WHEN decision='policy_changed' AND u.role='admin' AND u.site_id IS NULL
            AND s.stage IN ('foreman','engineer','timekeeper') THEN 'foreman'
        ELSE NULL END;
    IF next_stage IS NULL THEN
        RAISE EXCEPTION 'Review transition not permitted' USING ERRCODE='23514';
    END IF;
    IF (adjustment_in IS NOT NULL OR adjustment_out IS NOT NULL) AND decision NOT IN ('verify','reject') THEN
        RAISE EXCEPTION 'Only final timekeeper review can adjust a punch' USING ERRCODE='23514';
    END IF;
    current_in := COALESCE(adjustment_in,s.raw_in);
    current_out := COALESCE(adjustment_out,s.raw_out);
    IF next_stage='verified' AND (current_in IS NULL OR current_out IS NULL) THEN
        RAISE EXCEPTION 'Verification requires a complete effective pair' USING ERRCODE='23514';
    END IF;
    IF current_in IS NOT NULL AND current_out IS NOT NULL AND
       (current_out<=current_in OR current_out-current_in>=interval '24 hours') THEN
        RAISE EXCEPTION 'Effective time pair is outside the allowed range' USING ERRCODE='23514';
    END IF;

    previous := to_jsonb(s);
    UPDATE public.shifts SET stage=next_stage,
        adjusted_in=adjustment_in, adjusted_out=adjustment_out,
        verified_by=CASE WHEN next_stage IN ('verified','disputed') THEN COALESCE(u.login,'system') END,
        verified_at=CASE WHEN next_stage IN ('verified','disputed') THEN clock_timestamp() END,
        notes=CASE WHEN next_stage IN ('verified','disputed') THEN btrim(reason) END,
        policy_version=CASE WHEN decision='policy_changed' THEN (SELECT max(version) FROM public.policy_versions
            WHERE org_id=s.org_id) ELSE s.policy_version END,
        version=version+1,updated_at=clock_timestamp() WHERE id=target RETURNING * INTO s;
    INSERT INTO public.approval_audit (org_id,shift_id,actor_id,actor_name,request_id,action,reason,before_state,after_state,request_digest)
    VALUES (s.org_id,s.id,actor,COALESCE(u.login,'system'),request,decision,btrim(reason),previous,to_jsonb(s),digest);
    RETURN s.version;
END
$$;
REVOKE ALL ON FUNCTION review_shift(uuid,uuid,uuid,integer,text,text,timestamptz,timestamptz,text) FROM PUBLIC;
