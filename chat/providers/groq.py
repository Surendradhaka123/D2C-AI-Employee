import json
import os

from chat.providers.base import BaseProvider, ProviderResponse, ToolCall

MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")


def _to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """
    Anthropic format → OpenAI/Groq format.

    Anthropic: {"name": ..., "description": ..., "input_schema": {...}}
    OpenAI:    {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
    """
    result = []
    for t in anthropic_tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return result


class GroqProvider(BaseProvider):
    """
    Uses Groq's OpenAI-compatible API.

    System prompt is injected as the first message (role="system") since
    Groq follows the OpenAI messages format, not Anthropic's separate system param.
    """

    def __init__(self):
        try:
            from groq import Groq
        except ImportError:
            raise ImportError("Run: pip install groq")
        self._client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

    def complete(self, messages, tools, system) -> ProviderResponse:
        groq_messages = [{"role": "system", "content": system}] + messages
        groq_tools = _to_openai_tools(tools)

        response = self._client.chat.completions.create(
            model=MODEL,
            messages=groq_messages,
            tools=groq_tools,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = response.choices[0]
        message = choice.message

        text = message.content or ""
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    inputs = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    inputs = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, inputs=inputs))

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            wants_tool_use=choice.finish_reason == "tool_calls",
            _raw=message,
        )

    def build_tool_result_message(self, response, raw_message, tool_results):
        assistant_msg = {
            "role": "assistant",
            "content": raw_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.inputs, ensure_ascii=False),
                    },
                }
                for tc in response.tool_calls
            ],
        }
        tool_msgs = [
            {
                "role": "tool",
                "tool_call_id": r["tool_call_id"],
                "content": r["content"],
            }
            for r in tool_results
        ]
        return [assistant_msg] + tool_msgs
