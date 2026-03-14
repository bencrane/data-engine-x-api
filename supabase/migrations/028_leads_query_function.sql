-- 028_leads_query_function.sql
-- Postgres function for the leads query endpoint.
-- Joins person_entities + entity_relationships + company_entities into a flat lead shape.

CREATE OR REPLACE FUNCTION entities.query_leads(
    p_org_id UUID,
    -- Company filters
    p_industry TEXT DEFAULT NULL,
    p_employee_range TEXT DEFAULT NULL,
    p_hq_country TEXT DEFAULT NULL,
    p_canonical_domain TEXT DEFAULT NULL,
    p_company_name TEXT DEFAULT NULL,
    -- Person filters
    p_title TEXT DEFAULT NULL,
    p_seniority TEXT DEFAULT NULL,
    p_department TEXT DEFAULT NULL,
    p_email_status TEXT DEFAULT NULL,
    p_has_email BOOLEAN DEFAULT NULL,
    p_has_phone BOOLEAN DEFAULT NULL,
    -- Pagination
    p_limit INT DEFAULT 25,
    p_offset INT DEFAULT 0
)
RETURNS SETOF JSON
LANGUAGE sql
STABLE
AS $$
    SELECT json_build_object(
        'person_entity_id', pe.entity_id,
        'full_name', pe.full_name,
        'first_name', pe.first_name,
        'last_name', pe.last_name,
        'linkedin_url', pe.linkedin_url,
        'title', pe.title,
        'seniority', pe.seniority,
        'department', pe.department,
        'work_email', pe.work_email,
        'email_status', pe.email_status,
        'phone_e164', pe.phone_e164,
        'contact_confidence', pe.contact_confidence,
        'person_last_enriched_at', pe.last_enriched_at,
        'company_entity_id', ce.entity_id,
        'company_domain', ce.canonical_domain,
        'company_name', ce.canonical_name,
        'company_linkedin_url', ce.linkedin_url,
        'company_industry', ce.industry,
        'company_employee_count', ce.employee_count,
        'company_employee_range', ce.employee_range,
        'company_revenue_band', ce.revenue_band,
        'company_hq_country', ce.hq_country,
        'relationship_id', er.id,
        'relationship_valid_as_of', er.valid_as_of,
        'total_matched', COUNT(*) OVER()
    )
    FROM entities.entity_relationships er
    JOIN entities.person_entities pe
        ON er.org_id = pe.org_id AND er.source_entity_id = pe.entity_id
    LEFT JOIN entities.company_entities ce
        ON er.org_id = ce.org_id AND er.target_entity_id = ce.entity_id
    WHERE er.org_id = p_org_id
      AND er.relationship = 'works_at'
      AND er.source_entity_type = 'person'
      AND er.target_entity_type = 'company'
      AND er.invalidated_at IS NULL
      -- Company filters
      AND (p_industry IS NULL OR ce.industry ILIKE '%' || p_industry || '%')
      AND (p_employee_range IS NULL OR ce.employee_range = p_employee_range)
      AND (p_hq_country IS NULL OR ce.hq_country = p_hq_country)
      AND (p_canonical_domain IS NULL OR ce.canonical_domain = p_canonical_domain)
      AND (p_company_name IS NULL OR ce.canonical_name ILIKE '%' || p_company_name || '%')
      -- Person filters
      AND (p_title IS NULL OR pe.title ILIKE '%' || p_title || '%')
      AND (p_seniority IS NULL OR pe.seniority = p_seniority)
      AND (p_department IS NULL OR pe.department ILIKE '%' || p_department || '%')
      AND (p_email_status IS NULL OR pe.email_status = p_email_status)
      AND (p_has_email IS NULL OR (p_has_email = TRUE AND pe.work_email IS NOT NULL) OR (p_has_email = FALSE AND pe.work_email IS NULL))
      AND (p_has_phone IS NULL OR (p_has_phone = TRUE AND pe.phone_e164 IS NOT NULL) OR (p_has_phone = FALSE AND pe.phone_e164 IS NULL))
    ORDER BY pe.updated_at DESC
    LIMIT p_limit
    OFFSET p_offset;
$$;
