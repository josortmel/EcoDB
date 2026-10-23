-- 5.4.1 (#569): columnas de revisión del mapeo de predicados en triples.
-- Producción ya las tiene: las añadieron los scripts de la Fase 3b (scripts/migrate_predicates.py),
-- sin migración en el repo, así que ninguna base nueva ni la de pruebas las tenía.
-- Mismos tipos y valores por defecto que producción (\d triples, 23-oct-2026).
-- Idempotente: en producción no cambia nada.
BEGIN;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS valid_from           timestamptz;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS valid_to             timestamptz;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS assertion_confidence real;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS source_agent         text;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS needs_review         boolean DEFAULT false;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS mapper_confidence    real;
ALTER TABLE triples ADD COLUMN IF NOT EXISTS original_predicate   text;
COMMIT;
