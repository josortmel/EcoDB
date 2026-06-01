-- Migration: v5.0.1 → v5.1.0 (multi-tenant)
-- Ejecutar DESPUÉS de v0.8.6. Idempotente.
BEGIN;

-- ── D1: organization_id cache en users ──
ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id INT REFERENCES organizations(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_users_organization ON users (organization_id) WHERE organization_id IS NOT NULL;

-- ── D5: API key rotation ──
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS replaced_by_key_id INT REFERENCES api_keys(id);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS grace_until TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_api_keys_grace ON api_keys (grace_until) WHERE grace_until IS NOT NULL AND active = true;

-- ── D10: organization_id en teams ──
ALTER TABLE teams ADD COLUMN IF NOT EXISTS organization_id INT REFERENCES organizations(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_teams_organization ON teams (organization_id);

-- ── D4: organization_id en audit_log ──
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS organization_id INT;
CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON audit_log (organization_id) WHERE organization_id IS NOT NULL;

-- ── D1: trigger propagación org_id (INSERT/UPDATE + DELETE) ──
CREATE OR REPLACE FUNCTION propagate_user_org_id() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
  target_user_id INT;
  resolved_org_id INT;
BEGIN
  target_user_id := COALESCE(NEW.user_id, OLD.user_id);

  SELECT DISTINCT w.organization_id INTO resolved_org_id
  FROM workspace_leads wl
  JOIN workspaces w ON w.id = wl.workspace_id
  WHERE wl.user_id = target_user_id AND w.organization_id IS NOT NULL
  LIMIT 1;

  IF resolved_org_id IS NULL THEN
    SELECT DISTINCT w.organization_id INTO resolved_org_id
    FROM project_members pm
    JOIN projects p ON p.id = pm.project_id
    JOIN workspaces w ON w.id = p.workspace_id
    WHERE pm.user_id = target_user_id AND w.organization_id IS NOT NULL
    LIMIT 1;
  END IF;

  UPDATE users SET organization_id = resolved_org_id WHERE id = target_user_id;
  RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_propagate_org_ws_leads ON workspace_leads;
CREATE TRIGGER trg_propagate_org_ws_leads
  AFTER INSERT OR UPDATE OR DELETE ON workspace_leads
  FOR EACH ROW EXECUTE FUNCTION propagate_user_org_id();

DROP TRIGGER IF EXISTS trg_propagate_org_proj_members ON project_members;
CREATE TRIGGER trg_propagate_org_proj_members
  AFTER INSERT OR UPDATE OR DELETE ON project_members
  FOR EACH ROW EXECUTE FUNCTION propagate_user_org_id();

-- ── D10: constraint cross-org en teams ──
CREATE OR REPLACE FUNCTION check_team_org_consistency() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
  team_org INT;
  member_org INT;
  resource_org INT;
BEGIN
  SELECT organization_id INTO team_org FROM teams WHERE id = NEW.team_id;

  IF TG_TABLE_NAME = 'team_members' THEN
    SELECT organization_id INTO member_org FROM users WHERE id = NEW.user_id;
    IF team_org IS NOT NULL AND member_org IS NOT NULL AND team_org != member_org THEN
      RAISE EXCEPTION 'Cannot add user from org % to team of org %', member_org, team_org;
    END IF;
  ELSIF TG_TABLE_NAME = 'team_resources' THEN
    SELECT w.organization_id INTO resource_org
    FROM projects p JOIN workspaces w ON w.id = p.workspace_id
    WHERE p.id = NEW.project_id;
    IF team_org IS NOT NULL AND resource_org IS NOT NULL AND team_org != resource_org THEN
      RAISE EXCEPTION 'Cannot add project from org % to team of org %', resource_org, team_org;
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_check_team_member_org ON team_members;
CREATE TRIGGER trg_check_team_member_org
  BEFORE INSERT OR UPDATE ON team_members
  FOR EACH ROW EXECUTE FUNCTION check_team_org_consistency();

DROP TRIGGER IF EXISTS trg_check_team_resource_org ON team_resources;
CREATE TRIGGER trg_check_team_resource_org
  BEFORE INSERT OR UPDATE ON team_resources
  FOR EACH ROW EXECUTE FUNCTION check_team_org_consistency();

-- ── D7: migration de datos existentes ──
INSERT INTO organizations (name)
SELECT 'Default'
WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE name = 'Default');

UPDATE workspaces
SET organization_id = (SELECT id FROM organizations WHERE name = 'Default')
WHERE organization_id IS NULL AND id != 1;

UPDATE users u SET organization_id = (
  SELECT DISTINCT w.organization_id
  FROM workspace_leads wl JOIN workspaces w ON w.id = wl.workspace_id
  WHERE wl.user_id = u.id AND w.organization_id IS NOT NULL
  LIMIT 1
) WHERE u.organization_id IS NULL AND NOT u.is_super;

UPDATE users u SET organization_id = (
  SELECT DISTINCT w.organization_id
  FROM project_members pm JOIN projects p ON p.id = pm.project_id
  JOIN workspaces w ON w.id = p.workspace_id
  WHERE pm.user_id = u.id AND w.organization_id IS NOT NULL
  LIMIT 1
) WHERE u.organization_id IS NULL AND NOT u.is_super;

UPDATE teams t SET organization_id = (
  SELECT DISTINCT w.organization_id
  FROM team_resources tr
  JOIN projects p ON p.id = tr.project_id
  JOIN workspaces w ON w.id = p.workspace_id
  WHERE tr.team_id = t.id AND w.organization_id IS NOT NULL
  LIMIT 1
) WHERE t.organization_id IS NULL;

DO $$
DECLARE
  multi_org_users RECORD;
BEGIN
  FOR multi_org_users IN
    SELECT DISTINCT u.id, u.name, array_agg(DISTINCT w.organization_id) AS orgs
    FROM users u
    LEFT JOIN workspace_leads wl ON wl.user_id = u.id
    LEFT JOIN workspaces w ON w.id = wl.workspace_id
    WHERE w.organization_id IS NOT NULL AND NOT u.is_super
    GROUP BY u.id, u.name
    HAVING COUNT(DISTINCT w.organization_id) > 1
  LOOP
    RAISE WARNING 'User % (%) has memberships in multiple orgs: %. Assigned to first.',
      multi_org_users.id, multi_org_users.name, multi_org_users.orgs;
  END LOOP;
END;
$$;

INSERT INTO schema_version (version, notes)
VALUES ('5.1.0', 'Multi-tenant: users.organization_id, api_keys rotation, teams.organization_id, audit_log.organization_id, org propagation triggers, team cross-org constraints.')
ON CONFLICT (version) DO NOTHING;

COMMIT;
