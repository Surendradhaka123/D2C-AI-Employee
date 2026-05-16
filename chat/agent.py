"""
Claude tool-use loop with hard citation enforcement.

Flow:
  1. Send user message + tool definitions to Claude
  2. If Claude calls a tool → execute it, send result back
  3. Repeat until Claude returns stop_reason == "end_turn"
  4. Post-process response through citation enforcer
  5. If bare numbers found → retry (max 2 retries)
  6. If still uncited after 2 retries → return grounding_failure error
"""

import json
import os
from typing import Generator

import anthropic

from chat.tools import TOOL_DEFINITIONS, handle_tool
from chat.citations import SYSTEM_PROMPT, enforce_citations, CITATION_RETRY_PROMPT

MAX_CITATION_RETRIES = 2
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

_client = anthropic.Anthropic()


def chat(
    merchant_id: str,
    user_message: str,
    history: list[dict] | None = None,
) -> dict:
    """
    Run a single chat turn. Returns:
      {"response": str, "tool_calls": int, "citation_retries": int}
    or on grounding failure:
      {"error": "grounding_failure", "message": str}
    """
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    tool_call_count = 0
    citation_retry_count = 0

    # Tool-use loop
    while True:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Collect any text blocks
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if response.stop_reason == "tool_use" and tool_use_blocks:
            # Execute all tool calls
            tool_results = []
            for block in tool_use_blocks:
                tool_call_count += 1
                try:
                    result = handle_tool(block.name, block.input)
                except Exception as exc:
                    result = {"error": str(exc)}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Append assistant turn + tool results to history
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        # Claude finished — enforce citations
        final_text = "\n".join(text_blocks)

        for attempt in range(MAX_CITATION_RETRIES + 1):
            is_clean, violations = enforce_citations(final_text)
            if is_clean:
                break

            if attempt == MAX_CITATION_RETRIES:
                return {
                    "error": "grounding_failure",
                    "message": (
                        "Could not produce a fully-cited answer after "
                        f"{MAX_CITATION_RETRIES} retries. Uncited values: {violations}"
                    ),
                }

            # Ask Claude to fix citations
            citation_retry_count += 1
            retry_prompt = CITATION_RETRY_PROMPT.format(violations=violations)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": retry_prompt})

            retry_resp = _client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
            final_text = "\n".join(
                b.text for b in retry_resp.content if hasattr(b, "text")
            )

        return {
            "response": final_text,
            "tool_calls": tool_call_count,
            "citation_retries": citation_retry_count,
        }


def chat_repl(merchant_id: str) -> None:
    """Interactive REPL for testing the chat layer."""
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    history: list[dict] = []

    console.print(Panel(
        f"[bold green]D2C AI Employee[/bold green]\n"
        f"Merchant: [cyan]{merchant_id}[/cyan]\n"
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

        with console.status("[bold yellow]Thinking...[/bold yellow]"):
            result = chat(merchant_id, user_input, history)

        if "error" in result:
            console.print(f"[red]Error:[/red] {result['message']}")
        else:
            console.print(Markdown(result["response"]))
            console.print(
                f"[dim](tools called: {result['tool_calls']}, citation retries: {result['citation_retries']})[/dim]"
            )
            # Persist conversation history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": result["response"]})
