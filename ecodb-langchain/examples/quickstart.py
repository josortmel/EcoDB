"""Quickstart — a LangGraph agent that thinks with EcoDB.

Prereqs:
    pip install -e ".[openai]"
    export ECODB_API_URL=http://localhost:8080
    export ECODB_API_KEY=ecodb_...
    export CELL_LLM_KEY=...          # DeepSeek (or DEEPSEEK_API_KEY)

Run:
    python examples/quickstart.py
"""

from ecodb_langchain import EcoDBClient, build_ecodb_agent, default_llm

# 1) Client + (any) model. default_llm() points at DeepSeek via base_url; swap freely.
client = EcoDBClient(agent_identifier="Eco")  # reads ECODB_API_URL / ECODB_API_KEY from env
llm = default_llm()

# 2) Compile the LangGraph agent (StateGraph ReAct loop over the EcoDB tools).
agent = build_ecodb_agent(llm=llm, client=client)

# 3) Ask it something that requires recalling and/or navigating the graph.
result = agent.invoke(
    {"messages": [("user", "What do we know about EcoDB's retrieval engine? Check memory and the graph.")]}
)
print(result["messages"][-1].content)


# --- Using the pieces directly (without the agent) ---------------------------
#
# from ecodb_langchain import EcoDBRetriever, EcoDBMemory, make_ecodb_tools
#
# retriever = EcoDBRetriever(client=client, k=6)
# docs = retriever.invoke("decisions about Azure")
#
# tools = make_ecodb_tools(client)          # hand to any LangChain/LangGraph agent
# memory = EcoDBMemory(client=client)       # durable, cross-session chain memory
