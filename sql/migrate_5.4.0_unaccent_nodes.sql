-- 5.4.0 (#478, decisión 24): buscar y emparejar nodos sin tildes.
-- search_nodes encuentra «Jōtarō» buscando «Jotaro», y al crear un nodo se detecta el gemelo
-- que solo difiere en tildes (graph.py: _flag_accent_twin). La clave sin tildes sirve para
-- ENCONTRAR, no es un índice único: «Pärt» y «Part» tienen que poder convivir.
-- unaccent() es STABLE (su diccionario podría cambiar); el envoltorio IMMUTABLE con el
-- diccionario fijado es el patrón habitual para poder indexarlo.
-- Idempotente.
BEGIN;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE OR REPLACE FUNCTION public.f_unaccent(text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
    AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;
CREATE INDEX IF NOT EXISTS idx_nodes_name_unaccent ON nodes (public.f_unaccent(lower(name)));
COMMIT;
