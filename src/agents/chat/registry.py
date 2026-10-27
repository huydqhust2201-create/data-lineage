"""Registry and JSON-schema bridge for deterministic chat capabilities."""

from __future__ import annotations

from typing import Any, cast

from langchain_core.tools import StructuredTool

from src.agents.chat.base import Capability
from src.agents.tools.breaking_change_tools import BREAKING_CHANGES_CAPABILITY
from src.agents.tools.ddl_preview_tools import PREVIEW_DDL_IMPACT_CAPABILITY
from src.agents.tools.description_tools import (
    SEARCH_BY_DESCRIPTION_CAPABILITY,
    SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY,
)
from src.agents.tools.graph_tools import LIST_RELATIONSHIPS_CAPABILITY, SEARCH_TABLES_CAPABILITY
from src.agents.tools.impact_tools import ASSESS_CHANGE_CAPABILITY, TRAVERSE_CAPABILITY
from src.agents.tools.query_tools import ANALYZE_QUERY_CAPABILITY

# search_sql_content da rut khoi REGISTRY: chi muc SQL RONG o moi database da do
# (1, 2, 2363) vi do thi duoc ingest truoc khi main them
# buoc embed SQL. Tool nay gio tra error="index_empty" cho moi truy van; dang ky no
# van chi ton mot luot goi de nhan biet chi muc rong, tung lam case 04 mat luot
# goi traverse (3/3 lan do). Dua lai khi nao ingest da nap chi muc;
# sql_document_tools.py giu nguyen.
#
# get_asset da rut khoi REGISTRY o T-0d: khong con cau hoi nao no tra loi duoc ma tool khac
# khong, con vong doi thi rong (1/37 bang co du lieu). asset_tools.py va AssetProfile giu
# nguyen de dua lai re neu ingest sau nay ghi duoc vong doi.
REGISTRY: dict[str, Capability] = {
    capability.name: cast(Capability, capability)
    for capability in (
        TRAVERSE_CAPABILITY,
        ASSESS_CHANGE_CAPABILITY,
        SEARCH_TABLES_CAPABILITY,
        LIST_RELATIONSHIPS_CAPABILITY,
        SEARCH_BY_DESCRIPTION_CAPABILITY,
        SEARCH_COLUMN_BY_DESCRIPTION_CAPABILITY,
        PREVIEW_DDL_IMPACT_CAPABILITY,
        BREAKING_CHANGES_CAPABILITY,
        ANALYZE_QUERY_CAPABILITY,
    )
}


def _never_called(**_: Any) -> str:
    """Fail loudly if a future caller accidentally executes schema-only tools."""
    raise NotImplementedError("Chat capability dispatch belongs to tools_node")


def build_tools() -> list[StructuredTool]:
    """Build schema-only LangChain tools for `bind_tools`."""
    return [
        StructuredTool.from_function(
            func=_never_called,
            name=capability.name,
            description=capability.description,
            args_schema=capability.Params,
        )
        for capability in REGISTRY.values()
    ]


def merged_prompt_rules() -> str:
    """Combine concise capability-specific instructions for the agent prompt."""
    return "\n".join(capability.prompt_rules() for capability in REGISTRY.values())
