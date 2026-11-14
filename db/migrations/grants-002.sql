GRANT SELECT, INSERT ON policy_versions, scan_audit, dynamic_uses, shifts TO {role};
GRANT SELECT, INSERT, UPDATE ON employees, badges, terminals TO {role};
GRANT SELECT, INSERT, DELETE ON assignments, scan_evidence TO {role};
GRANT SELECT, INSERT, UPDATE, DELETE ON profile_evidence TO {role};
GRANT DELETE ON dynamic_uses TO {role};
GRANT UPDATE (raw_in, raw_out, in_event, out_event, updated_at, version) ON shifts TO {role};
