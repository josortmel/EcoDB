-- Auto-sync nodes table → AGE graph.
-- Delimiters: $cypher$ instead of $$ to avoid conflict with node names containing $$.
-- #447 (16-oct): the values travel as an agtype PARAMETER (EXECUTE … USING, AGE manual «Prepared
-- Statements»), never interpolated. format(%L) is SQL escaping: cypher does not read '' as an escaped quote,
-- so a name like «O'Brien» made the node in SQL but no vertex in AGE (only a WARNING). Rule (graph.py:21):
-- no value is ever interpolated into a cypher text, not in SQL or triggers either.

CREATE OR REPLACE FUNCTION age_sync_insert() RETURNS trigger AS
$body$
BEGIN
    EXECUTE 'SELECT * FROM cypher(''ecodb_graph'', $cypher$CREATE (n:Entity {name: $name, sql_id: $sid}) RETURN id(n)$cypher$, $1) AS (node_id agtype)'
        USING (jsonb_build_object('name', NEW.name, 'sid', NEW.id))::text::agtype;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'AGE sync INSERT failed for node %: %', NEW.id, SQLERRM;
    RETURN NEW;
END;
$body$
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION age_sync_remove() RETURNS trigger AS
$body$
DECLARE
    target_id int;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_id := OLD.id;
    ELSE
        target_id := NEW.id;
    END IF;
    IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND NEW.status != 'active' AND (OLD.status = 'active' OR OLD.status IS NULL)) THEN
        EXECUTE format(
            'SELECT * FROM cypher(''ecodb_graph'', $cypher$MATCH (n:Entity {sql_id: %s}) DETACH DELETE n$cypher$) AS (d agtype)',
            target_id
        );
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'AGE sync REMOVE failed for node %: %', COALESCE(target_id, -1), SQLERRM;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$body$
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION age_sync_rename() RETURNS trigger AS
$body$
BEGIN
    IF NEW.name != OLD.name THEN
        EXECUTE 'SELECT * FROM cypher(''ecodb_graph'', $cypher$MATCH (n:Entity {sql_id: $sid}) SET n.name = $name RETURN id(n)$cypher$, $1) AS (node_id agtype)'
            USING (jsonb_build_object('name', NEW.name, 'sid', NEW.id))::text::agtype;
    END IF;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'AGE sync RENAME failed for node %: %', NEW.id, SQLERRM;
    RETURN NEW;
END;
$body$
LANGUAGE plpgsql;

-- Reactivation: recreate AGE node when status changes back to 'active'
CREATE OR REPLACE FUNCTION age_sync_reactivate() RETURNS trigger AS
$body$
BEGIN
    IF NEW.status = 'active' AND (OLD.status != 'active' OR OLD.status IS NULL) THEN
        EXECUTE 'SELECT * FROM cypher(''ecodb_graph'', $cypher$CREATE (n:Entity {name: $name, sql_id: $sid}) RETURN id(n)$cypher$, $1) AS (node_id agtype)'
            USING (jsonb_build_object('name', NEW.name, 'sid', NEW.id))::text::agtype;
    END IF;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'AGE sync REACTIVATE failed for node %: %', NEW.id, SQLERRM;
    RETURN NEW;
END;
$body$
LANGUAGE plpgsql;

-- Attach triggers
DROP TRIGGER IF EXISTS trg_age_sync_insert ON nodes;
CREATE TRIGGER trg_age_sync_insert
    AFTER INSERT ON nodes
    FOR EACH ROW
    WHEN (NEW.status = 'active' OR NEW.status IS NULL)
    EXECUTE FUNCTION age_sync_insert();

DROP TRIGGER IF EXISTS trg_age_sync_remove ON nodes;
CREATE TRIGGER trg_age_sync_remove
    AFTER DELETE OR UPDATE OF status ON nodes
    FOR EACH ROW
    EXECUTE FUNCTION age_sync_remove();

DROP TRIGGER IF EXISTS trg_age_sync_rename ON nodes;
CREATE TRIGGER trg_age_sync_rename
    AFTER UPDATE OF name ON nodes
    FOR EACH ROW
    WHEN (NEW.status = 'active')
    EXECUTE FUNCTION age_sync_rename();

DROP TRIGGER IF EXISTS trg_age_sync_reactivate ON nodes;
CREATE TRIGGER trg_age_sync_reactivate
    AFTER UPDATE OF status ON nodes
    FOR EACH ROW
    WHEN (NEW.status = 'active')
    EXECUTE FUNCTION age_sync_reactivate();
