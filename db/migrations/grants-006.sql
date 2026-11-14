GRANT SELECT ON scan_reconciliations TO {role};
GRANT EXECUTE ON FUNCTION reconcile_scan(uuid,uuid,text,text,uuid) TO {role};
