"""Offline tests for the cell-worker LangChain engine. No live LLM needed."""

import asyncio
import json

from ecodb_langchain.cell_agent import acell_llm_call, make_cell_llm


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """Stand-in chat model: records messages, returns a JSON string like DeepSeek."""

    def __init__(self, payload):
        self.payload = payload
        self.last_messages = None

    async def ainvoke(self, messages):
        self.last_messages = messages
        return _FakeResp(json.dumps(self.payload))


def test_acell_llm_call_returns_json_string_and_orders_messages():
    fake = _FakeLLM({"clusters": [], "lo_que_evitas": "x"})
    out = asyncio.run(acell_llm_call("SYS", "USR", llm=fake))
    # Returns the raw JSON string (cell worker does json.loads on it)
    assert json.loads(out) == {"clusters": [], "lo_que_evitas": "x"}
    # system first, human second — same contract as the old _llm_call
    assert fake.last_messages[0].type == "system"
    assert fake.last_messages[0].content == "SYS"
    assert fake.last_messages[1].type == "human"
    assert fake.last_messages[1].content == "USR"


def test_acell_llm_call_joins_content_blocks():
    class _BlockLLM:
        async def ainvoke(self, messages):
            return _FakeResp([{"text": '{"a":'}, {"text": "1}"}])
    out = asyncio.run(acell_llm_call("s", "u", llm=_BlockLLM()))
    assert json.loads(out) == {"a": 1}


def test_make_cell_llm_builds_offline():
    llm = make_cell_llm(api_key="x")  # no network on construction
    assert llm is not None
    assert hasattr(llm, "ainvoke")
