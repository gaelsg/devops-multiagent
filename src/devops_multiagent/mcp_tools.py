from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Callable

from mcp import StdioServerParameters
from mcp.client import Client


@dataclass
class ToolCallRecord:
    tool: str
    arguments: dict[str, Any]
    executed: bool
    result: Any


Gate = Callable[[str, dict[str, Any]], bool]


class ToolRegistry:
    """Conecta a uno o mas servidores MCP via stdio y expone sus tools en formato Ollama.

    Un `gate` opcional por servidor decide, tool por tool, si una llamada se
    ejecuta de verdad o queda bloqueada (usado por Operator para las tools de
    escritura sin aprobacion explicita).
    """

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._tool_specs: list[dict[str, Any]] = []
        self._tool_to_client: dict[str, Client] = {}
        self._gates: dict[str, Gate] = {}
        self.trace: list[ToolCallRecord] = []

    async def connect(
        self,
        label: str,
        params: StdioServerParameters,
        gate: Gate | None = None,
        hide_when_gated: bool = True,
    ) -> None:
        client = Client(params)
        await self._exit_stack.enter_async_context(client)
        self._clients[label] = client

        listed = await client.list_tools()
        for tool in listed.tools:
            self._tool_to_client[tool.name] = client
            if gate is not None:
                self._gates[tool.name] = gate
                if hide_when_gated and not gate(tool.name, {}):
                    # Ni siquiera se anuncia al modelo: no puede intentar
                    # llamar lo que no ve, no solo queda bloqueado al llamarlo.
                    continue
            self._tool_specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.input_schema,
                    },
                }
            )

    async def close(self) -> None:
        await self._exit_stack.aclose()

    @property
    def ollama_tools(self) -> list[dict[str, Any]]:
        return self._tool_specs

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        gate = self._gates.get(name)
        if gate is not None and not gate(name, arguments):
            result = {"status": "blocked_pending_approval", "tool": name, "arguments": arguments}
            self.trace.append(
                ToolCallRecord(tool=name, arguments=arguments, executed=False, result=result)
            )
            return result

        client = self._tool_to_client[name]
        call_result = await client.call_tool(name, arguments)
        if call_result.structured_content is not None:
            value: Any = call_result.structured_content
        else:
            value = [block.text for block in call_result.content if hasattr(block, "text")]

        self.trace.append(
            ToolCallRecord(tool=name, arguments=arguments, executed=True, result=value)
        )
        if call_result.is_error:
            raise RuntimeError(f"Tool {name} devolvio error: {value}")
        return value
