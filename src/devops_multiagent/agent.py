from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import requests

from devops_multiagent.mcp_tools import ToolRegistry

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen3:14b")
MAX_TURNS = 6


@dataclass
class AgentResult:
    final_text: str
    messages: list[dict[str, Any]] = field(default_factory=list)


def _chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={"model": MODEL, "messages": messages, "tools": tools, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]


async def run_agent(system_prompt: str, user_message: str, registry: ToolRegistry) -> AgentResult:
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
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return AgentResult(final_text="(max_turns alcanzado sin respuesta final)", messages=messages)
