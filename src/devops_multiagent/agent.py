from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import requests
from opentelemetry import trace

from devops_multiagent.mcp_tools import ToolRegistry

OnEvent = Callable[[dict[str, Any]], Awaitable[None]]

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen3:14b")
MAX_TURNS = 6

_tracer = trace.get_tracer("devops-multiagent")


@dataclass
class AgentResult:
    final_text: str
    messages: list[dict[str, Any]] = field(default_factory=list)


def _chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    # Mismas convenciones semanticas gen_ai.* que usa el middleware de
    # OpenTelemetry embebido en el SDK de MCP para las tool calls -- un
    # solo vocabulario de atributos en todo el trace, no dos.
    with _tracer.start_as_current_span(
        "ollama.chat",
        attributes={
            "gen_ai.system": "ollama",
            "gen_ai.request.model": MODEL,
            "gen_ai.operation.name": "chat",
        },
    ) as span:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": MODEL, "messages": messages, "tools": tools, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        if "eval_count" in data:
            span.set_attribute("gen_ai.usage.output_tokens", data["eval_count"])
        if "prompt_eval_count" in data:
            span.set_attribute("gen_ai.usage.input_tokens", data["prompt_eval_count"])
        return data["message"]


async def run_agent(
    system_prompt: str,
    user_message: str,
    registry: ToolRegistry,
    on_event: OnEvent | None = None,
) -> AgentResult:
    """`on_event`, si se pasa, se invoca despues de cada tool-call real con
    {"type": "tool_call", "tool": ..., "arguments": ..., "result": ...} -
    permite a un consumidor (ej. el dashboard web via SSE) mostrar el trace
    en vivo sin acoplar este modulo a como se sirve esa UI."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TURNS):
        message = _chat(messages, registry.ollama_tools)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # qwen3 a veces deja "content" vacio y pone la respuesta final en
            # "thinking" (modelo hibrido de razonamiento) - fallback necesario,
            # no un caso raro: ocurrio en la mayoria de las pruebas manuales.
            final_text = message.get("content") or message.get("thinking") or ""
            return AgentResult(final_text=final_text, messages=messages)

        for call in tool_calls:
            fn = call["function"]
            result = await registry.call(fn["name"], fn["arguments"])
            if on_event is not None:
                await on_event(
                    {"type": "tool_call", "tool": fn["name"], "arguments": fn["arguments"], "result": result}
                )
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return AgentResult(final_text="(max_turns alcanzado sin respuesta final)", messages=messages)
