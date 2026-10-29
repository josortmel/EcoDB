-- #816 (29-oct-2026): search reads memory_embeddings, not memories.embedding. The cell's memories
-- (#717) and scripts/backfill_embeddings.py wrote only memories.embedding, so they stayed invisible to
-- search until an api restart re-ran migrate_3_0h_multimodal.sql (the #812 re-runs) and copied them.
-- One place for every writer: whenever a memory gets or changes its embedding, its 'text' row in
-- memory_embeddings follows. SECURITY DEFINER because ecodb_cell has no grant on memory_embeddings.
-- The API's own insert (memories.py FASE 3b) becomes a harmless ON CONFLICT DO NOTHING.
-- Every route stores the TEXT vector (of `content`) in memories.embedding; an image's vector goes to its
-- own 'image' row (memories.py FASE 3b), so this never files an image vector as 'text'. A PUT that
-- re-embeds used to update only memories.embedding: search kept the old vector; now it follows.
-- An UPDATE to NULL leaves the existing row alone (no invented delete). Idempotent: safe to re-run.

CREATE OR REPLACE FUNCTION sync_text_embedding() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    IF NEW.embedding IS NOT NULL THEN
        INSERT INTO public.memory_embeddings (memory_id, modality, embedding, source_ref, created_at)
        VALUES (NEW.id, 'text', NEW.embedding, NULL, NEW.created_at)
        ON CONFLICT (memory_id, modality) DO UPDATE SET embedding = EXCLUDED.embedding;
    END IF;
    RETURN NEW;
END $$;

REVOKE ALL ON FUNCTION sync_text_embedding() FROM PUBLIC;

-- #717 made the cell INSERT memories WITH embedding, but ecodb_cell had no INSERT on that column:
-- a scheduled (cron/catch-up) weekly run failed whole on its identity tension (Prima 19-25 oct,
-- 28-oct 17:50, "permission denied for table memories"). Runs triggered through the API (role ecodb)
-- were fine, which is why the regeneration hid it. Column-level, like the cell's other grants.
GRANT INSERT (embedding) ON public.memories TO ecodb_cell;

DROP TRIGGER IF EXISTS trg_sync_text_embedding ON public.memories;
CREATE TRIGGER trg_sync_text_embedding
    AFTER INSERT OR UPDATE OF embedding ON public.memories
    FOR EACH ROW EXECUTE FUNCTION sync_text_embedding();
