CREATE TABLE scan_reconciliations (
    event_id uuid PRIMARY KEY REFERENCES scan_audit(id),
    org_id uuid NOT NULL REFERENCES organizations(id),
    actor_id uuid NOT NULL REFERENCES staff(id),
    actor_login text NOT NULL,
    shift_id uuid REFERENCES shifts(id),
    disposition text NOT NULL CHECK (disposition IN ('dismissed','linked_for_review')),
    notes text NOT NULL CHECK (length(btrim(notes)) BETWEEN 1 AND 1500),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((disposition = 'linked_for_review') = (shift_id IS NOT NULL))
);
CREATE TRIGGER scan_reconciliation_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON scan_reconciliations
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_evidence_edits();

CREATE FUNCTION reconcile_scan(target uuid, actor uuid, decision text, reason text, shift_target uuid)
RETURNS public.scan_reconciliations
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    evt public.scan_audit%ROWTYPE;
    u public.staff%ROWTYPE;
    linked public.shifts%ROWTYPE;
    saved public.scan_reconciliations%ROWTYPE;
BEGIN
    SELECT * INTO evt FROM public.scan_audit WHERE id=target AND result='QUARANTINED';
    SELECT * INTO u FROM public.staff WHERE id=actor AND org_id=evt.org_id AND active
        AND role='timekeeper' AND (site_id IS NULL OR site_id=evt.site_id);
    IF u.id IS NULL THEN
        RAISE EXCEPTION 'Quarantined scan is outside the reviewer scope' USING ERRCODE='42501';
    END IF;
    SELECT * INTO saved FROM public.scan_reconciliations WHERE event_id=target;
    IF saved.event_id IS NOT NULL THEN
        IF ROW(saved.actor_id,saved.disposition,saved.notes,saved.shift_id)
           IS DISTINCT FROM ROW(actor,decision,btrim(reason),shift_target) THEN
            RAISE EXCEPTION 'This scan already has a reconciliation decision' USING ERRCODE='40001';
        END IF;
        RETURN saved;
    END IF;
    IF decision='linked_for_review' THEN
        SELECT * INTO linked FROM public.shifts WHERE id=shift_target AND org_id=evt.org_id
            AND site_id=evt.site_id AND stage IN ('foreman','engineer','timekeeper')
            AND (evt.employee_id IS NULL OR employee_id=evt.employee_id)
            AND (evt.work_date IS NULL OR work_date=evt.work_date);
        IF linked.id IS NULL THEN
            RAISE EXCEPTION 'Link an in-scope pending shift for the same employee and work date'
                USING ERRCODE='23514';
        END IF;
    END IF;
    INSERT INTO public.scan_reconciliations(event_id,org_id,actor_id,actor_login,shift_id,disposition,notes)
    VALUES (target, evt.org_id, actor, u.login, shift_target, decision, btrim(reason))
    ON CONFLICT (event_id) DO NOTHING RETURNING * INTO saved;
    IF saved.event_id IS NULL THEN
        SELECT * INTO saved FROM public.scan_reconciliations WHERE event_id=target;
        IF ROW(saved.actor_id,saved.disposition,saved.notes,saved.shift_id)
           IS DISTINCT FROM ROW(actor,decision,btrim(reason),shift_target) THEN
            RAISE EXCEPTION 'This scan already has a reconciliation decision' USING ERRCODE='40001';
        END IF;
    END IF;
    RETURN saved;
END
$$;
REVOKE ALL ON FUNCTION reconcile_scan(uuid,uuid,text,text,uuid) FROM PUBLIC;
