import os
import anthropic

from chat.providers.base import BaseProvider, ProviderResponse, ToolCall

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

_client = anthropic.Anthropic()


class AnthropicProvider(BaseProvider):
    """
    Anthropic tool definition format:
      {"name": "...", "description": "...", "input_schema": {...}}

    Tool call response: content blocks with type="tool_use"
    Tool result message: role="user", content=[{type:"tool_result", tool_use_id, content}]
    """

    def complete(self, messages, tools, system) -> ProviderResponse:
        # Tools are already in Anthropic format (from tools.py TOOL_DEFINITIONS)
        response = _client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )

        text = " ".join(b.text for b in response.content if hasattr(b, "text"))
        tool_calls = [
            ToolCall(id=b.id, name=b.name, inputs=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            wants_tool_use=response.stop_reason == "tool_use",
            # Stash raw content so build_tool_result_message can use it
            _raw=response.content,
        )

    def build_tool_result_message(self, response, raw_content, tool_results):
        return [
            {"role": "assistant", "content": raw_content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r["tool_call_id"],
                        "content": r["content"],
                    }
                    for r in tool_results
                ],
            },
        ]


# Patch ProviderResponse to carry raw content without polluting the dataclass
_orig_init = ProviderResponse.__init__

def _patched_init(self, *args, _raw=None, **kwargs):
    _orig_init(self, *args, **kwargs)
    self._raw = _raw

ProviderResponse.__init__ = _patched_init
