from __future__ import annotations

from mcp import StdioServerParameters

from devops_multiagent.agent import AgentResult, OnEvent, run_agent
from devops_multiagent.mcp_tools import ToolRegistry

SYSTEM_PROMPT = """Eres el Diagnostician de un sistema DevOps para un cluster Proxmox VE casero.
Solo puedes leer estado (nodos, VMs, contenedores) y buscar en la base de conocimiento (bitacoras
del proyecto). No tienes ninguna capacidad de escritura. Responde en espanol, se conciso, y basa
tus respuestas en los datos reales que obtengas de las tools, nunca inventes estados o datos."""

PROXMOX_SERVER = StdioServerParameters(
    command="uv",
    args=[
        "run",
        "--directory",
        "/home/gaelsg/projects/proxmox-mcp-server",
        "proxmox-mcp-server",
    ],
)

RAG_SERVER = StdioServerParameters(
    command="uv",
    args=["run", "--directory", "/home/gaelsg/projects/rag-mcp-server", "rag-mcp-server"],
)

READ_ONLY_TOOLS = {"list_nodes", "list_vms", "list_containers", "get_resource_status"}


def _diagnostician_gate(name: str, _arguments: dict) -> bool:
    return name in READ_ONLY_TOOLS


async def diagnose(user_message: str, on_event: OnEvent | None = None) -> tuple[AgentResult, ToolRegistry]:
    registry = ToolRegistry()
    try:
        await registry.connect("proxmox", PROXMOX_SERVER, gate=_diagnostician_gate)
        await registry.connect("rag", RAG_SERVER)
        result = await run_agent(SYSTEM_PROMPT, user_message, registry, on_event=on_event)
        return result, registry
    finally:
        await registry.close()
