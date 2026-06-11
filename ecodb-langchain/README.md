# ecodb-langchain

**LangChain & LangGraph integration for [EcoDB](../README.md) — give your agents memory and a knowledge graph in three lines.**

```python
from ecodb_langchain import build_ecodb_agent

agent = build_ecodb_agent()  # LangGraph StateGraph agent, EcoDB tools, DeepSeek by default
agent.invoke({"messages": [("user", "What did we decide about Azure? Check memory and the graph.")]})
```

That's a full ReAct agent that recalls long-term memory (GAMR retrieval), navigates the knowledge graph, and writes new memories back — all over EcoDB's REST API.

---

## What you get

| Piece | Class / fn | What it is |
|---|---|---|
| **Agent** | `build_ecodb_agent` | A compiled **LangGraph `StateGraph`** ReAct loop wired to the EcoDB tools. Model-agnostic. |
| **Tools** | `make_ecodb_tools` | 9 LangChain tools at parity with EcoDB's agentic MCP surface: `search`, `search_recent`, `save_memory`, `read_memory`, graph `neighbors` / `path` / `search_nodes` / `status`, `save_triple`. |
| **Retriever** | `EcoDBRetriever` | A `BaseRetriever` over GAMR search — drop into any RAG chain. |
| **Memory** | `EcoDBMemory` | A `BaseMemory` with durable, cross-session storage in EcoDB. |
| **Client** | `EcoDBClient` | A faithful sync REST client (JWT auth + 401 refresh) — endpoints mirror the MCP server. |

## Install

```bash
pip install -e ".[openai]"
```

## Configure

```bash
export ECODB_API_URL=http://localhost:8080
export ECODB_API_KEY=ecodb_...
export CELL_LLM_KEY=...          # DeepSeek key (or DEEPSEEK_API_KEY)
```

## The graph

```
START ─▶ agent ──(tool call?)──▶ tools ──▶ agent ──▶ END
```

The `agent` node runs an LLM bound to the EcoDB tools; the `tools` node executes
calls and feeds results back until the model answers. Built with an explicit
`StateGraph` (not just a prebuilt) so the loop is inspectable and extensible.

## Model-agnostic

`build_ecodb_agent` takes any LangChain `BaseChatModel`. `default_llm()` points at
DeepSeek through an OpenAI-compatible `base_url` — swap in Claude, a local model,
or any OpenAI-compatible endpoint without touching the graph.

```python
from langchain_openai import ChatOpenAI
from ecodb_langchain import build_ecodb_agent
agent = build_ecodb_agent(llm=ChatOpenAI(model="gpt-4o-mini"))
```

## Security

Retrieved memories are treated as **data, not instructions**: the default system
prompt forbids the agent from obeying directions embedded inside stored content
(prompt-injection guard).

## Use the pieces directly

```python
from ecodb_langchain import EcoDBClient, EcoDBRetriever, EcoDBMemory, make_ecodb_tools

client = EcoDBClient(agent_identifier="Eco")
retriever = EcoDBRetriever(client=client, k=6)     # any RAG chain
tools = make_ecodb_tools(client)                   # any LangChain/LangGraph agent
memory = EcoDBMemory(client=client)                # durable chain memory
```

## License

PolyForm Noncommercial 1.0.0 — same as EcoDB. Commercial use requires a license from Eco Consulting.
