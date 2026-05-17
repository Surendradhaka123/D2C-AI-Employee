import os
from chat.providers.base import BaseProvider


def get_provider() -> BaseProvider:
    """Return the configured LLM provider. Set LLM_PROVIDER=groq to use Groq."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "groq":
        from chat.providers.groq import GroqProvider
        return GroqProvider()

    from chat.providers.anthropic import AnthropicProvider
    return AnthropicProvider()
