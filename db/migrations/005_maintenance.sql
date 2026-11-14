CREATE FUNCTION purge_expired_evidence()
RETURNS TABLE(scan_images bigint, badge_images bigint) LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
BEGIN
    DELETE FROM public.scan_evidence WHERE expires_at <= clock_timestamp();
    GET DIAGNOSTICS scan_images = ROW_COUNT;
    DELETE FROM public.profile_evidence WHERE expires_at <= clock_timestamp();
    GET DIAGNOSTICS badge_images = ROW_COUNT;
    RETURN NEXT;
END
$$;
REVOKE ALL ON FUNCTION purge_expired_evidence() FROM PUBLIC;
