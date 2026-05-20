-- ============================================================================
-- EcoDB — init.sql
-- Schema inicial v1.0.0 (plan maestro v3, 2026-05-07)
--
-- Este script se ejecuta automaticamente por docker-entrypoint-initdb.d
-- contra la base ecodb ya creada por POSTGRES_DB en docker-compose.
-- NO incluir CREATE DATABASE — la BD ya existe.
--
-- Cambios respecto al plan v3:
--   1. tags TEXT[] añadido a memories (2026-05-07).
--   2. Numeracion de seccion 1.11 desambiguada a 1.11/1.12/1.13.
--   3. ALTER DATABASE para persistir search_path y preload de AGE.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1.0 Extensiones e inicializacion del grafo AGE
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector >= 0.9
CREATE EXTENSION IF NOT EXISTS age;          -- Apache AGE 1.5.0 para PG16
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram fuzzy matching
-- gen_random_uuid() es built-in en PG13+. uuid-ossp y pgcrypto NO son necesarios.

-- AGE necesita estar precargado en cada sesion y ag_catalog en el search_path.
-- Persistir a nivel de base de datos para que TODA conexion lo herede.
-- IMPORTANTE: public PRIMERO en el search_path para que CREATE TABLE en este
-- script (y futuros migrations) vayan a public, no a ag_catalog. Las funciones
-- de AGE (cypher, create_graph, etc.) siguen accesibles sin prefijo porque
-- ag_catalog esta en el path.
ALTER DATABASE ecodb SET search_path = public, ag_catalog, "$user";
ALTER DATABASE ecodb SET session_preload_libraries = 'age';

LOAD 'age';
SET search_path = public, ag_catalog, "$user";

-- Inicializar el grafo principal del sistema. Idempotente: si ya existe, ignorar.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'ecodb_graph') THEN
    PERFORM create_graph('ecodb_graph');
  END IF;
END$$;

-- ----------------------------------------------------------------------------
-- 1.1 Versionado de schema
-- ----------------------------------------------------------------------------
CREATE TABLE schema_version (
  version    TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ DEFAULT now(),
  notes      TEXT
);

INSERT INTO schema_version (version, notes)
VALUES ('5.0.0', 'EcoDB schema Fase 5: staleness, auto-link confidence, trust tiers, BM25, entity governance, related documents.');

-- ----------------------------------------------------------------------------
-- 1.2 Usuarios, agentes y API keys
-- ----------------------------------------------------------------------------
-- ============================================================================
-- MODELO DE ROLES — cuatro niveles de privilegio (decision arquitectonica
-- cerrada el 2026-05-07 durante construccion; debe propagarse al plan v3 §1
-- y al SKILL workflow-diseno para que no se quede sin fijar en proximos disenos):
--
--   1. SUPERUSUARIO (platform owner):
--      - users.is_super = true
--      - acceso a TODO sin restriccion de organizacion
--      - puede crear organizations y CEOs
--      - unico en el sistema (constraint: solo una fila con is_super=true)
--
--   2. CEO (dueño de empresa cliente):
--      - users.is_ceo = true + organizations.ceo_user_id apunta a este user
--      - acceso a TODO dentro de SU organization
--      - puede crear workspace_leads (admins) dentro de SU organization
--      - 1 CEO por organization (organizations.ceo_user_id UNIQUE)
--
--   3. ADMIN / LEAD de workspace (jefe de departamento — RRHH, ventas, etc.):
--      - workspace_leads.user_id apunta a este user
--      - puede crear users y asignarlos a projects DENTRO de SU workspace
--      - puede usar projects globales (is_common=true) del workspace
--      - NO puede tocar otros workspaces ni crear is_ceo/is_super
--
--   4. USUARIO regular:
--      - project_members.user_id apunta a este user
--      - acceso solo a los projects donde es miembro
--
-- Mapeo conceptual:
--   organization = empresa cliente
--   workspace    = departamento de la empresa
--   project      = proyecto literal del departamento (o is_common del depto)
--
-- When onboarding a new client organization:
--   1. Super crea la organization.
--   2. Super designa al CEO de la empresa (is_ceo=true, organizations.ceo_user_id).
--   3. CEO designa workspace_leads (jefes de cada departamento de la empresa).
--   4. Cada lead crea sus users dentro de su workspace.
--
-- F4 (verificador Loop 3 + coord): emails como tabla puente normalizada
-- user_emails con email como PK → unicidad global automatica. El modelo anterior
-- con aliases TEXT[] permitia que el email de un user apareciera como alias de
-- otro → suplantacion en auth lookup.
--
-- Auth lookup tipico:
--   SELECT u.id, u.name, u.is_super, u.is_ceo
--   FROM users u JOIN user_emails ue ON ue.user_id = u.id
--   WHERE ue.email = :email AND u.active = true;
-- ============================================================================
CREATE TABLE users (
  id         SERIAL PRIMARY KEY,
  name       TEXT NOT NULL,
  is_super   BOOLEAN NOT NULL DEFAULT false,
  is_ceo     BOOLEAN NOT NULL DEFAULT false,
  active     BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  -- OBS-1 (verificador Loop 4): super y CEO son roles excluyentes por
  -- definicion del modelo. The superuser is the platform owner; CEOs are
  -- client company owners. Que coexistan en la misma fila seria
  -- semanticamente incoherente. CHECK lo impide a nivel schema.
  CHECK (NOT (is_super AND is_ceo))
);

-- Solo UN superusuario en el sistema. Partial unique index.
CREATE UNIQUE INDEX idx_users_one_super
  ON users (is_super) WHERE is_super = true;

CREATE TABLE user_emails (
  email      TEXT PRIMARY KEY,           -- Unicidad GLOBAL gratuita
  user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  is_primary BOOLEAN NOT NULL DEFAULT false,
  added_at   TIMESTAMPTZ DEFAULT now()
);

-- UN solo primary por user — partial unique index.
CREATE UNIQUE INDEX idx_user_emails_one_primary
  ON user_emails (user_id) WHERE is_primary = true;

-- Indice para enumerar todos los emails de un user (auth audit, /auth/me).
CREATE INDEX idx_user_emails_user_id ON user_emails (user_id);

-- Empresas cliente. Cada organization tiene UN CEO.
CREATE TABLE organizations (
  id          SERIAL PRIMARY KEY,
  name        TEXT UNIQUE NOT NULL,
  ceo_user_id INT UNIQUE REFERENCES users(id),  -- 1:1 organization↔CEO
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE agents (
  id         SERIAL PRIMARY KEY,
  identifier TEXT UNIQUE NOT NULL,
  user_id    INT REFERENCES users(id),
  active     BOOLEAN DEFAULT true,
  last_seen  TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_keys (
  id         SERIAL PRIMARY KEY,
  key_hash   TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  user_id    INT REFERENCES users(id),
  expires_at TIMESTAMPTZ,
  active     BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 1.3 Workspaces, proyectos y permisos
-- ----------------------------------------------------------------------------
-- Workspace = departamento de una empresa cliente.
-- organization_id NULLABLE: workspaces sin organization son "del sistema",
-- accesibles solo por superuser. Workspaces con organization pertenecen a la
-- empresa cliente correspondiente y su CEO los ve todos.
CREATE TABLE workspaces (
  id              SERIAL PRIMARY KEY,
  organization_id INT REFERENCES organizations(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now(),
  -- name unico dentro de su organization. Para workspaces del sistema
  -- (organization_id IS NULL) PostgreSQL trata NULL!=NULL en UNIQUE, asi
  -- que esta constraint NO previene duplicados de workspaces sistema.
  -- El partial unique index abajo cierra ese hueco (deuda Tarea 1.1 #17).
  UNIQUE (organization_id, name)
);

-- Tarea 1.14 fix #17 (adv-code Tarea 1.9): partial unique index para que
-- workspaces del sistema (org_id NULL) tampoco tengan name duplicado.
CREATE UNIQUE INDEX idx_workspaces_system_unique_name
  ON workspaces (name)
  WHERE organization_id IS NULL;

CREATE TABLE workspace_leads (
  workspace_id INT REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id      INT REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE projects (
  id           SERIAL PRIMARY KEY,
  workspace_id INT REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  is_common    BOOLEAN DEFAULT false,
  created_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE (workspace_id, name)
);

CREATE TABLE project_members (
  project_id INT REFERENCES projects(id) ON DELETE CASCADE,
  user_id    INT REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (project_id, user_id)
);

-- Tarea 2.10 (consenso 5/5 B sala ecodb-consejo, 2026-05-08): rol "Jefe de
-- proyecto" / project_lead — autorizado por el Lead del workspace para ver
-- todas las memorias private del project (cuando expand_scope=true) y
-- gestionar el project con nivel intermedio entre worker y Lead. Simétrico a
-- workspace_leads un nivel abajo.
-- Gestión (POST/DELETE): super | CEO de la org del ws | Lead del ws.
-- NO project_lead se auto-asigna (anti-horizontal-escalation, observación
-- adv-seg Loop 1 Tarea 2.10).
CREATE TABLE project_leads (
  project_id INT REFERENCES projects(id) ON DELETE CASCADE,
  user_id    INT REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (project_id, user_id)
);

-- Tarea 2.10 (consenso adv-code + adv-seg): índices user_id en tablas de
-- roles + memories(user_id, visibility) — coste trivial ahora, doloroso
-- después cuando volumen multi-tenant lo exija.
CREATE INDEX IF NOT EXISTS idx_workspace_leads_user_id ON workspace_leads(user_id);
CREATE INDEX IF NOT EXISTS idx_project_leads_user_id ON project_leads(user_id);
-- idx_memories_user_visibility se crea más abajo tras CREATE TABLE memories.

CREATE TABLE teams (
  id         SERIAL PRIMARY KEY,
  name       TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE team_members (
  team_id INT REFERENCES teams(id) ON DELETE CASCADE,
  user_id INT REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (team_id, user_id)
);

CREATE TABLE team_resources (
  team_id    INT REFERENCES teams(id) ON DELETE CASCADE,
  project_id INT REFERENCES projects(id) ON DELETE CASCADE,
  PRIMARY KEY (team_id, project_id)
);

-- ----------------------------------------------------------------------------
-- 1.3.1 Identidad persistente de agentes (Tarea 1.15 plan v3 §5.2 ext)
-- ----------------------------------------------------------------------------
-- Schema (2026-05-08): persiste fragmentos de identidad de cada agente como dato de
-- primera clase del sistema. Permite que un cliente reconstruya un agente sin
-- depender del Claude system prompt o de ChromaDB original. La identidad NO es
-- una memoria — no decae, no participa en GAMR, no tiene workspace/project.
-- Por eso tabla separada y no `memories` con type='identidad'.
--
-- - `agent_id` FK al agente. ON DELETE CASCADE: si borras el agente, su
--   identidad se va con el.
-- - `organization_id` NULL = identidad shared/no atribuida a org concreta. INT =
--   identidad atada a esa org (multi-org VPS donde un mismo CEO tiene varias
--   organizaciones bajo su control y quiere segmentar identidades).
-- - `version` permite historial: la identidad de un agente puede evolucionar.
--   Cargar identidad vigente = WHERE version = MAX(version).
-- - `fragment_idx` ordinal de carga (0..N-1, compactado tras delete).
-- - UNIQUE NULLS NOT DISTINCT (PG16+): trata NULL como valor real para que
--   `(Eco, NULL, 1, 0)` no permita duplicado silencioso.
-- - SIN columna embedding en Fase 1: caso de uso es cargar todo por agente, no
--   busqueda semantica. Cuando llegue caso real (Fase 5+ probablemente), se
--   anade columna + `searchable BOOL DEFAULT FALSE` para excluirla del corpus
--   /search global (adv-seg cazo "embedding inversion oracle").
CREATE TABLE agent_identity (
  id              SERIAL PRIMARY KEY,
  agent_id        INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  organization_id INT REFERENCES organizations(id) ON DELETE CASCADE,
  version         INT NOT NULL DEFAULT 1,
  fragment_idx    INT NOT NULL,
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (agent_id, organization_id, version, fragment_idx)
);
CREATE INDEX idx_agent_identity_agent_org ON agent_identity (agent_id, organization_id, version);

-- ----------------------------------------------------------------------------
-- 1.4 Configuracion de tipos de memoria
-- ----------------------------------------------------------------------------
CREATE TABLE memory_type_config (
  type        TEXT PRIMARY KEY,
  base_weight REAL NOT NULL,
  decay_rate  REAL NOT NULL DEFAULT 0.0,
  decay_type  TEXT NOT NULL DEFAULT 'none'
);

INSERT INTO memory_type_config (type, base_weight, decay_rate, decay_type) VALUES
  ('acuerdo',        0.9, 0.0,  'none'),
  ('decision',       0.9, 0.0,  'none'),
  ('momento',        0.7, 0.02, 'slow'),
  ('descubrimiento', 0.7, 0.05, 'medium'),
  ('referencia',     0.6, 0.0,  'none'),
  ('observacion',    0.5, 0.05, 'medium'),
  ('tecnico',        0.5, 0.10, 'fast');

-- ----------------------------------------------------------------------------
-- 1.5 Memorias
-- ----------------------------------------------------------------------------
CREATE TYPE memory_type AS ENUM (
  'momento', 'decision', 'acuerdo', 'tecnico',
  'descubrimiento', 'observacion', 'referencia'
);

CREATE TYPE content_modality AS ENUM (
  'text', 'image', 'audio', 'document', 'video'
);

CREATE TYPE visibility AS ENUM ('public', 'private');

CREATE TABLE memories (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         INT REFERENCES users(id),
  agent_id        INT REFERENCES agents(id),
  workspace_id    INT REFERENCES workspaces(id) NOT NULL,
  project_id      INT REFERENCES projects(id) NOT NULL,
  type            memory_type NOT NULL,
  content_type    content_modality NOT NULL DEFAULT 'text',
  visibility      visibility NOT NULL DEFAULT 'public',
  content         TEXT NOT NULL,
  -- summary: campo de presentacion (no de dominio). Resumen compacto independiente
  -- del content (NO es truncado). Aniadido en Tarea 1.15 (migracion eco_memory)
  -- tras votacion 5/5 unanimidad C en sala ecodb-consejo el 2026-05-08.
  -- Criterio de schema: campo conocido + alta cobertura + user-facing → top-level
  -- (no JSONB metadata). Pydantic max_length=1000 + _no_null_bytes en API.
  summary         TEXT,
  embedding       vector(512),
  embedding_model TEXT DEFAULT 'jina-v4',
  media_path      TEXT,
  tags            TEXT[] NOT NULL DEFAULT '{}',
  weight          REAL NOT NULL DEFAULT 0.5,
  weight_base     REAL NOT NULL DEFAULT 0.5,
  access_count    INT DEFAULT 0,
  last_accessed   TIMESTAMPTZ,
  staleness       TEXT DEFAULT 'active'
                    CHECK (staleness IN ('active', 'stale', 'dormant', 'archived')),
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_memories_embedding ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
CREATE INDEX idx_memories_workspace    ON memories (workspace_id);
CREATE INDEX idx_memories_project      ON memories (project_id);
CREATE INDEX idx_memories_user         ON memories (user_id);
-- Tarea 2.10: índice compuesto para queries con filter visibility frecuente
-- (expand_scope y filtros user_id+private). Coste trivial, gains en multi-tenant.
CREATE INDEX idx_memories_user_visibility ON memories (user_id, visibility);
CREATE INDEX idx_memories_agent        ON memories (agent_id);
CREATE INDEX idx_memories_type         ON memories (type);
CREATE INDEX idx_memories_created      ON memories (created_at DESC);
CREATE INDEX idx_memories_weight       ON memories (weight DESC);
CREATE INDEX idx_memories_tags         ON memories USING gin (tags);
CREATE INDEX idx_memories_content_trgm ON memories
  USING gin (content gin_trgm_ops);
CREATE INDEX idx_memories_fulltext     ON memories
  USING gin (to_tsvector('spanish', content));

-- ----------------------------------------------------------------------------
-- 1.6 Grafo (nodos y tripletas — tablas relacionales de respaldo)
--     AGE gestiona el grafo activo en ecodb_graph. Estas tablas guardan los
--     mismos datos en forma relacional para queries SQL puras (FT search,
--     pg_trgm) y backup explicito.
-- ----------------------------------------------------------------------------
CREATE TABLE nodes (
  id          SERIAL PRIMARY KEY,
  name        TEXT UNIQUE NOT NULL,
  type        TEXT,
  description TEXT,
  embedding   vector(512),
  status      TEXT DEFAULT 'active'
                CHECK (status IN ('active', 'merged')),
  merged_into BIGINT REFERENCES nodes(id),
  created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE nodes ADD CONSTRAINT chk_no_self_merged_into
  CHECK (merged_into IS NULL OR merged_into != id);

CREATE TABLE triples (
  id          SERIAL PRIMARY KEY,
  -- F1 (verificador Loop 2): NOT NULL en subject_id y object_id. Sin esto, NULLs
  -- pasan el UNIQUE silenciosamente (NULL != NULL en PostgreSQL) y se cuelan
  -- triples fantasma sin sujeto/objeto que romperian Stage 4 del GAMR de forma
  -- impredecible. Una tripleta sin sujeto u objeto es semanticamente invalida
  -- para un knowledge graph.
  subject_id  INT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  predicate   TEXT NOT NULL,
  object_id   INT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  author      TEXT,
  -- Schema (2026-05-08): trazabilidad de tripletas como columnas top-level. fecha y origen son
  -- universales (99% origen, 55% fecha en el dataset migrado de eco_graph viejo + esperable
  -- en futuras tripletas de Fase 4 ingesta de documentos). document_id reservada como FK
  -- para Fase 4 — JSONB no soporta FK constraints. peso queda en metadata (45%, no se
  -- consulta por rango).
  fecha       DATE,
  origen      TEXT,
  document_id UUID,  -- FK a documents(id) anadida via ALTER al final del schema (orden de creacion)
  metadata    JSONB DEFAULT '{}'
              CHECK (pg_column_size(metadata) < 65536),  -- adv-seg: cap 64KB para evitar bloat / DoS via JSONB libre
  created_at  TIMESTAMPTZ DEFAULT now(),
  -- BC2 (adv-code): evitar aristas duplicadas que inflan shared_entities en GAMR Etapa 4.
  UNIQUE (subject_id, predicate, object_id)
);

CREATE TABLE predicate_embeddings (
  predicate  TEXT PRIMARY KEY,
  embedding  vector(512),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_triples_subject       ON triples (subject_id);
CREATE INDEX idx_triples_object        ON triples (object_id);
CREATE INDEX idx_triples_predicate     ON triples (predicate);
-- Indices partial para queries GAMR Etapa 6 (coherencia temporal) + auditoria por workflow.
-- Solo indexa filas con valor → indice mas pequeno + queries con WHERE fecha/origen IS NOT NULL
-- usan el indice. Recomendacion equipo consenso 2026-05-08.
CREATE INDEX idx_triples_fecha         ON triples (fecha)       WHERE fecha       IS NOT NULL;
CREATE INDEX idx_triples_origen        ON triples (origen)      WHERE origen      IS NOT NULL;
CREATE INDEX idx_triples_document_id   ON triples (document_id) WHERE document_id IS NOT NULL;
CREATE INDEX idx_nodes_merged          ON nodes (merged_into) WHERE status = 'merged';
CREATE INDEX idx_nodes_name_trgm       ON nodes USING gin (name gin_trgm_ops);
CREATE INDEX idx_nodes_embedding       ON nodes
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
CREATE INDEX idx_predicate_embeddings  ON predicate_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);  -- IC2 (adv-code): default ef_construction=64 da recall pobre.

-- ----------------------------------------------------------------------------
-- 1.7 Tabla puente memoria-entidad (SQL <-> AGE)
--     entity_node_id es el id() interno de AGE para nodos :Entity.
-- ----------------------------------------------------------------------------
CREATE TABLE memory_entity_links (
  memory_id      UUID REFERENCES memories(id) ON DELETE CASCADE,
  entity_node_id BIGINT NOT NULL,
  link_type      TEXT DEFAULT 'mentions',
  auto           BOOLEAN DEFAULT true,
  created_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (memory_id, entity_node_id)
);

CREATE INDEX idx_mel_entity ON memory_entity_links (entity_node_id);

-- ----------------------------------------------------------------------------
-- 1.8 Documentos
-- ----------------------------------------------------------------------------
CREATE TABLE documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- BC1 (adv-code): NOT NULL en workspace_id/project_id para alinear con memories
  -- y evitar que un documento sin project_id quede invisible al filtro de permisos.
  workspace_id  INT REFERENCES workspaces(id) NOT NULL,
  project_id    INT REFERENCES projects(id) NOT NULL,
  visibility    visibility NOT NULL DEFAULT 'public',
  uri           TEXT NOT NULL UNIQUE,  -- UA1 (adv-code): evitar doble ingesta del mismo path por watchdog.
  filename      TEXT NOT NULL,
  doc_type      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','processing','indexed','failed','deleted')),
  file_hash     TEXT,
  retry_count   INT NOT NULL DEFAULT 0,
  processing_started_at TIMESTAMPTZ,
  processing_metrics    JSONB,
  base_weight   REAL NOT NULL DEFAULT 0.7,
  trust_origin  TEXT DEFAULT 'manual',
  trust_tier    INT DEFAULT 1 CHECK(trust_tier BETWEEN 0 AND 3),
  content_fingerprint TEXT,
  document_version INT DEFAULT 1,
  supersedes_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
  reconciled    BOOLEAN DEFAULT false,
  last_indexed  TIMESTAMPTZ,
  last_modified TIMESTAMPTZ,
  metadata      JSONB DEFAULT '{}',
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE document_chunks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  content     TEXT NOT NULL,
  embedding   vector(512),
  section_path TEXT,
  metadata    JSONB DEFAULT '{}',
  tags        TEXT[] DEFAULT '{}',
  UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_doc_chunks_embedding ON document_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
CREATE INDEX idx_dc_fulltext ON document_chunks
  USING gin (to_tsvector('spanish', content));
CREATE INDEX idx_documents_uri        ON documents (uri);
CREATE INDEX idx_documents_workspace  ON documents (workspace_id);
CREATE INDEX idx_documents_project    ON documents (project_id);
-- FK triples.document_id → documents(id). Definida via ALTER porque triples se crea
-- antes que documents en este init.sql (orden historico del schema). Mantenemos la
-- FK explicita para enforcement DB-level (no solo aplicacion).
ALTER TABLE triples
  ADD CONSTRAINT fk_triples_document_id
  FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL;

ALTER TABLE documents ADD CONSTRAINT chk_no_self_supersede
  CHECK (supersedes_document_id IS NULL OR supersedes_document_id != id);
ALTER TABLE documents ADD CONSTRAINT chk_fingerprint_len
  CHECK (content_fingerprint IS NULL OR length(content_fingerprint) = 64);

-- ----------------------------------------------------------------------------
-- 1.9 Vinculos memoria-documento y documento-entidad
-- ----------------------------------------------------------------------------
CREATE TABLE memory_document_links (
  memory_id   UUID REFERENCES memories(id) ON DELETE CASCADE,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  link_type   TEXT DEFAULT 'source',
  confidence  REAL,
  validated   BOOLEAN DEFAULT false,
  PRIMARY KEY (memory_id, document_id)
);

CREATE TABLE document_entity_links (
  document_id    UUID REFERENCES documents(id) ON DELETE CASCADE,
  entity_node_id BIGINT NOT NULL,
  chunk_id       UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
  created_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (document_id, entity_node_id, chunk_id)
);

CREATE INDEX idx_del_entity ON document_entity_links (entity_node_id);

CREATE INDEX idx_mdl_memory ON memory_document_links (memory_id);
CREATE INDEX idx_dc_document_id ON document_chunks (document_id);

ALTER TABLE memory_document_links ADD CONSTRAINT chk_mdl_confidence_range
  CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);

-- ----------------------------------------------------------------------------
-- 1.9b Stop entities (Fase 4)
-- Entidades que NO generan nodos AGE ni document_entity_links.
-- Seed manual por Eco antes de pipeline ingesta.
-- ----------------------------------------------------------------------------
CREATE TABLE stop_entities (
  id              SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  reason          TEXT,
  created_by      INT NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE (name_normalized)
);

-- No explicit index needed: UNIQUE(name_normalized) creates implicit btree (BC3 adv-code)

-- ----------------------------------------------------------------------------
-- 1.9c Entity alias candidates (Fase 5)
-- ----------------------------------------------------------------------------
CREATE TABLE entity_alias_candidates (
  id SERIAL PRIMARY KEY,
  source_name TEXT NOT NULL,
  target_node_id BIGINT NOT NULL REFERENCES nodes(id),
  confidence REAL NOT NULL,
  occurrences INT DEFAULT 1,
  sample_contexts TEXT[],
  status TEXT DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'archived')),
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now(),
  reviewed_by INT REFERENCES users(id)
);

CREATE INDEX idx_eac_source_name ON entity_alias_candidates (source_name);
CREATE INDEX idx_eac_target_node ON entity_alias_candidates (target_node_id);
CREATE INDEX idx_eac_pending ON entity_alias_candidates (status) WHERE status = 'pending';
ALTER TABLE entity_alias_candidates ADD CONSTRAINT chk_confidence_range
  CHECK (confidence BETWEEN 0 AND 1);
ALTER TABLE entity_alias_candidates ADD CONSTRAINT chk_sample_contexts_len
  CHECK (sample_contexts IS NULL OR array_length(sample_contexts, 1) <= 20);

-- ----------------------------------------------------------------------------
-- 1.9d Entity merge log (Fase 5)
-- ----------------------------------------------------------------------------
CREATE TABLE entity_merge_log (
  id SERIAL PRIMARY KEY,
  source_node_id BIGINT NOT NULL,
  target_node_id BIGINT NOT NULL,
  target_original_id BIGINT NOT NULL,
  merged_by INT REFERENCES users(id),
  reason TEXT,
  merged_at TIMESTAMPTZ DEFAULT now(),
  undone_at TIMESTAMPTZ
);

CREATE INDEX idx_eml_source ON entity_merge_log (source_node_id);
CREATE INDEX idx_eml_target ON entity_merge_log (target_node_id);
ALTER TABLE entity_merge_log ADD CONSTRAINT chk_no_self_merge
  CHECK (source_node_id != target_node_id);

-- ----------------------------------------------------------------------------
-- 1.9e Related documents (Fase 5)
-- ----------------------------------------------------------------------------
CREATE TABLE related_documents (
  source_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  target_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  relation_type TEXT
    CHECK (relation_type IN ('duplicate', 'near_duplicate', 'revision_of', 'supersedes', 'derived_from')),
  similarity REAL,
  detected_at TIMESTAMPTZ DEFAULT now(),
  confirmed_by INT REFERENCES users(id),
  PRIMARY KEY (source_id, target_id)
);
CREATE INDEX idx_related_target ON related_documents (target_id);
ALTER TABLE related_documents ADD CONSTRAINT chk_no_self_relation
  CHECK (source_id != target_id);
ALTER TABLE related_documents ADD CONSTRAINT chk_similarity_range
  CHECK (similarity IS NULL OR similarity BETWEEN 0 AND 1);

-- ----------------------------------------------------------------------------
-- 1.10 Log de busquedas
-- ----------------------------------------------------------------------------
CREATE TABLE search_log (
  id            BIGSERIAL PRIMARY KEY,
  user_id       INT REFERENCES users(id),
  agent_id      INT REFERENCES agents(id),
  query_text    TEXT NOT NULL,
  query_type    TEXT,
  results_count INT NOT NULL DEFAULT 0,
  latency_ms    INT NOT NULL,
  failed        BOOLEAN DEFAULT false,
  project_ids   INT[],
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_search_log_created ON search_log (created_at DESC);

-- ----------------------------------------------------------------------------
-- 1.11 Preferencias de usuario
-- ----------------------------------------------------------------------------
CREATE TABLE user_preferences (
  user_id    INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  prefs      JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 1.12 Papelera y audit log
-- ----------------------------------------------------------------------------
CREATE TABLE trash (
  id              UUID PRIMARY KEY,
  original_table  TEXT NOT NULL,
  original_data   JSONB NOT NULL,
  deleted_by      INT REFERENCES users(id),
  deleted_at      TIMESTAMPTZ DEFAULT now(),
  retention_until TIMESTAMPTZ DEFAULT (now() + INTERVAL '90 days')
);

CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     INT REFERENCES users(id),
  agent_id    INT REFERENCES agents(id),
  action      TEXT NOT NULL,
  resource    TEXT NOT NULL,
  resource_id TEXT,
  details     JSONB DEFAULT '{}',
  ip_address  INET,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_user      ON audit_log (user_id);
CREATE INDEX idx_audit_created   ON audit_log (created_at DESC);
CREATE INDEX idx_audit_resource  ON audit_log (resource, resource_id);  -- RD1 (adv-code): query tipica filtra por (resource, resource_id).
CREATE INDEX idx_trash_retention ON trash (retention_until);

-- ----------------------------------------------------------------------------
-- 1.12.1 Función check_visibility — Tarea 2.10
-- ----------------------------------------------------------------------------
-- Resuelve si un actor puede ver una memoria, con o sin expand_scope=true.
-- Consenso 5/5 sala ecodb-consejo (patrón 11.19, segunda ronda):
-- - SQL function: lógica jerárquica en un sitio, testeable con SELECT directo.
-- - Nivel CONTEXTUAL: actor_level se resuelve POR MEMORIA (árbol ws/project),
--   no max global. Test BLOQUEANTE: CEO de org A NO ve private de org B.
-- - Runtime always: re-evalúa per-query, sin congelar creator_level en columna.
-- - expand_scope=true: override visibility por jerarquía estricta — actor con
--   nivel mayor que el creador EN EL ÁRBOL del creador ve la private.
-- - actor_level: super(4) | CEO de la org del ws(3) | Lead del ws(2) |
--   project_lead(1) | project_member(0) | none(-1).
-- - creator_level: igual resolución para memory.user_id.
CREATE OR REPLACE FUNCTION check_visibility(
  m_user_id INT, m_visibility TEXT, m_workspace_id INT, m_project_id INT,
  a_id INT, a_is_super BOOLEAN, a_is_ceo BOOLEAN, a_org_id INT,
  a_lead_ws INT[],
  expand_scope BOOLEAN
) RETURNS BOOLEAN
LANGUAGE SQL STABLE AS $$
  WITH ws_info AS (
    SELECT organization_id FROM workspaces WHERE id = m_workspace_id
  ),
  actor_level AS (
    SELECT CASE
      WHEN a_is_super THEN 4
      WHEN a_is_ceo AND a_org_id IS NOT NULL AND (SELECT organization_id FROM ws_info) = a_org_id THEN 3
      WHEN m_workspace_id = ANY(a_lead_ws) THEN 2
      WHEN EXISTS(SELECT 1 FROM project_leads WHERE project_id = m_project_id AND user_id = a_id) THEN 1
      WHEN EXISTS(SELECT 1 FROM project_members WHERE project_id = m_project_id AND user_id = a_id) THEN 0
      ELSE -1
    END AS lvl
  ),
  creator_level AS (
    SELECT CASE
      WHEN (SELECT is_super FROM users WHERE id = m_user_id) THEN 4
      WHEN (SELECT is_ceo FROM users WHERE id = m_user_id)
           AND (SELECT organization_id FROM ws_info) = (SELECT id FROM organizations WHERE ceo_user_id = m_user_id) THEN 3
      WHEN EXISTS(SELECT 1 FROM workspace_leads WHERE workspace_id = m_workspace_id AND user_id = m_user_id) THEN 2
      WHEN EXISTS(SELECT 1 FROM project_leads WHERE project_id = m_project_id AND user_id = m_user_id) THEN 1
      ELSE 0
    END AS lvl
  )
  SELECT
    a_is_super
    OR a_id = m_user_id
    OR (m_visibility = 'public' AND (SELECT lvl FROM actor_level) >= 0)
    OR (m_visibility = 'public' AND EXISTS(
          SELECT 1 FROM projects p WHERE p.id = m_project_id AND p.is_common = true
        ) AND m_workspace_id IN (
          SELECT DISTINCT pp.workspace_id FROM project_members pm
          JOIN projects pp ON pp.id = pm.project_id
          WHERE pm.user_id = a_id
        ))
    OR (m_visibility = 'public' AND m_project_id IN (
          SELECT tr.project_id FROM team_resources tr
          JOIN team_members tm ON tm.team_id = tr.team_id
          WHERE tm.user_id = a_id
        ))
    OR (m_visibility = 'private' AND NOT expand_scope
        AND a_is_ceo AND a_org_id IS NOT NULL
        AND (SELECT organization_id FROM ws_info) = a_org_id)
    OR (m_visibility = 'private' AND expand_scope
        AND (SELECT lvl FROM actor_level) > (SELECT lvl FROM creator_level)
        AND (SELECT lvl FROM actor_level) >= 0);
$$;


-- ----------------------------------------------------------------------------
-- 1.13 entity_dictionary — diccionario configurable de overrides para GLiNER
-- ----------------------------------------------------------------------------
-- Architectural decision (2026-05-09):
--
-- Arquitectura E lookup-first GLiNER:
--   1. Carga del diccionario al arranque uvicorn (cache RAM, lifespan FastAPI).
--   2. Helper `_match_dictionary(text, dict_cache)` en gliner_service.py busca
--      matches del diccionario en el texto contra `name_normalized`.
--   3. Spans matcheados → tipo del diccionario, sin GLiNER. Reemplazo con
--      espacios mismo largo (NO eliminacion — preserva offsets).
--   4. GLiNER procesa el texto residual.
--   5. Merge con provenance source="dictionary"|"gliner".
--
-- Regla longest-match wins: ordenar dict_entries por len(name) DESC antes del
-- bucle. Longer entries match before shorter ones.
--
-- Word-boundary regex \b{name}\b por entry — without it short names match
-- inside longer words (falso positivo silencioso).
--
-- Single-tenant mode: tabla simple sin organization_id. Cuando llegue cliente real:
--   ALTER TABLE entity_dictionary ADD COLUMN organization_id INT REFERENCES organizations(id);
-- Migracion trivial, no rediseno.
--
-- Permisos: super-only en endpoints REST /admin/entity-dictionary.
CREATE TABLE entity_dictionary (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    notes TEXT,
    created_by INT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(name_normalized)
);
CREATE INDEX idx_ed_name ON entity_dictionary (name_normalized);

-- Example entity dictionary seed. These override GLiNER classifications
-- for terms that are commonly misclassified (polysemy, rare proper nouns).
-- name_normalized is computed as lower(unaccent(name)) in Python, matching
-- user text normalization.
INSERT INTO entity_dictionary (name, name_normalized, entity_type) VALUES
    ('Anthropic',      'anthropic',       'organizacion'),
    ('OpenAI',         'openai',          'organizacion'),
    ('PostgreSQL',     'postgresql',      'tecnologia'),
    ('Docker',         'docker',          'tecnologia'),
    ('FastAPI',        'fastapi',         'producto'),
    ('Jina v4',        'jina v4',         'producto'),
    ('GLiNER',         'gliner',          'producto'),
    ('ChromaDB',       'chromadb',        'producto'),
    ('Docling',        'docling',         'producto'),
    ('EcoDB',          'ecodb',           'proyecto');


-- ----------------------------------------------------------------------------
-- Fase B — injection_telemetry (B.1)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS injection_telemetry (
  id SERIAL PRIMARY KEY,
  injection_id TEXT NOT NULL UNIQUE,
  memory_ids UUID[] NOT NULL,
  scores REAL[],
  agent_identifier TEXT,
  session_id TEXT,
  prompt_hash TEXT,
  status TEXT DEFAULT 'injected' CHECK (status IN ('injected', 'used', 'ignored')),
  use_score REAL,
  novel_entities TEXT[],
  created_at TIMESTAMPTZ DEFAULT now(),
  evaluated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_it_status ON injection_telemetry (status);
CREATE INDEX IF NOT EXISTS idx_it_created ON injection_telemetry (created_at DESC);

-- Fase B.3 — corpus_vocabulary (BM25 query expansion)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corpus_vocabulary (
  term TEXT PRIMARY KEY,
  embedding vector(512),
  doc_freq INT DEFAULT 1,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cv_embedding ON corpus_vocabulary
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=200);

-- ----------------------------------------------------------------------------
-- Seed data (bootstrap)
-- ----------------------------------------------------------------------------

-- Default superuser. After first boot, create a real admin account via the API
-- and update this user's details, or replace this seed entirely.
INSERT INTO users (name, is_super, is_ceo) VALUES ('admin', true, false);

INSERT INTO user_emails (email, user_id, is_primary) VALUES
  ('admin@example.com', 1, true);

-- Default workspace and project.
INSERT INTO workspaces (name) VALUES ('default');
INSERT INTO projects (workspace_id, name, is_common)
  VALUES (1, 'general', true);

INSERT INTO project_members (project_id, user_id) VALUES (1, 1);

-- Bootstrap agent. Additional agents are created via the API
-- (POST /admin/agents or through the MCP guardar_memoria tool).
INSERT INTO agents (identifier, user_id) VALUES
  ('default', 1), ('SIN_AUTOR', 1);
