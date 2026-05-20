"""Tests unitarios — — api/permissions.py.

Cubren los helpers síncronos puros (sin DB) y los async contra postgres real.
Los tests de cascada full ya están en test_workspaces.py + test_projects.py +
test_memories.py — aquí enfocamos en helpers individuales para que un fallo
puntual se localice rápido sin tener que correr la matriz entera.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)

sys.path.insert(0, str(Path(__file__).parent.parent))

from permissions import (
    no_null_bytes,
    user_can_create_project_in_ws,
    user_can_create_workspace,
    user_can_delete_project,
    user_can_delete_workspace,
    user_can_modify_project,
    user_can_modify_workspace,
    validate_name_strip_blank,
    visible_project_ids,
    visible_workspace_ids,
)


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# Validation helpers (síncronos, sin DB)
# ===========================================================================

def test_no_null_bytes_passes_clean_string():
    assert no_null_bytes("foo bar", "name") == "foo bar"


def test_no_null_bytes_rejects_x00():
    with pytest.raises(ValueError, match="name cannot contain null bytes"):
        no_null_bytes("foo\x00bar", "name")


def test_validate_name_strip_blank_trims_and_returns():
    assert validate_name_strip_blank("  foo  ", "name") == "foo"


def test_validate_name_strip_blank_rejects_blank():
    with pytest.raises(ValueError, match="cannot be blank"):
        validate_name_strip_blank(" ", "name")


def test_validate_name_strip_blank_rejects_only_whitespace():
    with pytest.raises(ValueError, match="cannot be blank"):
        validate_name_strip_blank("   ", "name")


def test_validate_name_strip_blank_rejects_null_bytes():
    with pytest.raises(ValueError, match="cannot contain null bytes"):
        validate_name_strip_blank("foo\x00bar", "name")


def test_validate_name_strip_blank_field_name_in_error():
    with pytest.raises(ValueError, match="title cannot be blank"):
        validate_name_strip_blank(" ", "title")


# ===========================================================================
# Workspace permissions (síncronos)
# ===========================================================================

def test_super_can_create_any_workspace():
    actor = {"is_super": True, "is_ceo": False, "organization_id": None, "lead_workspaces": [], "sub": "1"}
    assert user_can_create_workspace(actor, None) is True
    assert user_can_create_workspace(actor, 5) is True


def test_ceo_can_create_in_own_org():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 7, "lead_workspaces": [], "sub": "10"}
    assert user_can_create_workspace(actor, 7) is True


def test_ceo_cannot_create_in_foreign_org():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 7, "lead_workspaces": [], "sub": "10"}
    assert user_can_create_workspace(actor, 8) is False


def test_ceo_cannot_create_system_workspace():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 7, "lead_workspaces": [], "sub": "10"}
    assert user_can_create_workspace(actor, None) is False


def test_lead_cannot_create_workspace():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [3], "sub": "10"}
    assert user_can_create_workspace(actor, 5) is False


def test_worker_cannot_create_workspace():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [], "sub": "10"}
    assert user_can_create_workspace(actor, 5) is False


def test_super_can_modify_any_workspace():
    actor = {"is_super": True, "lead_workspaces": []}
    ws = {"id": 1, "organization_id": 5}
    assert user_can_modify_workspace(actor, ws) is True


def test_ceo_can_modify_own_org_workspace():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 5, "lead_workspaces": []}
    ws = {"id": 10, "organization_id": 5}
    assert user_can_modify_workspace(actor, ws) is True


def test_ceo_cannot_modify_foreign_workspace():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 5, "lead_workspaces": []}
    ws = {"id": 10, "organization_id": 99}
    assert user_can_modify_workspace(actor, ws) is False


def test_lead_can_modify_assigned_workspace():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [10]}
    ws = {"id": 10, "organization_id": None}
    assert user_can_modify_workspace(actor, ws) is True


def test_lead_cannot_modify_unassigned_workspace():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [3]}
    ws = {"id": 10, "organization_id": None}
    assert user_can_modify_workspace(actor, ws) is False


def test_worker_cannot_delete_workspace():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": []}
    ws = {"id": 10, "organization_id": None}
    assert user_can_delete_workspace(actor, ws) is False


def test_lead_cannot_delete_workspace():
    """Lead modifica pero NO borra workspace — decisión del dueño de la org."""
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [10]}
    ws = {"id": 10, "organization_id": None}
    assert user_can_delete_workspace(actor, ws) is False


def test_ceo_can_delete_own_org_workspace():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 5, "lead_workspaces": []}
    ws = {"id": 10, "organization_id": 5}
    assert user_can_delete_workspace(actor, ws) is True


# ===========================================================================
# Project permissions (síncronos)
# ===========================================================================

def test_super_can_modify_any_project():
    actor = {"is_super": True, "lead_workspaces": []}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": 5}
    assert user_can_modify_project(actor, proj) is True


def test_lead_can_modify_project_in_own_workspace():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [10]}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": None}
    assert user_can_modify_project(actor, proj) is True


def test_ceo_can_modify_project_in_own_org():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 5, "lead_workspaces": []}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": 5}
    assert user_can_modify_project(actor, proj) is True


def test_ceo_cannot_modify_project_in_foreign_org():
    actor = {"is_super": False, "is_ceo": True, "organization_id": 5, "lead_workspaces": []}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": 99}
    assert user_can_modify_project(actor, proj) is False


def test_orphan_project_ws_org_null_blocks_ceo():
    """Edge case VS1-PROJ Loop 2: si workspace fue borrado entre operaciones,
    LEFT JOIN devuelve ws_organization_id=None → CEO check fail-closed."""
    actor = {"is_super": False, "is_ceo": True, "organization_id": 5, "lead_workspaces": []}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": None}
    assert user_can_modify_project(actor, proj) is False


def test_lead_can_delete_project_in_own_workspace():
    """A diferencia de DELETE workspace, lead SÍ puede DELETE project del ws."""
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": [10]}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": None}
    assert user_can_delete_project(actor, proj) is True


def test_worker_cannot_delete_project():
    actor = {"is_super": False, "is_ceo": False, "organization_id": None, "lead_workspaces": []}
    proj = {"id": 1, "workspace_id": 10, "ws_organization_id": None}
    assert user_can_delete_project(actor, proj) is False


# ===========================================================================
# Async helpers — DB integration
# ===========================================================================

@pytest.fixture
def super_actor():
    return {"is_super": True, "is_ceo": False, "organization_id": None, "lead_workspaces": [], "sub": "1"}


def test_visible_workspace_ids_super_returns_all(super_actor):
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            ids = await visible_workspace_ids(conn, super_actor)
            return ids
        finally:
            await conn.close()

    ids = _run(run())
    # workspace_id=1 (default) debe estar para super.
    assert 1 in ids


def test_visible_project_ids_super_returns_all(super_actor):
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await visible_project_ids(conn, super_actor)
        finally:
            await conn.close()

    ids = _run(run())
    assert 1 in ids  # project default


def test_visible_workspace_ids_unknown_user_empty():
    """User que no es super, ni CEO, ni lead, sin project_members → set vacío."""
    actor = {
        "is_super": False, "is_ceo": False, "organization_id": None,
        "lead_workspaces": [], "sub": "999999",
    }

    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await visible_workspace_ids(conn, actor)
        finally:
            await conn.close()

    assert _run(run()) == set()


def test_visible_project_ids_unknown_user_empty():
    actor = {
        "is_super": False, "is_ceo": False, "organization_id": None,
        "lead_workspaces": [], "sub": "999999",
    }

    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await visible_project_ids(conn, actor)
        finally:
            await conn.close()

    assert _run(run()) == set()


def test_user_can_create_project_in_ws_super_in_known_workspace(super_actor):
    """Super en workspace_id=1 (default) → True."""
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await user_can_create_project_in_ws(conn, super_actor, 1)
        finally:
            await conn.close()

    assert _run(run()) is True


def test_user_can_create_project_in_ws_super_in_unknown_workspace(super_actor):
    """Super en workspace inexistente: True (super es authoritative; FK fallará al INSERT)."""
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await user_can_create_project_in_ws(conn, super_actor, 999999)
        finally:
            await conn.close()

    assert _run(run()) is True


def test_user_can_create_project_in_ws_worker_no_access():
    actor = {
        "is_super": False, "is_ceo": False, "organization_id": None,
        "lead_workspaces": [], "sub": "999999",
    }

    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await user_can_create_project_in_ws(conn, actor, 1)
        finally:
            await conn.close()

    assert _run(run()) is False
