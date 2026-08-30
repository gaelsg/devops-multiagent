from __future__ import annotations

from opentelemetry import trace

from devops_multiagent.agent import AgentResult, run_agent
from devops_multiagent.diagnostician import PROXMOX_SERVER
from devops_multiagent.mcp_tools import ToolRegistry

_tracer = trace.get_tracer("devops-multiagent")

SYSTEM_PROMPT = """Eres el Operator de un sistema DevOps para un cluster Proxmox VE casero.
Puedes leer estado y ejecutar acciones de power management (start_resource, stop_resource,
restart_resource) sobre VMs y contenedores. Estas acciones requieren aprobacion humana explicita
por adelantado (ya otorgada o no antes de que actues, tu no la pides en la conversacion). Si una
tool de escritura devuelve status "blocked_pending_approval", informa claramente al usuario que la
accion quedo pendiente de aprobacion y no se ejecuto - no la reintentes ni asumas que si paso.
Responde en espanol, se conciso."""

WRITE_TOOLS = {"start_resource", "stop_resource", "restart_resource"}


def _make_operator_gate(approved: bool):
    def gate(name: str, _arguments: dict) -> bool:
        if name in WRITE_TOOLS:
            return approved
        return True

    return gate


async def operate(user_message: str, approved: bool = False) -> tuple[AgentResult, ToolRegistry]:
    """approved=False: las tools de escritura se anuncian (el modelo puede razonar sobre ellas)
    pero cualquier intento real de ejecutarlas queda bloqueado en el ToolRegistry, no en el
    criterio del modelo."""
    with _tracer.start_as_current_span(
        "operate", attributes={"gen_ai.operation.name": "operate", "operator.approved": approved}
    ):
        registry = ToolRegistry()
        try:
            await registry.connect(
                "proxmox", PROXMOX_SERVER, gate=_make_operator_gate(approved), hide_when_gated=False
            )
            result = await run_agent(SYSTEM_PROMPT, user_message, registry)
            return result, registry
        finally:
            await registry.close()
