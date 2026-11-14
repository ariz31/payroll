GRANT SELECT ON approval_audit TO {role};
GRANT EXECUTE ON FUNCTION review_shift(uuid,uuid,uuid,integer,text,text,timestamptz,timestamptz,text) TO {role};
GRANT SELECT, INSERT ON payroll_exports TO {role};
