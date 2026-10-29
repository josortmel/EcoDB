"""#547 (L14): a save_memory during an embeddings/API outage is queued on disk with its final id
and time, sent later, and a send that fails for any other reason stays visible in failed/.
Offline: httpx with respx, a temporary spool dir, no API and no database."""
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest
import respx

SERVER = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
API = "http://localhost:8080"


@pytest.fixture
def mod(monkeypatch, tmp_path):
    monkeypatch.setenv("ECODB_API_URL", API)
    monkeypatch.setenv("ECODB_API_KEY", "ecodb_test")
    monkeypatch.setenv("ECODB_SPOOL_DIR", str(tmp_path / "spool"))
    spec = importlib.util.spec_from_file_location("ecodb_mcp_server_547", SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._jwt = None
    return m


@pytest.fixture
def api():
    with respx.mock(base_url=API, assert_all_called=False) as r:
        r.post("/auth/token").respond(200, json={"access_token": "t", "expires_in": 3600})
        yield r


def _created(req):
    body = json.loads(req.content)
    return {"id": body.get("client_id") or "00000000-0000-0000-0000-000000000001",
            "type": body["type"], "tags": [], "created_at": body.get("occurred_at")}


def _posts(api):
    return [json.loads(c.request.content) for c in api.calls if c.request.url.path == "/memories"]


def test_outage_queues_with_final_id_and_time(mod, api):
    api.post("/memories").respond(503, json={"detail": "embeddings service unavailable"})
    r = mod.save_memory(content="pytest spool", type="observacion")
    assert r["status"] == "queued"
    queued = mod.SPOOL_DIR / f"{r['id']}.json"
    rec = json.loads(queued.read_text(encoding="utf-8"))
    assert rec["payload"]["client_id"] == r["id"]
    assert rec["payload"]["occurred_at"] == r["created_at"]
    assert r["spool"]["pending"] == 1


def test_flush_sends_with_the_same_id_and_time_then_removes_it(mod, api):
    route = api.post("/memories")
    route.respond(503, json={"detail": "down"})
    r = mod.save_memory(content="pytest spool", type="observacion")
    route.side_effect = lambda req: respx.MockResponse(201, json=_created(req))
    assert mod._spool_flush() == {"sent": 1, "kept": 0, "failed": 0}
    sent = _posts(api)[-1]
    assert sent["client_id"] == r["id"] and sent["occurred_at"] == r["created_at"]
    assert list(mod.SPOOL_DIR.glob("*")) == []


def test_still_down_keeps_it_queued(mod, api):
    api.post("/memories").respond(503, json={"detail": "down"})
    r = mod.save_memory(content="pytest spool", type="observacion")
    assert mod._spool_flush() == {"sent": 0, "kept": 1, "failed": 0}
    assert (mod.SPOOL_DIR / f"{r['id']}.json").exists()


def test_a_non_outage_failure_goes_to_failed_and_is_reported(mod, api):
    route = api.post("/memories")
    route.respond(503, json={"detail": "down"})
    mod.save_memory(content="pytest spool", type="observacion")
    route.respond(422, json={"detail": "bad"})
    assert mod._spool_flush() == {"sent": 0, "kept": 0, "failed": 1}
    failed = list((mod.SPOOL_DIR / "failed").glob("*.json"))
    assert len(failed) == 1 and "422" in json.loads(failed[0].read_text(encoding="utf-8"))["error"]
    route.side_effect = lambda req: respx.MockResponse(201, json=_created(req))
    ok = mod.save_memory(content="pytest next", type="observacion")
    assert ok["status"] == "ok" and ok["spool"]["failed"] == 1 and "could NOT be saved" in ok["spool"]["warning"]


def test_normal_save_sends_no_client_id(mod, api):
    api.post("/memories").mock(side_effect=lambda req: respx.MockResponse(201, json=_created(req)))
    r = mod.save_memory(content="pytest normal", type="observacion")
    assert r["status"] == "ok" and "spool" not in r
    assert "client_id" not in _posts(api)[-1]


def test_other_errors_are_not_queued(mod, api):
    api.post("/memories").respond(422, json={"detail": "bad type"})
    r = mod.save_memory(content="pytest", type="observacion")
    assert "error" in r and not mod.SPOOL_DIR.exists()


def test_a_lock_left_by_a_dead_process_is_cleared_and_retried(mod, api):
    api.post("/memories").respond(503, json={"detail": "down"})
    r = mod.save_memory(content="pytest spool", type="observacion")
    lock = mod.SPOOL_DIR / f"{r['id']}.lock"
    lock.write_text("")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    api.post("/memories").mock(side_effect=lambda req: respx.MockResponse(201, json=_created(req)))
    assert mod._spool_flush()["sent"] == 1
    assert list(mod.SPOOL_DIR.glob("*")) == []


def test_a_fresh_lock_of_another_session_is_left_alone(mod, api):
    api.post("/memories").respond(503, json={"detail": "down"})
    r = mod.save_memory(content="pytest spool", type="observacion")
    (mod.SPOOL_DIR / f"{r['id']}.lock").write_text("")
    assert mod._spool_flush() == {"sent": 0, "kept": 0, "failed": 0}
    assert (mod.SPOOL_DIR / f"{r['id']}.json").exists()


def test_a_file_another_session_already_sent_is_not_a_failure(mod, api):
    """The race measured on 29-oct: we listed the file, another session sent and removed it
    before our lock. That must be a skip, never an entry in failed/."""
    api.post("/memories").respond(503, json={"detail": "down"})
    r = mod.save_memory(content="pytest spool", type="observacion")
    f = mod.SPOOL_DIR / f"{r['id']}.json"
    real_claim = mod._spool_claim

    def claim_after_other_session_sent(path):
        path.unlink()  # the other session finished it
        return real_claim(path)

    mod._spool_claim = claim_after_other_session_sent
    assert mod._spool_flush() == {"sent": 0, "kept": 0, "failed": 0}
    assert not (mod.SPOOL_DIR / "failed").exists() and not f.with_suffix(".lock").exists()
