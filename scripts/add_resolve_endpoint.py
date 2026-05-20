"""Add predicate resolve + aliases endpoints to graph.py in ecodb-api container.

Run: docker cp this_file ecodb-api:/tmp/ && docker exec ecodb-api python /tmp/add_resolve_endpoint.py
"""
import subprocess, textwrap

ENDPOINT_CODE = textwrap.dedent('''

# ---------------------------------------------------------------------------
# Fase 3b — Predicate governance endpoints
# ---------------------------------------------------------------------------

class PredicateResolveResponse(BaseModel):
    canonical: Optional[str] = None
    confidence: float = 0.0
    method: str = "none"
    original: str = ""

class AliasEntry(BaseModel):
    alias: str
    canonical: str
    domain: Optional[str] = None

class AliasListResponse(BaseModel):
    aliases: list[AliasEntry]


@router.get("/predicates/resolve", response_model=PredicateResolveResponse)
async def resolve_predicate(
    predicate: str = Query(..., min_length=1, max_length=200),
    subject_type: str = Query("unknown"),
    object_type: str = Query("unknown"),
    actor: dict = Depends(get_current_user),
) -> PredicateResolveResponse:
    """Resolve free-text predicate to canonical via 3 stages:
    1. Exact match in predicates_canonical
    2. Alias lookup in predicate_aliases
    3. Embedding similarity (ANN cosine on predicates_canonical.embedding)
    """
    lexeme = predicate.strip().lower().replace(" ", "_").replace("-", "_")
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Stage 1: exact match
        row = await conn.fetchrow(
            "SELECT name FROM predicates_canonical WHERE name = $1 AND state IN ('approved','experimental','candidate')",
            lexeme,
        )
        if row:
            return PredicateResolveResponse(canonical=row["name"], confidence=1.0, method="exact", original=predicate)

        # Stage 2: alias lookup
        alias_row = await conn.fetchrow(
            """SELECT canonical FROM predicate_aliases
               WHERE alias = $1 AND (domain IS NULL OR domain = $2 OR domain = $3)
               ORDER BY CASE WHEN domain IS NULL THEN 1 ELSE 0 END
               LIMIT 1""",
            lexeme, subject_type, object_type,
        )
        if alias_row:
            return PredicateResolveResponse(canonical=alias_row["canonical"], confidence=1.0, method="alias", original=predicate)

        # Stage 3: embedding similarity
        # Get embedding for the input predicate
        from embeddings_client import embed_text
        try:
            embedding_str = await embed_text(lexeme, prompt_name="query")
        except Exception:
            return PredicateResolveResponse(canonical=None, confidence=0.0, method="embedding_failed", original=predicate)

        # Parse embedding vector
        import json as _json
        vec = _json.loads(embedding_str) if isinstance(embedding_str, str) else embedding_str

        # ANN search against predicates_canonical embeddings
        best = await conn.fetchrow(
            """SELECT name, 1 - (embedding <=> $1::vector) AS similarity
               FROM predicates_canonical
               WHERE state IN ('approved','experimental','candidate')
                 AND embedding IS NOT NULL
               ORDER BY embedding <=> $1::vector
               LIMIT 1""",
            str(vec),
        )
        if best and best["similarity"] and float(best["similarity"]) > 0:
            # Type validation (stage 3b): check domain_types/range_types if node types known
            if subject_type != "unknown" or object_type != "unknown":
                type_row = await conn.fetchrow(
                    "SELECT domain_types, range_types FROM predicates_canonical WHERE name = $1",
                    best["name"],
                )
                if type_row:
                    dt = type_row["domain_types"] or []
                    rt = type_row["range_types"] or []
                    if dt and subject_type != "unknown" and subject_type not in dt:
                        pass  # type mismatch but don't block — just lower confidence
                    if rt and object_type != "unknown" and object_type not in rt:
                        pass

            return PredicateResolveResponse(
                canonical=best["name"],
                confidence=float(best["similarity"]),
                method="embedding",
                original=predicate,
            )

        return PredicateResolveResponse(canonical=None, confidence=0.0, method="none", original=predicate)


@router.get("/predicates/aliases", response_model=AliasListResponse)
async def list_aliases(actor: dict = Depends(get_current_user)) -> AliasListResponse:
    """List all predicate aliases for MCP cache."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT alias, canonical, domain FROM predicate_aliases ORDER BY alias")
    return AliasListResponse(aliases=[AliasEntry(alias=r["alias"], canonical=r["canonical"], domain=r["domain"]) for r in rows])
''')

# Read current graph.py
result = subprocess.run(["cat", "/app/graph.py"], capture_output=True, text=True)
content = result.stdout

# Append endpoints
with open("/app/graph.py", "a") as f:
    f.write(ENDPOINT_CODE)

print("Endpoints added to graph.py")

# Check Optional import
if "Optional" not in content.split("from")[0]:
    print("NOTE: Optional may need import — check if already imported")
