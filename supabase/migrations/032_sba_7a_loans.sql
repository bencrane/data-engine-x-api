BEGIN;

CREATE TABLE IF NOT EXISTS entities.sba_7a_loans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- SBA 7(a) CSV columns (43 fields)
    asofdate TEXT,
    program TEXT,
    l2locid TEXT,
    borrname TEXT,
    borrstreet TEXT,
    borrcity TEXT,
    borrstate TEXT,
    borrzip TEXT,
    bankname TEXT,
    bankfdicnumber TEXT,
    bankncuanumber TEXT,
    bankstreet TEXT,
    bankcity TEXT,
    bankstate TEXT,
    bankzip TEXT,
    grossapproval TEXT,
    sbaguaranteedapproval TEXT,
    approvaldate TEXT,
    approvalfiscalyear TEXT,
    firstdisbursementdate TEXT,
    processingmethod TEXT,
    subprogram TEXT,
    initialinterestrate TEXT,
    fixedorvariableinterestind TEXT,
    terminmonths TEXT,
    naicscode TEXT,
    naicsdescription TEXT,
    franchisecode TEXT,
    franchisename TEXT,
    projectcounty TEXT,
    projectstate TEXT,
    sbadistrictoffice TEXT,
    congressionaldistrict TEXT,
    businesstype TEXT,
    businessage TEXT,
    loanstatus TEXT,
    paidinfulldate TEXT,
    chargeoffdate TEXT,
    grosschargeoffamount TEXT,
    revolverstatus TEXT,
    jobssupported TEXT,
    collateralind TEXT,
    soldsecmrktind TEXT,

    -- Extract metadata columns
    extract_date DATE NOT NULL,
    source_filename TEXT NOT NULL,
    source_url TEXT,
    source_provider TEXT NOT NULL DEFAULT 'sba',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Composite unique constraint (dedup key)
ALTER TABLE entities.sba_7a_loans
    ADD CONSTRAINT uq_sba_7a_loans_extract_date_composite
    UNIQUE (extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_borrname
    ON entities.sba_7a_loans(borrname);

CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_borrstate
    ON entities.sba_7a_loans(borrstate);

CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_naicscode
    ON entities.sba_7a_loans(naicscode);

CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_approvaldate
    ON entities.sba_7a_loans(approvaldate);

CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_extract_date
    ON entities.sba_7a_loans(extract_date DESC);

CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_loanstatus
    ON entities.sba_7a_loans(loanstatus);

-- updated_at trigger
DROP TRIGGER IF EXISTS update_sba_7a_loans_updated_at ON entities.sba_7a_loans;
CREATE TRIGGER update_sba_7a_loans_updated_at
    BEFORE UPDATE ON entities.sba_7a_loans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security
ALTER TABLE entities.sba_7a_loans ENABLE ROW LEVEL SECURITY;

COMMIT;
