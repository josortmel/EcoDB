BEGIN;
-- Reverse triggers
DROP TRIGGER IF EXISTS trg_check_team_resource_org ON team_resources;
DROP TRIGGER IF EXISTS trg_check_team_member_org ON team_members;
DROP TRIGGER IF EXISTS trg_propagate_org_proj_members ON project_members;
DROP TRIGGER IF EXISTS trg_propagate_org_ws_leads ON workspace_leads;
DROP FUNCTION IF EXISTS check_team_org_consistency();
DROP FUNCTION IF EXISTS propagate_user_org_id();
-- Reverse columns
ALTER TABLE audit_log DROP COLUMN IF EXISTS organization_id;
ALTER TABLE teams DROP COLUMN IF EXISTS organization_id;
ALTER TABLE api_keys DROP COLUMN IF EXISTS grace_until;
ALTER TABLE api_keys DROP COLUMN IF EXISTS replaced_by_key_id;
ALTER TABLE users DROP COLUMN IF EXISTS organization_id;
-- Reverse data (Default org stays — no data loss)
DELETE FROM schema_version WHERE version = '5.1.0';
COMMIT;
