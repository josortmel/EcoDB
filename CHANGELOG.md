# Changelog

All notable changes to EcoDB are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.8.6] — 2026-05-31

### Security
- **Graph discovery permission bypass** (`search.py` GC1): `check_visibility()` now applied when fetching graph-discovered memories — workspace scoping, CEO status, and lead permissions were previously bypassed (C1+H1)
- **MCP server crash on validate_link**: `validate_link` tool now wrapped in try/except; unhandled `RuntimeError` previously crashed the entire MCP server (C8)
- **IDOR oracle fix — validate_link API** (`memories.py`): missing memory returns 403 instead of 404, preventing existence enumeration (VS2)
- **IDOR oracle fix — unarchive_memory API** (`memories.py`): same fix — 403 instead of 404 for missing memories (VS1)
- **Path traversal in validate_link MCP tool**: UUID format validated before use; `quote()` now uses `safe=''` to encode all special characters including `/` (VS3)

### Infrastructure
- **MCP media volume mounted** (`docker-compose.yml`): MCP service now has `ecodb_media` volume mounted for `view_image` and image save support (C2)
- **MCP startup without API key**: `ECODB_API_KEY` gets empty default `:-` so MCP starts on first boot before key is generated (C7)
- **MCP media volume writable**: changed from `:ro` to `:rw` — required for `save_memory(image_path=...)` (BC1)
- **Backup/restore container name**: default corrected to `ecodb-postgres` in `backup.sh` and `restore.sh` (C3+C10)
- **NER version pinning** (`ner/Dockerfile`): `fastapi==0.118.0`, `uvicorn[standard]==0.40.0`, `gliner==0.2.26` — prevents rebuild drift (C4)
- **NER user/group standardized** (`ner/Dockerfile`): dedicated `nergroup` GID 1001, `neruser` UID 1000 — consistent with api/embeddings services (C5+VB1)
- **MCP dependency cap**: `mcp[cli]>=1.0.0,<2.0.0` prevents accidental major-version upgrade (C6)

### Robustness
- **search() input validation**: `limit` (1–100) and `deep_factor` (1–10) validated before API proxy (H13)
- **search_recent() tag param**: corrected `tag` → `tags` to match API contract (H14)
- **AGE hop retry**: `expand_by_graph` uses `continue` instead of `break` — hop=2 still attempted if hop=1 fails (H2)
- **AGE node creation race**: `_ensure_node` wraps fallback `_age_create` in try/except for defense-in-depth against concurrent duplicate creation (H4)
- **Worker stuck document recovery**: `recover_stuck_documents()` runs at worker startup — resets or fails documents stuck in `processing` after a process crash (H5)

### Documentation
- README: MCP tool count updated to 32 (was 22+)
- README: stdio transport config example added
- Spanish runtime error strings translated to English (B6)
- `backup.sh` / `restore.sh` header comments corrected to `ecodb-postgres` (IC2+OBS1)
- `json.dumps` calls in `search()` use `ensure_ascii=False` consistently (IC4)

## [0.8.5] — 2026-05-27

### Added
- **10-stage GAMR pipeline** — cross-encoder reranker as Etapa 10 (MiniLM-L-6-v2, SHA-pinned, fail-closed)
- **UltraSearch** — `deep_factor` parameter in search API (default=2, max=10). Multiplies internal candidate pool without changing result count. `search(limit=5, deep_factor=4)` returns 5 results with K=20 quality
- **MAX_FETCH_K=200** hard cap prevents DoS amplification via deep_factor
- **Reranker model allowlist** — only pre-approved models can load (supply chain protection)
- **Reranker safetensors enforcement** — prevents pickle RCE via model weights
- **Chunked benchmark scripts** — `run_benchmark_chunked.py` (5-turn windows, overlap 1, session dedup) and `run_benchmark_query_only.py` (K ablation without re-ingestion)
- Differentiated GAMR freshness weights by query type (factual/contextual=0.08, historical=0.02, analytical=0.05)

### Changed
- **All 32 MCP tools renamed from Spanish to English** — `buscar`→`search`, `guardar_memoria`→`save_memory`, `vecinos`→`neighbors`, etc. Breaking change for existing CLAUDE.md references (all updated)
- GAMR_WEIGHTS_BM25 dict now actually connected to `compute_composite_score` (was dead code)
- Reranker pre-cached in Docker image with SHA pin (eliminates first-request download delay)
- Content truncated to 2000 chars before cross-encoder (prevents CPU spike on large memories)

### Fixed
- **GLiNER/NER in search path** — entity extraction was silently failing (bare `except` swallowing errors). Now logs WARNING and degrades gracefully
- UltraSearch limit enforcement — results count now exactly matches `limit` after graph_discovery and document chunk appends
- `deep_factor` correctly wired to SQL LIMIT (was computed but not used)
- Dockerfile pre-cache SHA matches runtime revision (HF cache key mismatch caused re-download)
- Dockerfile cache file ownership (pre-cache ran as root, apiuser couldn't write metadata)

### Benchmarks (LoCoMo, 10 conversations, ~1982 queries)
- Baseline (monolithic sessions): R@5=0.769, R@10=0.894
- P1 reranker (no chunking): R@5=0.793, R@1=0.578
- **Chunked K=20: R@5=0.922, R@10=0.959** (+15.3pp from chunking alone)
- Chunked K=10: R@5=0.906, R@10=0.931
- Chunked K=5: R@5=0.914, R@10=0.914

## [0.8.1] — 2026-05-21

### Fixed
- Media path validation broken after public release sanitization — `ver_imagen` and inline images in `buscar` failed with "media_path outside of media store"
- Hardcoded `C:\EcoDB\media` replaced with project-relative default (`<project>/media/`)
- Path traversal vulnerability in worker document validation — `startswith(allowed + "/")` replaced with `pathlib.is_relative_to()`
- Worker bridge empty-string trap — `WINDOWS_MEDIA_PREFIX=""` caused `startswith("")` to match all URIs
- Worker bridge forward-slash mismatch — separate handling for backslash and forward-slash URI variants
- Docker MCP container missing `ECODB_MEDIA_DIR` — project-relative default resolved to `/media` instead of `/app/media`

### Changed
- `setup.sh` now creates `media/` directory during bootstrap
- `.env.example` documents `ECODB_MEDIA_DIR` and `WINDOWS_MEDIA_PREFIX` for native MCP deployments

## [0.8.0] — 2026-05-19

First public release. EcoDB has been in production use since May 2026.

### Core
- PostgreSQL 16 + pgvector (HNSW) + Apache AGE knowledge graph
- GAMR search engine: 8-stage scoring pipeline (semantic, BM25, graph, freshness, weight, trust tiers, contradiction detection, cross-modal)
- JWT authentication with API key hashing (bcrypt + pepper)
- Role-based access: superuser, CEO, workspace lead, project member
- Rate limiting per endpoint category

### Memory System
- CRUD for memories with 7 types (momento, decision, acuerdo, tecnico, descubrimiento, observacion, referencia)
- Automatic embedding via Jina v4 (512-dim, Matryoshka)
- Multimodal: text and image memories with cross-modal search
- Soft delete with recycle bin
- Weight system with semantic attenuation

### Knowledge Graph
- Apache AGE for Cypher queries within PostgreSQL
- Automatic entity extraction (GLiNER NER)
- Entity linking with dictionary-first lookup
- Co-occurrence analysis, graph discovery mode
- Auto-sync triggers (SQL → AGE)

### Document Ingestion
- Pipeline: parse → chunk → NER → embed → graph
- PDF, DOCX, PPTX via Docling; audio via Whisper
- 960-token chunks, GLiNER sub-chunking
- LISTEN/NOTIFY async processing
- SSE event broadcasts for real-time status

### MCP Server
- 22+ tools via Model Context Protocol (SSE transport)
- Compatible with any MCP host (Claude Code, Cursor, Windsurf, etc.)
- Context injection for agent onboarding

### Agent Identities
- Ordered narrative fragments per agent
- Version history for identity evolution
- Multi-agent support with access scoping

### Infrastructure
- Docker Compose with 6 services
- GPU-accelerated embeddings (NVIDIA CUDA)
- Bootstrap script with automatic secret generation
- Optional demo dataset (meta-circular tutorial)
- Feature flags for GAMR components (BM25, HyDE, trust tiers, etc.)
