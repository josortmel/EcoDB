# EcoDB

Collective AI memory infrastructure for organizations. Multi-agent semantic memory with knowledge graph, 8-stage GAMR search engine, and document ingestion pipeline.

Personal AI memory systems serve one user, one agent, one session. EcoDB is the step to **collective memory** — multiple agents, teams, and projects sharing a governed knowledge base with semantic search, graph reasoning, and temporal awareness.

## Features

**GAMR Search Engine (8 stages)**
- Semantic similarity (pgvector HNSW), BM25 full-text, knowledge graph expansion (Apache AGE)
- Temporal freshness scoring, trust tier decay, weight attenuation by relevance
- Contradiction detection across memories
- Cross-modal: text queries find image memories and vice versa

**Knowledge Graph**
- Apache AGE (PostgreSQL extension) — Cypher queries on your data
- Automatic entity extraction via GLiNER NER
- Entity linking, co-occurrence analysis, graph discovery mode
- Navigate with `vecinos`, `camino_entre`, `buscar_nodos`

**Document Ingestion**
- Pipeline: parse → chunk → NER → embed → graph (LISTEN/NOTIFY triggered)
- Supports PDF, DOCX, PPTX (via Docling), audio (via Whisper)
- 960-token chunks with GLiNER sub-chunking for entity extraction

**Agent Identities**
- Ordered narrative fragments per agent — not just metadata, but identity
- Multi-agent support with governed visibility (workspace/project scoping)

**Two Interfaces**
- **REST API** — 30+ endpoints, JWT auth, full CRUD for memories, documents, graph, agents
- **MCP Server** — 22+ tools via the Model Context Protocol standard. Works with any MCP-compatible host (Claude Code, Cursor, Windsurf, custom clients)

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

Six Docker services:

| Service | What it does | Image size |
|---------|-------------|-----------|
| `postgres` | Data storage + vector index + knowledge graph | ~640 MB |
| `embeddings` | Jina v4 embedding model (local, GPU-accelerated) | ~10 GB |
| `api` | FastAPI server, GAMR engine, auth, CRUD | ~10 GB |
| `mcp` | MCP protocol server (connects to API) | ~280 MB |
| `ner` | GLiNER named entity recognition | ~8.3 GB |
| `llm` | llama.cpp with Qwen 2.5 3B (classifier, optional) | ~2.2 GB |

## Requirements

- **Docker** with Compose v2
- **NVIDIA GPU** with CUDA drivers (for embeddings service)
- **~35 GB disk space** for Docker images and models
- **First boot takes several hours** (model downloads). Subsequent starts are immediate.

## Quick Start

```bash
git clone https://github.com/josortmel/ecodb
cd ecodb
./scripts/setup.sh          # generates .env, verifies dependencies
docker compose up -d         # first boot downloads models
```

First boot downloads models (~35 GB). Monitor progress:

```bash
docker compose logs -f embeddings ner    # watch until "model loaded" / "ready"
docker compose ps                        # all services should show "healthy"
```

Once all services are healthy, generate your API key:

```bash
docker exec ecodb-api python bootstrap_first_apikey.py
# Copy the key, add to .env as ECODB_API_KEY=ecodb_...
docker compose restart mcp
```

### Optional profiles

```bash
# Document ingestion (PDF, DOCX, audio)
docker compose --profile with-ingestion up -d

# Local LLM for classification and HyDE
docker compose --profile with-llm up -d
```

## MCP Tools

Connect any MCP-compatible client. Two transport options:

**SSE (HTTP)** — for clients that support HTTP transport:
```
URL: http://localhost:8091/sse
```

**stdio (Claude Code)** — add to your project's `.mcp.json`:
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
| `buscar` | Semantic search with GAMR scoring (8 stages) |
| `buscar_recientes` | Recent memories with filters |
| `guardar_memoria` | Store a memory (auto-embeds, auto-extracts entities, auto-links graph) |
| `leer_memoria` | Read a memory by ID |
| `borrar_memoria` | Soft-delete (recycle bin) |
| `guardar_tripleta` | Add a relationship to the knowledge graph |
| `guardar_tripletas_lote` | Batch add triples (max 100) |
| `vecinos` | Graph neighbors at depth N |
| `camino_entre` | Shortest path between two nodes |
| `buscar_nodos` | Fuzzy search nodes by name |
| `borrar_tripleta` | Remove a graph relationship |
| `estado_grafo` | Graph statistics |
| `cargar_identidad` | Load agent identity fragments |
| `guardar_identidad` | Save agent identity (full snapshot) |
| `ver_imagen` | Retrieve embedded image |
| `registrar_documento` | Register a document for ingestion |
| `estado_documento` | Check ingestion status |
| `buscar_en_documento` | Search within a specific document |
| `leer_documento` | Read document content |
| `listar_documentos` | List registered documents |
| `reindexar_documento` | Re-index a document |
| `desvincular_documento` | Unlink a document |

## REST API

Full API available at `http://localhost:8080`. Interactive docs at `/docs` (development mode).

Key endpoints:
- `POST /api/v1/memories` — Create memory
- `POST /api/v1/search` — GAMR search
- `GET /api/v1/graph/neighbors/{node}` — Graph traversal
- `POST /api/v1/documents` — Register document for ingestion
- `POST /api/v1/auth/token` — Get JWT token
- `GET /api/v1/health` — Health check

Interactive API docs available at `http://localhost:8080/docs` when running in development mode.

## Benchmarks

GAMR search performance on internal evaluation (1400+ memories, 60 queries):

| Metric | EcoDB GAMR | Typical RAG (cosine only) |
|--------|-----------|--------------------------|
| R@5 | **0.56** | ~0.30-0.40 |
| MRR | **0.39** | ~0.20-0.30 |
| Multimodal R@5 | **0.70** | N/A |

EcoDB outperforms pure vector search because GAMR combines 6 independent signals, not just cosine similarity. The knowledge graph and temporal scoring surface memories that semantic search alone would miss.

Benchmark methodology and reproducible evaluation scripts are in [eval/](eval/).

## Development

```bash
# Run tests (requires running postgres on port 5435)
cd api && python -m pytest tests/ -v

# Type check
cd api && python -m mypy .

# Run a single service for debugging
docker compose up postgres embeddings -d
cd api && uvicorn main:app --reload --port 8080
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal, educational, and noncommercial use. Commercial deployment requires a separate license from Eco Consulting.

See [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES) for open-source dependencies.

## Maintainers

- [@josortmel](https://github.com/josortmel)
- [@EcoConsulting](https://github.com/EcoConsulting)
