"""
Provider abstraction — swap Anthropic ↔ Groq (or any OpenAI-compatible API)
via LLM_PROVIDER env var. The tool-use loop in agent.py never changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    inputs: dict


@dataclass
class ProviderResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    wants_tool_use: bool = False   # True when provider returned tool calls


class BaseProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> ProviderResponse: ...

    @abstractmethod
    def build_tool_result_message(
        self,
        assistant_response: ProviderResponse,
        raw_assistant_content,       # original response content (provider-specific)
        tool_results: list[dict],    # [{"tool_call_id": ..., "content": ...}]
    ) -> list[dict]:
        """Return the messages to append after a tool call round."""
        ...
