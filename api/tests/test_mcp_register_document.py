"""C16: register_document must upload the file BYTES via POST /documents/upload.

The old path copied the file into the MCP's media dir and POSTed that path.
With the MCP on the host (stdio), that dir is the host folder, while the
worker reads /app/media inside the containers (a named volume) -> every
agent-registered document failed with "Document file not found".
Offline: httpx mocked with respx, no API, no DB.
"""
import importlib.util
import os
from pathlib import Path

import httpx
import pytest
import respx

SERVER = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
API = "http://localhost:8080"


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("ECODB_API_URL", API)
    monkeypatch.setenv("ECODB_API_KEY", "ecodb_test")
    spec = importlib.util.spec_from_file_location("ecodb_mcp_server_c16", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    media = tmp_path / "media"
    monkeypatch.setattr(mod, "MEDIA_STORE_DIR", media)
    mod._jwt = None
    return mod, media


def _mock_api(doc_type="md"):
    respx.post(f"{API}/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "jwt", "expires_in": 3600}))
    legacy = respx.post(f"{API}/documents").mock(return_value=httpx.Response(500))
    upload = respx.post(f"{API}/documents/upload").mock(return_value=httpx.Response(201, json={
        "id": "11111111-1111-1111-1111-111111111111", "status": "queued",
        "uri": "/app/media/abc.md", "doc_type": doc_type}))
    return legacy, upload


@respx.mock
def test_register_document_uploads_bytes_not_host_path(srv, tmp_path):
    mod, media = srv
    doc = tmp_path / "notas_secretas_dir" / "plan.md"
    doc.parent.mkdir()
    doc.write_bytes(b"# Plan\ncontenido unico 42\n")
    legacy, upload = _mock_api()

    out = mod.register_document(str(doc), project_id=7, visibility="private")

    assert not legacy.called, "must not POST /documents with a path"
    assert upload.called
    req = upload.calls.last.request
    body = req.content
    assert b"contenido unico 42" in body                      # the bytes travel
    assert str(tmp_path).encode() not in body                 # no host path
    assert b"notas_secretas_dir" not in body
    assert str(tmp_path) not in str(req.url)
    assert req.url.params["project_id"] == "7"
    assert req.url.params["visibility"] == "private"
    assert req.url.params["doc_type"] == "md"
    assert out == {"status": "queued", "document_id": "11111111-1111-1111-1111-111111111111",
                   "uri": "/app/media/abc.md", "doc_type": "md"}
    assert not media.exists() or not any(media.rglob("*")), "nothing copied to the MCP media dir"


@respx.mock
def test_register_document_keeps_security_checks(srv, tmp_path):
    mod, _ = srv
    _, upload = _mock_api()
    secret = tmp_path / "prod.env"
    secret.write_text("KEY=1")
    assert "error" in mod.register_document(str(secret), project_id=7)
    assert "error" in mod.register_document("https://example.com/x.md", project_id=7)
    assert "error" in mod.register_document(str(tmp_path / "missing.md"), project_id=7)
    assert not upload.called


@respx.mock
def test_register_document_rejects_oversize_before_upload(srv, tmp_path, monkeypatch):
    mod, _ = srv
    _, upload = _mock_api()
    monkeypatch.setattr(mod, "MAX_MEDIA_FILE_SIZE", 10)
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * 11)
    assert "error" in mod.register_document(str(big), project_id=7)
    assert not upload.called


def test_upload_rejects_unknown_doc_type_before_writing(tmp_path, monkeypatch):
    """API side: doc_type override is validated before the file is stored."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import documents
    from auth import get_current_user

    monkeypatch.setattr(documents, "_MEDIA_STORE", str(tmp_path / "store"))
    app = FastAPI()
    app.include_router(documents.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "is_super": True}
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/documents/upload", params={"project_id": 1, "doc_type": "exe"},
               files={"file": ("x.md", b"hola")})
    assert r.status_code == 422
    assert not (tmp_path / "store").exists()


def test_upload_accepts_fast_path_types():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import documents
    assert {"md", "txt", "markdown", "text", "pdf"} <= documents._UPLOAD_DOC_TYPES
