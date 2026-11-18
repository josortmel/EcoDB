-- 5.6.0 (#1332, pieza A de #1200): claves de SOLO LECTURA. Con read_only, la clave solo pasa por la lista
-- explícita de rutas de lectura de auth.RUTAS_DE_LECTURA; lo demás da 403 en el servidor.
-- Idempotente; las claves que ya existen quedan como estaban (false).
BEGIN;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS read_only boolean NOT NULL DEFAULT false;
COMMIT;
