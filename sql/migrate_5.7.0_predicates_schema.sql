-- 5.7.0 (#1362): the predicate vocabulary tables, which the API uses (graph.py: predicate resolution;
-- admin.py: get_graph_vocabulary and the predicates CRUD) but which NO migration ever created. They come
-- from before the first commit of the repo (Fase 3b) and only existed in databases made back then: a fresh
-- install (a new user of the public repo, the test database, CI) had no such tables, and the vocabulary
-- endpoint died with «relation "predicates_canonical" does not exist». Found by the first CI run.
--
-- Schema copied from production with `pg_dump -s` (23-nov-2026), same constraint and index names.
-- Idempotent: on a database that already has the tables (the family's), nothing changes.
-- Only the SCHEMA: the vocabulary itself (the approved predicates and their aliases) is data, and a new
-- install starts empty; predicates are added with the admin endpoints.
BEGIN;

CREATE TABLE IF NOT EXISTS predicates_canonical (
    name text NOT NULL,
    cluster text NOT NULL,
    ontology_layer text NOT NULL,
    domain text,
    description text,
    "symmetric" boolean DEFAULT false NOT NULL,
    inverse_of text,
    transitive boolean DEFAULT false NOT NULL,
    domain_types text[] DEFAULT '{}'::text[] NOT NULL,
    range_types text[] DEFAULT '{}'::text[] NOT NULL,
    authority_agents text[] DEFAULT '{}'::text[] NOT NULL,
    state text DEFAULT 'approved'::text NOT NULL,
    deprecated_since timestamp with time zone,
    replaced_by text,
    embedding vector(512),
    embedding_model text DEFAULT 'jina-v4'::text,
    embedding_version text,
    embedding_updated timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT predicates_canonical_pkey PRIMARY KEY (name),
    CONSTRAINT predicates_canonical_ontology_layer_check
        CHECK (ontology_layer = ANY (ARRAY['core'::text, 'domain'::text])),
    CONSTRAINT predicates_canonical_state_check
        CHECK (state = ANY (ARRAY['experimental'::text, 'candidate'::text, 'approved'::text, 'deprecated'::text,
                                  'archived'::text, 'forbidden'::text])),
    CONSTRAINT predicates_canonical_inverse_of_fkey
        FOREIGN KEY (inverse_of) REFERENCES predicates_canonical(name) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT predicates_canonical_replaced_by_fkey
        FOREIGN KEY (replaced_by) REFERENCES predicates_canonical(name)
);
CREATE INDEX IF NOT EXISTS idx_pc_cluster ON predicates_canonical USING btree (cluster);
CREATE INDEX IF NOT EXISTS idx_pc_embedding ON predicates_canonical
    USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='200');
CREATE INDEX IF NOT EXISTS idx_pc_state ON predicates_canonical USING btree (state);

CREATE TABLE IF NOT EXISTS predicate_aliases (
    alias text NOT NULL,
    canonical text NOT NULL,
    domain text NOT NULL,
    auto_learned boolean DEFAULT false,
    confirmations integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT predicate_aliases_pkey PRIMARY KEY (alias, domain),
    CONSTRAINT predicate_aliases_canonical_fkey FOREIGN KEY (canonical) REFERENCES predicates_canonical(name)
);

CREATE TABLE IF NOT EXISTS pending_predicates (
    predicate text NOT NULL,
    frequency integer DEFAULT 1,
    status text DEFAULT 'pending'::text NOT NULL,
    reviewed_by integer,
    first_seen timestamp with time zone DEFAULT now(),
    last_seen timestamp with time zone DEFAULT now(),
    archive_after timestamp with time zone DEFAULT (now() + '90 days'::interval),
    sample_triples jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT pending_predicates_pkey PRIMARY KEY (predicate),
    CONSTRAINT pending_predicates_status_check
        CHECK (status = ANY (ARRAY['pending'::text, 'promoted'::text, 'archived'::text, 'rejected'::text])),
    CONSTRAINT pending_predicates_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES users(id)
);

COMMIT;
