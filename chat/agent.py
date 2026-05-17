"""
Claude tool-use loop — provider-agnostic.

Swap LLM by setting LLM_PROVIDER=groq (or anthropic, the default).
The loop, citation enforcement, and tool dispatch are identical for both.
"""

import json
import os

from chat.providers import get_provider
from chat.tools import TOOL_DEFINITIONS, handle_tool
from chat.citations import SYSTEM_PROMPT, enforce_citations, CITATION_RETRY_PROMPT

MAX_CITATION_RETRIES = 2
MAX_PROVIDER_RETRIES = 2


def chat(
    merchant_id: str,
    user_message: str,
    history: list[dict] | None = None,
) -> dict:
    """
    Single chat turn. Returns:
      {"response": str, "tool_calls": int, "citation_retries": int, "provider": str}
    or on grounding failure:
      {"error": "grounding_failure", "message": str}
    or on provider failure:
      {"error": "provider_failure", "message": str}
    """
    provider = get_provider()
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    tool_call_count = 0
    citation_retry_count = 0
    provider_error_count = 0

    # ── Tool-use loop ────────────────────────────────────────────────────────
    while True:
        # Protect provider.complete() — if the LLM API fails, feed the error
        # back as a user message so the loop can retry without crashing.
        try:
            response = provider.complete(messages, TOOL_DEFINITIONS, SYSTEM_PROMPT)
            provider_error_count = 0  # reset on success
        except Exception as exc:
            provider_error_count += 1
            if provider_error_count > MAX_PROVIDER_RETRIES:
                return {
                    "error": "provider_failure",
                    "message": f"LLM API failed {MAX_PROVIDER_RETRIES} times: {exc}",
                }
            messages.append({
                "role": "user",
                "content": (
                    f"[system: the previous request to the LLM API failed with: {exc}. "
                    "Please try again.]"
                ),
            })
            continue

        if response.wants_tool_use and response.tool_calls:
            tool_results = []
            for tc in response.tool_calls:
                tool_call_count += 1
                try:
                    result = handle_tool(tc.name, tc.inputs, merchant_id=merchant_id)
                except Exception as exc:
                    # Structured error so the LLM sees what failed and can retry
                    result = {
                        "status": "tool_error",
                        "tool": tc.name,
                        "error": str(exc),
                        "hint": (
                            "This tool call failed. Check the parameters and retry "
                            "with corrected inputs. If the error persists, report it "
                            "to the user."
                        ),
                    }
                tool_results.append({
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            new_messages = provider.build_tool_result_message(
                response, response._raw, tool_results
            )
            messages.extend(new_messages)
            continue

        # ── Citation enforcement ─────────────────────────────────────────────
        final_text = response.text

        for attempt in range(MAX_CITATION_RETRIES + 1):
            is_clean, violations = enforce_citations(final_text)
            if is_clean:
                break

            if attempt == MAX_CITATION_RETRIES:
                return {
                    "error": "grounding_failure",
                    "message": (
                        f"Could not produce a fully-cited answer after "
                        f"{MAX_CITATION_RETRIES} retries. Uncited values: {violations}"
                    ),
                }

            citation_retry_count += 1
            retry_prompt = CITATION_RETRY_PROMPT.format(violations=violations)
            messages.append({"role": "assistant", "content": final_text})
            messages.append({"role": "user", "content": retry_prompt})

            retry_resp = provider.complete(messages, TOOL_DEFINITIONS, SYSTEM_PROMPT)
            final_text = retry_resp.text

        return {
            "response": final_text,
            "tool_calls": tool_call_count,
            "citation_retries": citation_retry_count,
            "provider": os.getenv("LLM_PROVIDER", "anthropic"),
        }


def chat_repl(merchant_id: str) -> None:
    """Interactive REPL for testing the chat layer."""
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    provider_name = os.getenv("LLM_PROVIDER", "anthropic").upper()
    console = Console()
    history: list[dict] = []

    console.print(Panel(
        f"[bold green]D2C AI Employee[/bold green]\n"
        f"Merchant: [cyan]{merchant_id}[/cyan]  Provider: [yellow]{provider_name}[/yellow]\n"
        f"Type 'quit' to exit.",
        title="Chat",
    ))

    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        with console.status(f"[bold yellow]Thinking ({provider_name})...[/bold yellow]"):
            result = chat(merchant_id, user_input, history)

        if "error" in result:
            console.print(f"[red]Error:[/red] {result['message']}")
        else:
            console.print(Markdown(result["response"]))
            console.print(
                f"[dim](provider: {result['provider']} | "
                f"tool calls: {result['tool_calls']} | "
                f"citation retries: {result['citation_retries']})[/dim]"
            )
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": result["response"]})
