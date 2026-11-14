CREATE TABLE oidc_links (
    org_id uuid NOT NULL,
    staff_id uuid NOT NULL,
    issuer text NOT NULL,
    subject text NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (org_id,issuer,subject),
    UNIQUE (staff_id,issuer),
    FOREIGN KEY (org_id,staff_id) REFERENCES staff(org_id,id)
);
