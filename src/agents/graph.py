from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.nodes.lineage_nodes import (
    describe_columns_node,
    describe_node,
    embed_sql_node,
    graph_build_node,
    hitl_node,
    llm_extract_node,
    parse_node,
)
from src.agents.nodes.query_nodes import (
    agent_node,
    compose_node,
    route_after_agent,
    route_after_tools,
    tools_node,
    verify_node,
)
from src.agents.state import ChatAgentState, LineageAgentState


def build_graph() -> StateGraph:
    """parse -> llm_extract (no-op nếu không có file fail) -> hitl (phân loại
    confirmed/pending) -> graph_build (ghi + persist). Xem ARCHITECTURE.md
    mục "Agent Flow" và PRD.md mục 6 (FR-1..FR-5).
    """
    graph = StateGraph(LineageAgentState)

    graph.add_node("parse", parse_node)
    graph.add_node("llm_extract", llm_extract_node)
    graph.add_node("hitl", hitl_node)
    graph.add_node("graph_build", graph_build_node)
    graph.add_node("describe", describe_node)
    graph.add_node("describe_columns", describe_columns_node)
    graph.add_node("embed_sql", embed_sql_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "llm_extract")
    graph.add_edge("llm_extract", "hitl")
    graph.add_edge("hitl", "graph_build")
    graph.add_edge("graph_build", "describe")
    graph.add_edge("describe", "describe_columns")
    graph.add_edge("describe_columns", "embed_sql")
    graph.add_edge("embed_sql", END)

    return graph.compile()


agent = build_graph()


def build_chat_graph() -> Any:
    """Build the bounded chat tool loop without changing the ingest graph."""
    graph = StateGraph(ChatAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("compose", compose_node)
    graph.add_node("verify", verify_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "compose": "compose"})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "compose": "compose"})
    graph.add_edge("compose", "verify")
    graph.add_edge("verify", END)
    return graph.compile()
