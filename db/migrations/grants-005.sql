REVOKE INSERT ON shifts FROM {role};
GRANT INSERT (id,org_id,employee_id,site_id,work_date,timezone,name,department,cost_code,crew,
    shift_type,policy_version,terminal_code,raw_in,in_event,raw_out,out_event) ON shifts TO {role};
REVOKE DELETE ON scan_evidence, profile_evidence FROM {role};
GRANT EXECUTE ON FUNCTION purge_expired_evidence() TO {role};
