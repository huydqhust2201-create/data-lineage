from typing import Any, cast

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config import get_settings


def get_llm(
    *, temperature: float | None = None, tools: list[Any] | None = None, structured: type[BaseModel] | None = None
) -> Any:
    """Build the chat LLM and optionally bind tools or structured output."""
    settings = get_settings()
    llm: Any = ChatOpenAI(
        model=settings.model_name,
        api_key=cast(Any, settings.openrouter_api_key),
        base_url=settings.openrouter_base_url,
        temperature=settings.llm_temperature if temperature is None else temperature,
    )
    if tools:
        llm = llm.bind_tools(tools)
    return llm.with_structured_output(structured) if structured else llm
