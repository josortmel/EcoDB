<p align="center">
  <strong>EcoDB</strong>
</p>

<p align="center">
  Collective AI memory infrastructure.<br>
  Multiple agents, teams, and projects — one governed knowledge base.
</p>

<p align="center">
  <a href="https://github.com/josortmel/ecodb/releases/tag/v1.0.0"><img src="https://img.shields.io/badge/release-v1.0.0-orange" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776ab" alt="Python">
  <img src="https://img.shields.io/badge/MCP-22%2B%20tools-0d9488" alt="MCP Tools">
  <img src="https://img.shields.io/badge/docker-compose-2496ed" alt="Docker">
</p>

---

Personal memory tools help one agent remember one session. EcoDB is the step beyond: a shared memory system where **multiple agents** store, search, connect, and govern knowledge across teams and projects.

Your agents remember what they learned yesterday. They find connections through a knowledge graph. They flag contradictions. They share insights without you copy-pasting context between sessions.

**In production since May 2026.** Built by [Eco Consulting](https://ecoconsultingia.com).

## Why not just vector search?

Standard RAG retrieves by cosine similarity. That works for simple recall — but falls apart when you need:

| Problem | Vector search | EcoDB GAMR |
|---------|:---:|:---:|
| "What's connected to X?" | Doesn't know | Graph traversal (Apache AGE) |
| Latest decision vs. stale one | Treats them equally | Temporal freshness scoring |
| Two memories that contradict | Returns both silently | Detects and flags contradictions |
| Text query finding an image | Not possible | Cross-modal search (text ↔ image) |
| Agent A's notes vs. Agent B's | No distinction | Governed visibility by workspace/project |

EcoDB's **GAMR engine** (Graph-Augmented Memory Retrieval) combines **8 scoring stages** into a single pipeline: semantic similarity, BM25 full-text, knowledge graph expansion, temporal freshness, memory weight, trust tier decay, contradiction detection, and cross-modal matching.

### Benchmarks

Production dataset — 1400+ memories, 60 queries ([methodology and scripts](eval/)):

| Metric | EcoDB GAMR | Typical RAG (cosine only) |
|--------|:---------:|:------------------------:|
| **R@5** | **0.56** | ~0.30–0.40 |
| **MRR** | **0.39** | ~0.20–0.30 |
| **Multimodal R@5** | **0.70** | N/A |

GAMR outperforms pure vector search because it combines 6 independent signals. The knowledge graph and temporal scoring surface memories that cosine similarity alone would miss.

## Features

### Search — GAMR Engine
- 8-stage pipeline: semantic (pgvector HNSW) → BM25 → graph expansion (Apache AGE) → freshness → weight → trust → contradiction detection → cross-modal
- Cross-modal: text queries find image memories and vice versa
- Configurable via feature flags (BM25, HyDE, trust tiers)

### Knowledge Graph
- Apache AGE — Cypher queries inside PostgreSQL, no separate database
- Automatic entity extraction via GLiNER NER
- Entity linking with dictionary-first lookup
- Graph traversal: neighbors, shortest path, fuzzy node search, co-occurrence analysis

### Document Ingestion
- Pipeline: parse → chunk (960 tokens) → NER → embed → graph link
- PDF, DOCX, PPTX (via Docling), audio (via Whisper)
- Async processing with LISTEN/NOTIFY and SSE status events

### Agent Identities
- Ordered narrative fragments per agent — not metadata, but identity
- Version history for identity evolution
- Multi-agent support with governed visibility (workspace/project scoping)

### Memory System
- 7 memory types: momento, decision, acuerdo, tecnico, descubrimiento, observacion, referencia
- Automatic embedding (Jina v4, 512-dim Matryoshka)
- Soft delete with recycle bin, weight system with semantic attenuation
- Multimodal: text and image storage with cross-modal retrieval

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  MCP Client │────▶│  MCP Server │────▶│    REST API      │
│  (any host) │     │  (protocol) │     │   (FastAPI)      │
└─────────────┘     └─────────────┘     └────────┬─────────┘
                                                  │
                    ┌─────────────────────────────┼──────────────┐
                    │                             │              │
              ┌─────▼─────┐  ┌───────────┐  ┌────▼────┐  ┌─────▼─────┐
              │ PostgreSQL │  │ Embeddings│  │  NER    │  │   LLM     │
              │ + pgvector │  │ (Jina v4) │  │(GLiNER) │  │(llama.cpp)│
              │ + AGE      │  └───────────┘  └─────────┘  └───────────┘
              └────────────┘
```

**Two interfaces — same data:**

- **REST API** — 30+ endpoints with JWT auth, full CRUD, interactive docs at `/docs`
- **MCP Server** — 22+ tools via Model Context Protocol. Works with any MCP host (Claude Code, Cursor, Windsurf, custom clients). SSE or stdio transport.

**Six Docker services:**

| Service | Role | Size |
|---------|------|-----:|
| `postgres` | Storage + vector index + knowledge graph | 640 MB |
| `api` | FastAPI, GAMR engine, auth, CRUD | 10 GB |
| `embeddings` | Jina v4 embedding model (GPU) | 10 GB |
| `ner` | GLiNER named entity recognition | 8.3 GB |
| `mcp` | MCP protocol server | 280 MB |
| `llm` | llama.cpp + Qwen 2.5 3B (optional) | 2.2 GB |

## Quick Start

```bash
git clone https://github.com/josortmel/ecodb
cd ecodb
./scripts/setup.sh          # generates .env, verifies dependencies
docker compose up -d         # first boot downloads models (~35 GB)
```

Monitor first boot (model downloads take time):

```bash
docker compose logs -f embeddings ner    # wait for "model loaded" / "ready"
docker compose ps                        # all services should show "healthy"
```

Generate your API key:

```bash
docker exec ecodb-api python bootstrap_first_apikey.py
# Add to .env: ECODB_API_KEY=ecodb_...
docker compose restart mcp
```

**Optional profiles:**

```bash
docker compose --profile with-ingestion up -d    # PDF, DOCX, audio ingestion
docker compose --profile with-llm up -d          # local LLM for classification
```

### Requirements

- Docker with Compose v2
- NVIDIA GPU with CUDA drivers
- ~35 GB disk space

## MCP Tools

Connect any MCP-compatible client:

```json
{
  "mcpServers": {
    "ecodb": {
      "type": "sse",
      "url": "http://localhost:8091/sse"
    }
  }
}
```

| Tool | What it does |
|------|-------------|
| `buscar` | GAMR search — 8-stage semantic + graph + temporal scoring |
| `buscar_recientes` | Recent memories with filters (agent, tags, date range) |
| `guardar_memoria` | Store memory (auto-embeds, auto-extracts entities, auto-links graph) |
| `leer_memoria` | Read a memory by ID |
| `borrar_memoria` | Soft-delete to recycle bin |
| `guardar_tripleta` | Add relationship to knowledge graph |
| `guardar_tripletas_lote` | Batch add triples (max 100) |
| `vecinos` | Graph neighbors at depth N |
| `camino_entre` | Shortest path between two nodes |
| `buscar_nodos` | Fuzzy search nodes by name |
| `borrar_tripleta` | Remove a graph relationship |
| `estado_grafo` | Graph statistics (nodes, edges, predicates) |
| `cargar_identidad` | Load agent identity (ordered narrative fragments) |
| `guardar_identidad` | Save agent identity snapshot |
| `ver_imagen` | Retrieve embedded image |
| `registrar_documento` | Register document for ingestion |
| `estado_documento` | Check ingestion pipeline status |
| `buscar_en_documento` | Search within a specific document |
| `leer_documento` | Read document content |
| `listar_documentos` | List registered documents |
| `reindexar_documento` | Re-index a document |
| `desvincular_documento` | Unlink a document |

## Documentation

- [`docs/architecture/`](docs/architecture/) — System briefs: governance, ingestion, intelligence, product design
- [`eval/`](eval/) — Benchmark framework and golden set evaluation
- [`CHANGELOG.md`](CHANGELOG.md) — Version history

## Development

```bash
# Tests (requires postgres on port 5435)
cd api && python -m pytest tests/ -v

# Type check
cd api && python -m mypy .

# Run API locally for debugging
docker compose up postgres embeddings -d
cd api && uvicorn main:app --reload --port 8080
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal, educational, and noncommercial use. Commercial deployment requires a license from [Eco Consulting](https://ecoconsultingia.com).

Third-party dependencies: [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES)

## Maintainers

Built by [Eco Consulting](https://ecoconsultingia.com) — AI consulting for SMEs, based in Seville.

- [@josortmel](https://github.com/josortmel)
- [@EcoConsulting](https://github.com/EcoConsulting)
