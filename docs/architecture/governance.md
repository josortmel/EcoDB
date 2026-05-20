# Brief v3 — EcoDB phaseb: Gobernanza del Grafo de Conocimiento

*the research lead. 11 de mayo de 2026. Arquitecta. Post-Loop 1 adversarial v1 (23 items) + adversarial v2 (17 items) + 6 revisiones externas (3 por version). Todos los REQUIRED resueltos.*

---

## 1. Contexto y motivacion

EcoDB es el sistema unificado de memoria de the organization. PostgreSQL 16 + pgvector + Apache AGE. En produccion desde el 9 de mayo de 2026 (dia 67). Fases 1-2 completas. phasea casi completa.

El grafo tiene un problema estructural. Post-purga del 11 mayo: 1040 nodos, 954 tripletas, 720 predicados unicos. Ratio predicados/tripletas de 0.75. El grafo sigue sin vocabulario comun.

Tres modelos externos (ChatGPT, Gemini, DeepSeek) convergieron: EcoDB necesita gobernanza del conocimiento — predicados con metadata ontologica, pipeline de validacion, tipado de nodos, temporalidad, y separacion de hechos vs creencias.

**Por que ahora:** la phasea (GAMR Etapa 4, expansion por grafo) amplifica la basura si no hay gobernanza. phase (documentos) metera mas datos. Gobernar antes de crecer.

---

## 2. Decisiones de diseno (con trazabilidad)

### D1: Vocabulario cerrado — target 100 predicados, cap 130 con revision trimestral
- Origen: [research] 3/3 modelos + [user-brief] 4/4 pares + [research] DeepSeek revision
- Razon: 720 predicados para 954 tripletas es insostenible. Vocabulario cerrado fuerza consistencia.
- Trade-off: pierde expresividad libre. Mitigado por tabla pending_predicates (ver D11).
- Limite: cada nuevo predicado requiere 3+ tripletas reales. Revision trimestral si se necesitan >100.

### D2: Eliminar "es" — partir en instancia_de, tipo_de, rol_de, alias_de
- Origen: [research] Convergencia 3/3 modelos externos
- Razon: "es" absorbe identidad, tipo, rol, equivalencia, alias.
- Trade-off: cuatro predicados donde habia uno.

### D3: Cluster epistemologico — cree, afirma, sospecha, verifica, contradice
- Origen: [research] Convergencia 3/3 modelos externos
- Razon: sistema multiagente donde las creencias no deben persistirse como verdades.
- Trade-off: complejidad en escritura — el agente elige entre sabe/cree/afirma/sospecha.

### D4: Causalidad y transformacion
- Origen: [research] ChatGPT + DeepSeek (2/3)
- Predicados: causa, provoca, habilita, bloquea, se_convierte_en, evoluciona_a, migra_a, fusiona_con.
- Razon: sin causalidad el grafo describe pero no explica.

### D5: Metadata ontologica por predicado
- Origen: [research] ChatGPT + DeepSeek (2/3)
- Campos: symmetric (bool), inverse_of (text nullable), transitive (bool), domain_types (text[]), range_types (text[]).
- Razon: evita duplicar tripletas para inversos. Habilita inferencia futura.

### D6: Temporalidad como edge properties
- Origen: [research] Convergencia 3/3
- Campos nuevos en tabla triples: valid_from (timestamptz nullable), valid_to (timestamptz nullable), assertion_confidence (real, 0-1, confianza en el hecho), source_agent (text nullable).
- Para tripletas migradas: valid_from = created_at original, source_agent = 'MIGRACION_LEGACY'.
- Nota: assertion_confidence mide certeza del HECHO. Es distinto de mapper_confidence que mide certeza del PROCESO de normalizacion (ver D8).

### D7: Tipado de nodos — lazy typing
- Origen: [research] ChatGPT + Gemini + [research] DeepSeek revision (tipado lazy)
- Implementacion: nodos nuevos exigen tipo en creacion. Nodos existentes tipo = 'unknown'. Priorizar clasificacion manual del top 20% por grado de conexion.
- Tipos disponibles: persona, agente_ia, organizacion, lugar, producto, proyecto, tecnologia, concepto, artefacto, evento, unknown.
- Nota: las 6 categorias originales de entity_dictionary se amplian a 11 para cubrir nodos tecnicos (Docker, PostgreSQL → tecnologia) y narrativos (paladin, magia → concepto).
- La validacion tipologica es PERMISIVA para nodos tipo 'unknown' (cualquier predicado permitido). Estricta solo para nodos con tipo asignado.

### D8: Pipeline de normalizacion hibrido — 5 etapas, reordenado
- Origen: [research] ChatGPT (pipeline 5 etapas) + Gemini (cache) + DeepSeek (ANN) + adversarial A4 (reorden)
- Orden corregido (embeddings al final, no al medio):
  1. Normalizacion lexica (lowercase, snake_case, trim) — <1ms
  2. Cache de lexemas + alias manuales por dominio — <1ms si hit
  3. Validacion estructural de tipos (domain_types/range_types de la matriz) — <1ms
  4. Embedding similarity con ANN index (pgvector sobre predicate_embeddings) — <50ms
  5. Human-in-the-loop: si mapper_confidence < 0.70 → tripleta se guarda con needs_review=true + original_predicate preservado
- Budget de latencia: <500ms total por guardar_tripleta (pipeline completo incluido).
- CE de baja confianza: mapper_confidence < 0.70 → needs_review=true, original_predicate preservado en metadata, tripleta accesible pero marcada. mapper_confidence >= 0.70 → mapeo automatico.
- Tabla de alias tiene columna domain (text nullable). Alias global si domain=null. Alias especifico si domain='tecnico'/'narrativo'/'diseno'.

### D9: Autoridad por dominio — SUGERENCIA para el humano, no regla automatica
- Origen: [research] Gemini propuesta + [research] DeepSeek + ChatGPT revision (ambos recomiendan guia, no automatismo) + adversarial C3/A5 (contradiccion con scope)
- Correccion post-adversarial: D9 original decia "gana para reasoning global". Eso implicaba automatismo. Corregido: la autoridad es metadata del predicado (authority_agents text[] en predicates_canonical). Cuando el GAMR detecta contradiccion, la SENALA con "agente X tiene autoridad sugerida sobre este cluster". El humano resuelve. El sistema NO resuelve automaticamente.
- Trade-off: requiere intervencion humana para contradicciones. Aceptable en single-tenant.

### D10: Mantener protege, escribe, gobierna
- Origen: [my-inference] + 4/4 pares
- Razon: matices semanticos reales, no teoricos. El grafo existe para capturar matices.

### D11: Tabla pending_predicates para predicados sin mapeo (NUEVO)
- Origen: [research] DeepSeek revision
- Razon: durante migracion, predicados que no mapean con confianza suficiente no se descartan. Van a pending_predicates con frecuencia de uso. Si alcanzan 3+ usos, se evaluan para incorporar al vocabulario. Si no, se archivan.

### D12: Versionado de ontologia (NUEVO)
- Origen: [research] DeepSeek revision + ChatGPT revision + adversarial L5
- Implementacion: cada predicado tiene estado (experimental → candidate → approved → deprecated → archived → forbidden) + deprecated_since (timestamptz) + replaced_by (text nullable).
- Predicados deprecated no se eliminan. Tripletas historicas con predicado deprecated se consultan via COALESCE(replaced_by, predicate).
- Sin versionado, la primera fusion de predicados rompe queries historicas sin rollback.

### D13: Inferencia de inversos como vista PostgreSQL desde dia 1 (NUEVO)
- Origen: [research] Gemini revision + adversarial R2
- Implementacion: vista SQL que combina tripleta directa con su inversa usando inverse_of de predicates_canonical. ~10 lineas SQL. Sin duplicacion de datos.
- La vista incluye campo `inferred BOOLEAN` — true para edges inferidos, false para explicitos. Los agentes nunca ven un edge inferido indistinguible de uno explicito.
- El GAMR y endpoints que usan la vista propagan el campo inferred para que el agente sepa que es una inferencia, no un hecho guardado.
- Razon: diferir esto era deuda injustificada — el coste es minimo y el beneficio es navegacion bidireccional inmediata.

### D14: Separar core ontology vs domain ontology (NUEVO)
- Origen: [research] ChatGPT revision
- Core (muy estable, cambios raros): parte_de, depende_de, causa, instancia_de, tipo_de, crea, usa...
- Domain (flexible, evoluciona por dominio): ama, simboliza, usa_paleta, antagonista_de...
- Beneficio: estabilidad global con flexibilidad local. Core no se toca sin revision formal. Domain evoluciona por dominio con revision trimestral.
- Campos en DDL: `ontology_layer` = 'core' o 'domain'. `cluster` = grupo semantico (ej. "Amor y deseo"). `domain` = area de conocimiento (ej. "narrativo", "tecnico", "diseno") — nullable para predicados universales. Los tres campos tienen semantica distinta y no son redundantes.
- Revision formal del core: requiere propuesta escrita + aprobacion de the platform owner + revision por el par con autoridad sobre el dominio afectado. Minimo 1 semana entre propuesta y aplicacion. Domain: el par con autoridad propone, the platform owner aprueba, aplicacion inmediata.

---

## 3. Scope

### Dentro:
- DDL de tabla predicates_canonical con metadata ontologica completa
- DDL de tabla predicate_aliases (variante → canonico, con dominio)
- DDL de tabla pending_predicates (predicados sin mapeo, con frecuencia)
- Campos nuevos en tabla triples: valid_from, valid_to, assertion_confidence, source_agent
- Campos nuevos en tabla nodes: type (text, default 'unknown')
- Columna needs_review (bool) + mapper_confidence (real) + original_predicate (text) en triples
- Vista SQL para inferencia bidireccional de inversos
- Pipeline de normalizacion en guardar_tripleta del MCP (5 etapas reordenadas)
- Seed del vocabulario con ~100 predicados consensuados + metadata
- Migracion de 720 predicados actuales a vocabulario canonico (con rollback)
- Clasificacion manual del top 20% nodos por grado (resto = 'unknown')
- Endpoint GET /graph/triples?needs_review=true (minimo viable para gobernanza)
- Ontology Console como tarea de phase (dashboard Electron con the design lead)

### Fuera (deuda consciente):
- Reasoning automatico sobre transitividad/simetria (la metadata se guarda pero no se explota en queries)
- Resolucion automatica de contradicciones (el sistema senala + sugiere autoridad, el humano resuelve)
- Umbrales diferenciados por cluster (durante fase sin umbrales, el mapper puede cometer errores de mayor gravedad en clusters de identidad/tecnico que en emocional — documentado como riesgo aceptado)
- Reificacion de relaciones complejas (regla documentada: "si una relacion necesita >3 atributos propios, deberia ser nodo" — comunicada a agentes aunque la implementacion se difiera)
- Semantic budgets por dominio (proceso operativo, no codigo)
- Archivo automatico de tripletas caducadas >90 dias (proceso mensual futuro)

---

## 4. DDL de predicates_canonical (resuelve L1 adversarial)

```sql
CREATE TABLE predicates_canonical (
  name            TEXT PRIMARY KEY,
  cluster         TEXT NOT NULL,
  ontology_layer  TEXT NOT NULL CHECK (ontology_layer IN ('core', 'domain')),
  domain          TEXT,
  description     TEXT,
  symmetric       BOOLEAN NOT NULL DEFAULT false,
  inverse_of      TEXT REFERENCES predicates_canonical(name) DEFERRABLE INITIALLY DEFERRED,
  transitive      BOOLEAN NOT NULL DEFAULT false,
  domain_types    TEXT[] NOT NULL DEFAULT '{}',
  range_types     TEXT[] NOT NULL DEFAULT '{}',
  authority_agents TEXT[] NOT NULL DEFAULT '{}',
  state           TEXT NOT NULL DEFAULT 'approved'
                  CHECK (state IN ('experimental','candidate','approved','deprecated','archived','forbidden')),
  deprecated_since TIMESTAMPTZ,
  replaced_by     TEXT REFERENCES predicates_canonical(name),
  embedding          vector(512),
  embedding_model    TEXT DEFAULT 'jina-v4',
  embedding_version  TEXT,
  embedding_updated  TIMESTAMPTZ,
  created_at         TIMESTAMPTZ DEFAULT now(),
  updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_pc_cluster ON predicates_canonical (cluster);
CREATE INDEX idx_pc_state ON predicates_canonical (state);
CREATE INDEX idx_pc_embedding ON predicates_canonical
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
```

```sql
CREATE TABLE predicate_aliases (
  alias       TEXT NOT NULL,
  canonical   TEXT NOT NULL REFERENCES predicates_canonical(name),
  domain      TEXT,
  auto_learned BOOLEAN DEFAULT false,
  confirmations INT DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (alias, domain)
);
-- ACL: escritura super-only para aliases manuales.
-- auto_learned es campo reservado para phase (aprendizaje por feedback).
-- En phaseb, auto_learned siempre false y confirmations siempre 0.
```

```sql
CREATE TABLE pending_predicates (
  predicate      TEXT PRIMARY KEY,
  frequency      INT DEFAULT 1,
  status         TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','promoted','archived','rejected')),
  reviewed_by    INT REFERENCES users(id),
  first_seen     TIMESTAMPTZ DEFAULT now(),
  last_seen      TIMESTAMPTZ DEFAULT now(),
  archive_after  TIMESTAMPTZ DEFAULT (now() + INTERVAL '90 days'),
  sample_triples JSONB DEFAULT '[]'
);
-- TTL: proceso mensual mueve a 'archived' los pending con
-- frequency < 3 AND last_seen < now() - 90 days.
-- 'promoted' = movido a predicates_canonical.
-- 'rejected' = descartado con razon documentada.
```

---

## 5. Criterios de exito (verificables)

- CE-1: SELECT count(*) FROM predicates_canonical WHERE state = 'approved' devuelve entre 90 y 130
- CE-2: Cada predicado approved tiene symmetric, inverse_of, transitive, domain_types, range_types, cluster, ontology_layer no null
- CE-3: SELECT count(*) FROM triples WHERE predicate NOT IN (SELECT name FROM predicates_canonical WHERE state IN ('approved','deprecated')) AND predicate NOT IN (SELECT predicate FROM pending_predicates) devuelve 0. NOTA: tripletas con predicado en pending_predicates NO participan en reasoning canonico del GAMR (Etapa 4 expansion las excluye). pending es cuarentena, no extension del vocabulario
- CE-4: guardar_tripleta con predicado libre "hecho_por" normaliza a "crea" y respuesta incluye original_predicate + canonical_predicate + mapper_confidence
- CE-5: guardar_tripleta con predicado "ama" + sujeto tipo "tecnologia" + objeto tipo "persona" devuelve error de validacion (nodo con tipo asignado). Con sujeto tipo "unknown" → pasa (permisivo)
- CE-6: SELECT count(*) FROM nodes WHERE type IS NULL devuelve 0 (todos tienen tipo, aunque sea 'unknown')
- CE-7: valid_from, valid_to, assertion_confidence, source_agent existen en triples. Tripletas nuevas rellenan source_agent obligatorio. Migradas tienen source_agent = 'MIGRACION_LEGACY'
- CE-8: Pipeline completo de guardar_tripleta < 500ms medido end-to-end
- CE-9: guardar_tripleta con mapper_confidence < MAPPER_THRESHOLD (configurable, default 0.70 provisional — a calibrar con piloto de 50 tripletas post-seed) guarda tripleta con needs_review=true + original_predicate preservado. El threshold es env var, no hardcoded. Tests usan el valor de la env var, no un literal
- CE-10: Vista SQL de inversos funciona: consultar hijo_de devuelve tambien padre_de inferido CON campo inferred=true
- CE-11: Target operativo nodos unknown: <50% al lanzamiento de phaseb, <30% dentro de 30 dias. Top 20% por grado clasificado manualmente antes de lanzar
- CE-12: guardar_tripleta respuesta MCP incluye mapper_confidence + original_predicate + canonical_predicate cuando hay normalizacion (contrato MCP actualizado)

---

## 6. Plan de rollback para migracion (resuelve L3 adversarial)

Antes de migrar predicados:
1. pg_dump snapshot de tablas triples + nodes + predicate_embeddings
2. Script de migracion genera report dry-run: cuantos mapean con confianza >= 0.70, cuantos van a pending_predicates, cuantos no mapean
3. Criterio de abort: si >25% de tripletas no mapean con confianza >= 0.70, abort y revision manual
4. Si abort: restore desde snapshot, revisar vocabulario, reintentar
5. Las tripletas migradas preservan original_predicate en metadata JSONB

---

## 7. Deuda explicita

- Umbrales diferenciados por cluster: durante fase sin umbrales, errores en clusters identidad/tecnico (instancia_de vs tipo_de) tienen mayor gravedad que errores en emocional (quiere vs ama). Riesgo aceptado, documentado.
- Clasificacion completa de nodos: top 20% por grado clasificado manualmente. Resto = 'unknown' con validacion permisiva. Clasificacion completa es gradual.
- Reificacion: regla "si relacion necesita >3 atributos → nodo" documentada y comunicada a agentes. Implementacion diferida hasta caso real.
- Archivo de tripletas caducadas: proceso mensual futuro (historical_triples).
- Ontology Console: phase, the design lead diseña UI. Mientras tanto: endpoint GET /graph/triples?needs_review=true + queries directas.

---

## 8. Cierre Loop 1 — resolucion de items adversariales

### Adversarial v1 (23 items): 7 REQUIRED resueltos en Brief v2
### Adversarial v2 (17 items): 7 REQUIRED resueltos en Brief v3

| Item | Resolucion |
|------|-----------|
| A1 (FK DEFERRABLE) | APPLIED — DDL corregido |
| A2 (CE-3 pending como canonico) | APPLIED — nota explicita: pending excluido de GAMR |
| A3 (CE-9 threshold hardcoded) | APPLIED — configurable via env var, provisional |
| A4 (embedding provenance) | APPLIED — embedding_model + embedding_version en DDL |
| C1 (auto_learned scope) | APPLIED — documentado como reservado phase |
| L1 (alias ACL) | APPLIED — super-only documentado |
| L2 (pending TTL) | APPLIED — estados + archive_after 90 dias |

### SOFT resueltos en Brief v3
| Item | Resolucion |
|------|-----------|
| C2 (inferred marker) | APPLIED — campo inferred en vista + CE-10 |
| C3 (domain vs cluster) | APPLIED — semantica aclarada en D14 |
| L3 (revision formal core) | APPLIED — proceso definido en D14 |
| L4 (target unknown) | APPLIED — CE-11: <50% lanzamiento, <30% en 30 dias |
| S3 (MCP response contract) | APPLIED — CE-12 |
| R3 (unknown target) | APPLIED — CE-11 |
| R4 (inferred marker) | APPLIED — D13 + CE-10 |

### DEFERRED con justificacion
| Item | Razon |
|------|-------|
| A5 (distribucion grado nodos) | Se calcula en verification_checkpoint Loop 2. No es dato de Brief |
| S1 (embeddings predicados seed) | Prerequisito implicito del seed — se ejecuta como parte de la tarea |
| S2 (cobertura vocabulario narrativo) | El vocabulario seed se valida con Eco antes de ejecutar. No blocker del Brief |
| R2 (separar tabla en 3) | Con 100 predicados, una tabla es manejable. Si llega a 500+, se refactoriza |

## 9. Preguntas para Loop 2 (Spec + Plan)

1. La vista de inversos con campo inferred — performance con 10k tripletas? Materializar si necesario?
2. El pipeline de normalizacion — implementacion concreta en server.py del MCP. Donde vive cada etapa?
3. El seed de ~100 predicados — lista completa con metadata. Quien la produce? Eco + the research lead + the design lead?
4. Piloto de 50 tripletas para calibrar threshold — antes o despues de migracion masiva?
5. El GAMR Etapa 4 excluye pending — cambio en search.py o en el MCP?
