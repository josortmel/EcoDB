"""Tests — FastAPI skeleton + health check.

Run from the api/ directory:
    pip install pytest httpx
    python -m pytest tests/ -v

Los tests usan create_app(environment) en vez del app module-level para que
cada caso pueda forzar el env sin depender de variables de entorno externas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import create_app
from settings import API_VERSION, SCHEMA_VERSION

# App de production (default) y development para tests segun caso.
app_prod = create_app("production")
app_dev = create_app("development")
client_prod = TestClient(app_prod)
client_dev = TestClient(app_dev)


# --- Liveness checks ---

def test_get_health_returns_200():
    response = client_prod.get("/health")
    assert response.status_code == 200


def test_head_health_returns_200():
    """RFC 7231 §4.3.2 — recurso GET debe soportar HEAD."""
    response = client_prod.head("/health")
    assert response.status_code == 200


def test_health_returns_json():
    response = client_prod.get("/health")
    assert response.headers["content-type"] == "application/json"


def test_health_status_ok():
    payload = client_prod.get("/health").json()
    assert payload["status"] == "ok"


def test_health_includes_service_metadata():
    payload = client_prod.get("/health").json()
    assert payload["service"] == "ecodb-api"
    assert payload["api_version"] == API_VERSION
    assert payload["schema_version_target"] == SCHEMA_VERSION


def test_health_no_required_auth():
    """Liveness check no debe requerir auth — debe responder con 200 sin Authorization header."""
    response = client_prod.get("/health")
    assert response.status_code == 200


# --- Security headers (VS5) ---

def test_security_headers_present():
    """X-Content-Type-Options + Referrer-Policy en cada respuesta."""
    response = client_prod.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "no-referrer"


# --- Docs gating por ENVIRONMENT (VS3) ---

def test_docs_hidden_in_production():
    """En production, /docs y /openapi.json deben devolver 404 (no exponer schema sin auth)."""
    assert client_prod.get("/docs").status_code == 404
    assert client_prod.get("/openapi.json").status_code == 404
    assert client_prod.get("/redoc").status_code == 404


def test_docs_available_in_development():
    """En development, /docs y /openapi.json siguen accesibles para debugging."""
    assert client_dev.get("/docs").status_code == 200
    assert client_dev.get("/redoc").status_code == 200
    assert client_dev.get("/openapi.json").status_code == 200


def test_openapi_schema_in_development_describes_health():
    """En development, el schema OpenAPI debe contener al menos /health."""
    schema = client_dev.get("/openapi.json").json()
    assert schema["info"]["title"] == "EcoDB API"
    assert "/health" in schema["paths"]


# --- Comportamiento HTTP general ---

def test_inexistent_endpoint_returns_404():
    response = client_prod.get("/foo/bar/baz")
    assert response.status_code == 404


def test_post_health_method_not_allowed():
    """POST /health debe devolver 405 — solo GET y HEAD aceptados."""
    assert client_prod.post("/health").status_code == 405
