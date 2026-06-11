"""Offline tests — httpx mocked with respx. No live EcoDB needed.

    pip install -e ".[openai,dev]"
    pytest -q
"""

import json

import httpx
import respx

from ecodb_langchain import (
    EcoDBClient,
    EcoDBRetriever,
    build_ecodb_agent,
    make_ecodb_tools,
)

BASE = "http://testserver:8080"


def _client() -> EcoDBClient:
    return EcoDBClient(base_url=BASE, api_key="ecodb_test", agent_identifier="Eco")


@respx.mock
def test_auth_then_search_builds_correct_request():
    token = respx.post(f"{BASE}/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "jwt123", "expires_in": 3600})
    )
    search = respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json={"query_type": "contextual", "results": [
            {"id": "m1", "type": "tecnico", "score": 0.91, "content": "EcoDB uses pgvector", "tags": ["db"]},
        ]})
    )
    data = _client().search("retrieval engine", limit=5)

    assert token.called
    # Bearer token attached after auth exchange
    assert search.calls.last.request.headers["authorization"] == "Bearer jwt123"
    sent = json.loads(search.calls.last.request.content)
    assert sent["query_text"] == "retrieval engine"
    assert sent["limit"] == 5
    assert sent["agent_identifier"] == "Eco"  # client default injected
    assert data["results"][0]["id"] == "m1"


@respx.mock
def test_save_memory_payload_and_401_refresh():
    # First token, then a 401 on /memories, then refresh + success.
    respx.post(f"{BASE}/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "jwt1", "expires_in": 3600})
    )
    route = respx.post(f"{BASE}/memories").mock(
        side_effect=[
            httpx.Response(401, json={"detail": "expired"}),
            httpx.Response(200, json={"id": "abc", "type": "decision", "weight": 0.7, "created_at": "now"}),
        ]
    )
    out = _client().save_memory("we picked LangGraph", type="decision", tags=["arch"])

    assert route.call_count == 2  # retried once after 401
    payload = json.loads(route.calls.last.request.content)
    assert payload["content"] == "we picked LangGraph"
    assert payload["type"] == "decision"
    assert payload["tags"] == ["arch"]
    assert payload["agent_identifier"] == "Eco"
    assert out["id"] == "abc"


@respx.mock
def test_retriever_maps_results_to_documents():
    respx.post(f"{BASE}/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "j", "expires_in": 3600})
    )
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json={"results": [
            {"id": "m1", "type": "tecnico", "score": 0.9, "content": "GAMR has 10 stages", "tags": []},
            {"id": "m2", "type": "momento", "score": 0.8, "content": "shipped v1", "tags": ["ship"]},
        ]})
    )
    docs = EcoDBRetriever(client=_client(), k=2).invoke("how does retrieval work")
    assert [d.page_content for d in docs] == ["GAMR has 10 stages", "shipped v1"]
    assert docs[0].metadata["id"] == "m1"
    assert docs[0].metadata["score"] == 0.9


def test_toolset_parity():
    tools = make_ecodb_tools(_client())
    names = {t.name for t in tools}
    assert names == {
        "ecodb_search", "ecodb_search_recent", "ecodb_save_memory", "ecodb_read_memory",
        "ecodb_graph_neighbors", "ecodb_graph_path", "ecodb_search_nodes",
        "ecodb_graph_status", "ecodb_save_triple",
    }


class _FakeLLM:
    """Minimal chat model stand-in: enough for build_ecodb_agent to compile."""

    def bind_tools(self, tools):
        self._tools = tools
        return self

    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content="ok")


def test_agent_graph_compiles():
    agent = build_ecodb_agent(llm=_FakeLLM(), client=_client())
    assert hasattr(agent, "invoke")
    # The compiled graph exposes its nodes; agent + tools must be present.
    graph = agent.get_graph()
    node_names = set(graph.nodes.keys())
    assert {"agent", "tools"}.issubset(node_names)
