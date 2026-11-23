"""Fake embeddings + NER services for the test suite (#1362).

Many API tests create memories through the real endpoints, which call the embeddings service (and the NER
service for entities). Those services are heavy (Jina v4, GLiNER) and are not available in CI or in a plain
test run; without them the API answers 503 and the tests fail for a reason that is not theirs.

This is a stand-in with the same HTTP contract, deterministic and instant:
  GET  /health        -> {"status": "ok"}
  POST /embed/text    -> {"embeddings": [[512 floats], ...]}   one vector per text, same text -> same vector
  POST /embed/image   -> {"embeddings": [[512 floats], ...]}
  POST /extract       -> []                                    no entities (the API already tolerates this)

Run it next to the tests and point the API at it:
  python -m uvicorn servicios_falsos:app --app-dir api/tests --port 8090 &
  EMBEDDINGS_URL=http://127.0.0.1:8090 NER_SERVICE_URL=http://127.0.0.1:8090 python -m pytest api/tests/...

It is NOT a model: similarity between different texts means nothing. Tests that need real semantic ranking
must not rely on it.
"""

import hashlib
import math

from fastapi import FastAPI, Request

DIM = 512  # settings.EMBEDDING_DIM; the API rejects any other length

app = FastAPI(title="EcoDB fake services (tests only)")


def vector_for(text: str, dim: int = DIM) -> list[float]:
    """Unit-length vector derived from sha256 of the text: deterministic, spread over all dimensions."""
    values: list[float] = []
    counter = 0
    while len(values) < dim:
        block = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        values.extend((b - 127.5) / 127.5 for b in block)
        counter += 1
    values = values[:dim]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/embed/text")
async def embed_text(request: Request) -> dict:
    body = await request.json()
    dim = int(body.get("truncate_dim") or DIM)
    return {"embeddings": [vector_for(t, dim) for t in body.get("texts", [])]}


@app.post("/embed/image")
async def embed_image(request: Request) -> dict:
    body = await request.json()
    dim = int(body.get("truncate_dim") or DIM)
    return {"embeddings": [vector_for("image:" + i, dim) for i in body.get("images", [])]}


@app.post("/extract")
async def extract(request: Request) -> list:
    await request.json()
    return []
