-- EcoDB Demo Dataset — Meta-Circular Tutorial
DO $$
DECLARE aid INT;
BEGIN
  INSERT INTO agents (identifier, user_id) VALUES ('tutorial', 1) ON CONFLICT (identifier, user_id) DO NOTHING;
  SELECT id INTO aid FROM agents WHERE identifier = 'tutorial' AND user_id = 1;

  INSERT INTO memories (user_id, agent_id, type, content, weight, visibility, workspace_id, project_id) VALUES
    (1, aid, 'tecnico', 'EcoDB stores memories with semantic embeddings (pgvector), a knowledge graph (Apache AGE), and full-text search (BM25). The GAMR search engine combines all three signals in 8 stages.', 0.9, 'public', 1, 1),
    (1, aid, 'decision', 'GAMR scoring uses multiplicative composition: semantic_score * (1 + graph_bonus) * freshness_factor * weight_factor.', 0.9, 'public', 1, 1),
    (1, aid, 'descubrimiento', 'EcoDB supports multimodal search: text queries find image memories and vice versa via Jina v4 cross-modal alignment.', 0.7, 'public', 1, 1),
    (1, aid, 'tecnico', 'Agent identities are stored as ordered fragments. Use cargar_identidad to load all fragments in narrative order.', 0.8, 'public', 1, 1),
    (1, aid, 'observacion', 'The knowledge graph uses Apache AGE for Cypher queries. Use guardar_tripleta to add knowledge, vecinos to explore, camino_entre to find paths.', 0.7, 'public', 1, 1),
    (1, aid, 'tecnico', 'EcoDB runs as 5 Docker services: postgres, embeddings (Jina v4), api (FastAPI + GAMR), mcp (MCP protocol), and optionally worker (document ingestion).', 0.5, 'public', 1, 1),
    (1, aid, 'tecnico', 'The MCP server exposes 22+ tools via Model Context Protocol. Any MCP-compatible host can connect.', 0.5, 'public', 1, 1),
    (1, aid, 'decision', 'Memory weight is attenuated by semantic relevance. High-weight + low-match scores lower than medium-weight + high-match.', 0.8, 'public', 1, 1),
    (1, aid, 'tecnico', 'Document ingestion: parse (Docling/Whisper) → chunk (960 tokens) → NER (GLiNER) → embed (Jina v4) → graph. Triggered via LISTEN/NOTIFY.', 0.7, 'public', 1, 1),
    (1, aid, 'observacion', 'Trust tiers decay memory weight by type: decisions decay slowly, technical notes faster, observations fastest.', 0.7, 'public', 1, 1);

  INSERT INTO triples (subject, predicate, object, user_id) VALUES
    ('EcoDB', 'uses', 'PostgreSQL', 1), ('EcoDB', 'uses', 'pgvector', 1),
    ('EcoDB', 'uses', 'Apache AGE', 1), ('EcoDB', 'uses', 'Jina v4', 1),
    ('EcoDB', 'uses', 'GLiNER', 1), ('EcoDB', 'has_component', 'GAMR Search Engine', 1),
    ('EcoDB', 'has_component', 'MCP Server', 1), ('EcoDB', 'has_component', 'Document Ingestion Pipeline', 1),
    ('GAMR Search Engine', 'has_stage', 'Semantic Search', 1),
    ('GAMR Search Engine', 'has_stage', 'Graph Expansion', 1),
    ('GAMR Search Engine', 'has_stage', 'BM25 Full-Text', 1),
    ('MCP Server', 'implements', 'Model Context Protocol', 1),
    ('Document Ingestion Pipeline', 'uses', 'GLiNER', 1),
    ('pgvector', 'provides', 'HNSW Index', 1),
    ('Apache AGE', 'provides', 'Cypher Queries', 1)
  ON CONFLICT DO NOTHING;
END $$;
