BEGIN;

CREATE TABLE IF NOT EXISTS ops.lists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('companies', 'people')),
    member_count INT NOT NULL DEFAULT 0,
    created_by_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT fk_lists_org FOREIGN KEY (org_id)
        REFERENCES ops.orgs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lists_org_id ON ops.lists(org_id);
CREATE INDEX IF NOT EXISTS idx_lists_org_id_deleted_at ON ops.lists(org_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_lists_created_by ON ops.lists(created_by_user_id);

CREATE TABLE IF NOT EXISTS ops.list_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    list_id UUID NOT NULL,
    org_id UUID NOT NULL,
    entity_id UUID,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person')),
    snapshot_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_list_members_list FOREIGN KEY (list_id)
        REFERENCES ops.lists(id) ON DELETE CASCADE,
    CONSTRAINT fk_list_members_org FOREIGN KEY (org_id)
        REFERENCES ops.orgs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_list_members_list_id ON ops.list_members(list_id);
CREATE INDEX IF NOT EXISTS idx_list_members_org_id ON ops.list_members(org_id);
CREATE INDEX IF NOT EXISTS idx_list_members_entity_id ON ops.list_members(entity_id);

COMMIT;
