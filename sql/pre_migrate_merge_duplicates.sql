-- Pre-migración 3.0h: merge 10 pares de nodos duplicados por casing.
-- Casing canónico decidido por Eco (worldbuilding Las Tierras Rotas).
-- Ejecutar ANTES de migrate_3_0h_multimodal.sql.
--
-- Estrategia: keep=nodo con más triples (menos UPDATEs). Rename si casing
-- del survivor no es el canónico. Reasignar triples + memory_entity_links.
-- ON CONFLICT: duplicados post-merge → ignorar (datos ya apuntan al survivor).

BEGIN;

-- Helper: para cada par, reasignar + borrar duplicado.
-- Pair 1: keep 798 "Abuela sin nombre" (1 triple), remove 2050 (0 triples)
UPDATE triples SET subject_id = 798 WHERE subject_id = 2050;
UPDATE triples SET object_id = 798 WHERE object_id = 2050;
UPDATE memory_entity_links SET entity_node_id = 798 WHERE entity_node_id = 2050;
DELETE FROM nodes WHERE id = 2050;

-- Pair 2: keep 500 "ECO_Textos" (2 triples), remove 1940 (1 triple)
UPDATE triples SET subject_id = 500 WHERE subject_id = 1940;
UPDATE triples SET object_id = 500 WHERE object_id = 1940;
UPDATE memory_entity_links SET entity_node_id = 500 WHERE entity_node_id = 1940;
DELETE FROM nodes WHERE id = 1940;

-- Pair 3: keep 675 "El Párpado Solar" (7 triples), remove 2035 (0 triples)
UPDATE triples SET subject_id = 675 WHERE subject_id = 2035;
UPDATE triples SET object_id = 675 WHERE object_id = 2035;
UPDATE memory_entity_links SET entity_node_id = 675 WHERE entity_node_id = 2035;
DELETE FROM nodes WHERE id = 2035;

-- Pair 4: keep 2038 (3 triples, rename), remove 284 (2 triples)
UPDATE triples SET subject_id = 2038 WHERE subject_id = 284;
UPDATE triples SET object_id = 2038 WHERE object_id = 284;
UPDATE memory_entity_links SET entity_node_id = 2038 WHERE entity_node_id = 284;
DELETE FROM nodes WHERE id = 284;
UPDATE nodes SET name = 'El Último Emperador' WHERE id = 2038;

-- Pair 5: keep 1009 "La Abuela" (20 triples), remove 576 (6 triples)
UPDATE triples SET subject_id = 1009 WHERE subject_id = 576;
UPDATE triples SET object_id = 1009 WHERE object_id = 576;
UPDATE memory_entity_links SET entity_node_id = 1009 WHERE entity_node_id = 576;
DELETE FROM nodes WHERE id = 576;

-- Pair 6: keep 2010 (14 triples, rename), remove 673 (2 triples)
UPDATE triples SET subject_id = 2010 WHERE subject_id = 673;
UPDATE triples SET object_id = 2010 WHERE object_id = 673;
UPDATE memory_entity_links SET entity_node_id = 2010 WHERE entity_node_id = 673;
DELETE FROM nodes WHERE id = 673;
UPDATE nodes SET name = 'Las Estrellas Danzantes' WHERE id = 2010;

-- Pair 7: keep 1239 "Marineros de Lantia" (1 triple), remove 2363 (1 triple)
UPDATE triples SET subject_id = 1239 WHERE subject_id = 2363;
UPDATE triples SET object_id = 1239 WHERE object_id = 2363;
UPDATE memory_entity_links SET entity_node_id = 1239 WHERE entity_node_id = 2363;
DELETE FROM nodes WHERE id = 2363;

-- Pair 8: keep 2560 (6 triples, rename), remove 695 (2 triples)
UPDATE triples SET subject_id = 2560 WHERE subject_id = 695;
UPDATE triples SET object_id = 2560 WHERE object_id = 695;
UPDATE memory_entity_links SET entity_node_id = 2560 WHERE entity_node_id = 695;
DELETE FROM nodes WHERE id = 695;
UPDATE nodes SET name = 'Nubes Obsidianas' WHERE id = 2560;

-- Pair 9: keep 703 "Protagonista" (3 triples), remove 2080 (0 triples)
UPDATE triples SET subject_id = 703 WHERE subject_id = 2080;
UPDATE triples SET object_id = 703 WHERE object_id = 2080;
UPDATE memory_entity_links SET entity_node_id = 703 WHERE entity_node_id = 2080;
DELETE FROM nodes WHERE id = 2080;

-- Pair 10: keep 773 (1 triple, rename), remove 2439 (1 triple)
UPDATE triples SET subject_id = 773 WHERE subject_id = 2439;
UPDATE triples SET object_id = 773 WHERE object_id = 2439;
UPDATE memory_entity_links SET entity_node_id = 773 WHERE entity_node_id = 2439;
DELETE FROM nodes WHERE id = 2439;
UPDATE nodes SET name = 'Pueblo de la Frontera' WHERE id = 773;

-- Cleanup: self-referencing triples (subject=object post-merge) si hubiera
DELETE FROM triples WHERE subject_id = object_id;

-- Verificación post-merge: 0 duplicados esperado
-- SELECT lower(name), count(*) FROM nodes GROUP BY lower(name) HAVING count(*) > 1;

COMMIT;
