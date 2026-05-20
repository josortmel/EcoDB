# Changelog

All notable changes to EcoDB are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] — 2026-05-19

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
