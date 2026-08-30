from __future__ import annotations

from mcp import StdioServerParameters

from devops_multiagent.agent import AgentResult, OnEvent, run_agent
from devops_multiagent.mcp_tools import ToolRegistry

SYSTEM_PROMPT = """Eres el Diagnostician de un sistema DevOps para infraestructura casera: un
cluster Proxmox VE y un cluster de Kubernetes (k3s) corriendo sobre el. Solo puedes leer estado
(nodos, VMs, contenedores Proxmox; nodos, pods, deployments, services y logs de Kubernetes) y
buscar en la base de conocimiento (bitacoras del proyecto). No tienes ninguna capacidad de
escritura. Responde en espanol, se conciso, y basa tus respuestas en los datos reales que
obtengas de las tools, nunca inventes estados o datos."""

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

K8S_SERVER = StdioServerParameters(
    command="uv",
    args=["run", "--directory", "/home/gaelsg/projects/k8s-mcp-server", "k8s-mcp-server"],
)

READ_ONLY_TOOLS = {"list_nodes", "list_vms", "list_containers", "get_resource_status"}


def _diagnostician_gate(name: str, _arguments: dict) -> bool:
    return name in READ_ONLY_TOOLS


async def diagnose(user_message: str, on_event: OnEvent | None = None) -> tuple[AgentResult, ToolRegistry]:
    registry = ToolRegistry()
    try:
        await registry.connect("proxmox", PROXMOX_SERVER, gate=_diagnostician_gate)
        await registry.connect("rag", RAG_SERVER)
        # k8s-mcp-server no tiene tools de escritura en absoluto (mismo criterio
        # que docker_tools.py en proxmox-mcp-server) -- no necesita gate.
        await registry.connect("k8s", K8S_SERVER)
        result = await run_agent(SYSTEM_PROMPT, user_message, registry, on_event=on_event)
        return result, registry
    finally:
        await registry.close()
