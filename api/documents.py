"""Document management endpoints — Task 4.11."""
from __future__ import annotations

import json
import logging
import os
import re
import uuid as _uuid
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from auth import get_current_user
from db import get_pool
from permissions import visible_project_ids

log = logging.getLogger("ecodb.documents")

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    uri: str = Field(..., min_length=1, max_length=2048)
    filename: str = Field(..., min_length=1, max_length=512)
    doc_type: str = Field(..., min_length=1, max_length=64)
    project_id: int
    workspace_id: Optional[int] = None
    visibility: Literal["public", "private"] = "public"


class DocumentResponse(BaseModel):
    id: UUID
    uri: str
    filename: str
    doc_type: str
    workspace_id: int
    project_id: int
    visibility: str
    status: str
    retry_count: int
    processing_started_at: Optional[datetime] = None
    last_indexed: Optional[datetime] = None
    processing_metrics: Optional[dict] = None
    base_weight: float
    created_at: datetime


class DocumentListItem(BaseModel):
    id: UUID
    uri: str
    filename: str
    doc_type: str
    workspace_id: int
    project_id: int
    status: str
    created_at: datetime


class ChunkItem(BaseModel):
    chunk_index: int
    content: str
    section_path: Optional[str] = None


class ChunksResponse(BaseModel):
    document_id: UUID
    chunks: list[ChunkItem]
    chunks_returned: int
    total_chunks: int
    truncated: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOC_SELECT = """
    SELECT id, uri, filename, doc_type, workspace_id, project_id,
           visibility::text, status, retry_count,
           processing_started_at, last_indexed, processing_metrics,
           base_weight, created_at
    FROM documents
"""


def _row_to_response(row) -> DocumentResponse:
    metrics = row["processing_metrics"]
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    return DocumentResponse(
        id=row["id"],
        uri=row["uri"],
        filename=row["filename"],
        doc_type=row["doc_type"],
        workspace_id=row["workspace_id"],
        project_id=row["project_id"],
        visibility=row["visibility"],
        status=row["status"],
        retry_count=row["retry_count"],
        processing_started_at=row.get("processing_started_at"),
        last_indexed=row.get("last_indexed"),
        processing_metrics=metrics,
        base_weight=float(row["base_weight"]),
        created_at=row["created_at"],
    )


async def _check_read_access(conn, doc_row, actor: dict) -> None:
    if actor.get("is_super"):
        return
    visible = await visible_project_ids(conn, actor)
    if doc_row["project_id"] not in visible:
        raise HTTPException(403, "no access to this document")


# ---------------------------------------------------------------------------
# POST /documents — register + queue
# ---------------------------------------------------------------------------

@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(
    body: DocumentCreate,
    actor: dict = Depends(get_current_user),
) -> DocumentResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        workspace_id = body.workspace_id
        if workspace_id is None:
            ws_id = await conn.fetchval(
                "SELECT workspace_id FROM projects WHERE id = $1", body.project_id
            )
            if ws_id is None:
                raise HTTPException(404, "project not found")
            workspace_id = ws_id

        if not actor.get("is_super"):
            visible = await visible_project_ids(conn, actor)
            if body.project_id not in visible:
                raise HTTPException(403, "no access to target project")

        row = await conn.fetchrow(
            """
            INSERT INTO documents (uri, filename, doc_type, workspace_id, project_id, visibility, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'queued')
            RETURNING id, uri, filename, doc_type, workspace_id, project_id,
                      visibility::text, status, retry_count,
                      processing_started_at, last_indexed, processing_metrics,
                      base_weight, created_at
            """,
            body.uri, body.filename, body.doc_type,
            workspace_id, body.project_id, body.visibility,
        )
        await conn.execute("SELECT pg_notify('ecodb_ingest', $1)", str(row["id"]))
        await conn.execute(
            """INSERT INTO audit_log (user_id, action, resource, resource_id, details, organization_id)
            VALUES ($1, 'register_document', 'document', $2, $3::jsonb, $4)""",
            int(actor["sub"]), str(row["id"]),
            json.dumps({"uri": body.uri, "filename": body.filename, "project_id": body.project_id}),
            actor.get("organization_id"),
        )
        return _row_to_response(row)


# ---------------------------------------------------------------------------
# POST /documents/upload — multipart file upload (dashboard, distribution)
# ---------------------------------------------------------------------------

_MEDIA_STORE = os.environ.get("MEDIA_STORE_DIR", "/app/media")

_DOC_TYPE_MAP = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "docx",
    ".pptx": "pptx", ".ppt": "pptx",
    ".md": "markdown", ".txt": "text",
    ".html": "html", ".htm": "html",
    ".csv": "csv", ".json": "json",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
}
# C16: types a caller may force on upload — the inferred ones plus the parser's
# fast-path names (parsers.py: "txt"/"md" skip docling) that the MCP sends.
_UPLOAD_DOC_TYPES = frozenset(_DOC_TYPE_MAP.values()) | {"md", "txt"}
# C16b: upload is the only gate for agent documents — cap, denylist and a sane
# extension shape are enforced before anything is written. Same size env as the parser.
_MAX_UPLOAD_BYTES = int(os.environ.get("MAX_DOC_SIZE_BYTES", str(50 * 1024 * 1024)))
_DENIED_UPLOAD_EXTENSIONS = frozenset({
    ".env", ".key", ".pem", ".pfx", ".p12", ".p8", ".ppk", ".der", ".yaml", ".toml", ".ini",
    ".config", ".exe", ".dll", ".bat", ".ps1", ".sh", ".cmd",
})
_EXT_RE = re.compile(r"^\.[a-z0-9]{1,10}$")


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    project_id: int = Query(..., gt=0),
    visibility: Literal["public", "private"] = "public",
    doc_type: Optional[str] = Query(
        None, description="Override del tipo inferido por extension. md/txt usan el parser de texto rapido."),
    actor: dict = Depends(get_current_user),
) -> DocumentResponse:
    """Upload a document file via multipart. Dashboard and MCP use this — no host path needed."""
    if not file.filename:
        raise HTTPException(400, "file has no name")
    if doc_type is not None and doc_type not in _UPLOAD_DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {sorted(_UPLOAD_DOC_TYPES)}")
    ext = os.path.splitext(file.filename)[1].lower()
    if not _EXT_RE.match(ext):
        raise HTTPException(422, "file must have a plain alphanumeric extension")
    if ext in _DENIED_UPLOAD_EXTENSIONS:
        raise HTTPException(422, f"file extension '{ext}' blocked for security")

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file exceeds max size ({_MAX_UPLOAD_BYTES} bytes)")

    if doc_type is None:
        doc_type = _DOC_TYPE_MAP.get(ext, "text")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # C16b: permission and project checks BEFORE the file is written.
        if not actor.get("is_super"):
            visible = await visible_project_ids(conn, actor)
            if project_id not in visible:
                raise HTTPException(403, "no access to target project")

        workspace_id = await conn.fetchval(
            "SELECT workspace_id FROM projects WHERE id = $1", project_id
        )
        if workspace_id is None:
            raise HTTPException(404, "project not found")

        os.makedirs(_MEDIA_STORE, exist_ok=True)
        stored_path = os.path.join(_MEDIA_STORE, f"{_uuid.uuid4()}{ext}")
        with open(stored_path, "wb") as f:
            f.write(content)

        try:
            row = await conn.fetchrow(
                """
                INSERT INTO documents (uri, filename, doc_type, workspace_id, project_id, visibility, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'queued')
                RETURNING id, uri, filename, doc_type, workspace_id, project_id,
                          visibility::text, status, retry_count,
                          processing_started_at, last_indexed, processing_metrics,
                          base_weight, created_at
                """,
                stored_path, file.filename, doc_type,
                workspace_id, project_id, visibility,
            )
        except Exception:
            os.unlink(stored_path)  # no orphan file when the row could not be created
            raise
        await conn.execute("SELECT pg_notify('ecodb_ingest', $1)", str(row["id"]))
        await conn.execute(
            """INSERT INTO audit_log (user_id, action, resource, resource_id, details, organization_id)
            VALUES ($1, 'upload_document', 'document', $2, $3::jsonb, $4)""",
            int(actor["sub"]), str(row["id"]),
            json.dumps({"filename": file.filename, "project_id": project_id, "size": len(content)}),
            actor.get("organization_id"),
        )
        return _row_to_response(row)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[DocumentListItem])
async def list_documents(
    project_id: Optional[int] = Query(None),
    workspace_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor: dict = Depends(get_current_user),
) -> list[DocumentListItem]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        where: list[str] = ["status != 'deleted'"]
        params: list = []
        idx = 1

        if not actor.get("is_super"):
            visible = await visible_project_ids(conn, actor)
            if not visible:
                return []
            where.append(f"project_id = ANY(${idx}::int[])")
            params.append(list(visible))
            idx += 1

        if project_id is not None:
            where.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if workspace_id is not None:
            where.append(f"workspace_id = ${idx}")
            params.append(workspace_id)
            idx += 1
        if status is not None:
            where.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        params.append(limit)
        params.append(offset)
        rows = await conn.fetch(
            f"SELECT id, uri, filename, doc_type, workspace_id, project_id, status, created_at"
            f" FROM documents WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *params,
        )
        return [
            DocumentListItem(
                id=r["id"], uri=r["uri"], filename=r["filename"],
                doc_type=r["doc_type"], workspace_id=r["workspace_id"],
                project_id=r["project_id"], status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    actor: dict = Depends(get_current_user),
) -> DocumentResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _DOC_SELECT + "WHERE id = $1 AND status != 'deleted'",
            document_id,
        )
        if row is None:
            raise HTTPException(404, "document not found")
        await _check_read_access(conn, row, actor)
        return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /documents/{document_id}/chunks
# ---------------------------------------------------------------------------

@router.get("/{document_id}/chunks", response_model=ChunksResponse)
async def get_document_chunks(
    document_id: UUID,
    start: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    actor: dict = Depends(get_current_user),
) -> ChunksResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT id, project_id, status FROM documents WHERE id = $1 AND status != 'deleted'",
            document_id,
        )
        if doc is None:
            raise HTTPException(404, "document not found")
        await _check_read_access(conn, doc, actor)

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = $1", document_id
        )
        rows = await conn.fetch("""
            SELECT chunk_index, content, section_path
            FROM document_chunks
            WHERE document_id = $1
            ORDER BY chunk_index
            LIMIT $2 OFFSET $3
        """, document_id, limit, start)

    return ChunksResponse(
        document_id=document_id,
        chunks=[
            ChunkItem(
                chunk_index=r["chunk_index"],
                content=r["content"],
                section_path=r["section_path"],
            )
            for r in rows
        ],
        chunks_returned=len(rows),
        total_chunks=int(total),
        truncated=(start + len(rows)) < int(total),
    )


# ---------------------------------------------------------------------------
# PUT /documents/{document_id}/reindex
# ---------------------------------------------------------------------------

@router.put("/{document_id}/reindex")
async def reindex_document(
    document_id: UUID,
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not actor.get("is_super"):
            raise HTTPException(404, "not found")

        doc = await conn.fetchrow(
            "SELECT id, project_id, status FROM documents WHERE id = $1 AND status != 'deleted'",
            document_id,
        )
        if doc is None:
            raise HTTPException(404, "not found")

        await conn.execute("""
            UPDATE documents
            SET status = 'queued', retry_count = 0,
                processing_started_at = NULL, last_indexed = NULL
            WHERE id = $1
        """, document_id)
        await conn.execute("SELECT pg_notify('ecodb_ingest', $1)", str(document_id))
        await conn.execute(
            """INSERT INTO audit_log (user_id, action, resource, resource_id, details, organization_id)
            VALUES ($1, 'reindex_document', 'document', $2, $3::jsonb, $4)""",
            int(actor["sub"]), str(document_id),
            json.dumps({}),
            actor.get("organization_id"),
        )

    return {"status": "queued", "document_id": str(document_id)}


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id} — soft delete
# ---------------------------------------------------------------------------

@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    actor: dict = Depends(get_current_user),
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not actor.get("is_super"):
            raise HTTPException(404, "not found")

        doc = await conn.fetchrow(
            "SELECT id, project_id, status FROM documents WHERE id = $1", document_id
        )
        if doc is None or doc["status"] == "deleted":
            raise HTTPException(404, "not found")

        await conn.execute(
            "UPDATE documents SET status = 'deleted' WHERE id = $1", document_id
        )
        await conn.execute(
            """INSERT INTO audit_log (user_id, action, resource, resource_id, details, organization_id)
            VALUES ($1, 'delete_document', 'document', $2, $3::jsonb, $4)""",
            int(actor["sub"]), str(document_id),
            json.dumps({"project_id": doc["project_id"]}),
            actor.get("organization_id"),
        )
