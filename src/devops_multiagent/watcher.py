from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from devops_multiagent import notify
from devops_multiagent.diagnostician import PROXMOX_SERVER, _diagnostician_gate, diagnose
from devops_multiagent.mcp_tools import ToolRegistry

NODE = os.environ.get("WATCHER_NODE", "batman01")
STATE_PATH = Path(
    os.environ.get("WATCHER_STATE_PATH", "~/projects/devops-multiagent/state/last_known.json")
).expanduser()


async def _snapshot() -> dict[str, Any]:
    registry = ToolRegistry()
    try:
        await registry.connect("proxmox", PROXMOX_SERVER, gate=_diagnostician_gate)
        nodes = await registry.call("list_nodes", {})
        containers = await registry.call("list_containers", {"node": NODE})
    finally:
        await registry.close()

    return {
        "nodes": {n["node"]: n["status"] for n in nodes},
        "containers": {
            str(c["vmid"]): {"name": c.get("name"), "status": c["status"]} for c in containers
        },
    }


def _diff(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    changes: list[str] = []

    for node, status in current.get("nodes", {}).items():
        prev_status = previous.get("nodes", {}).get(node)
        if prev_status is not None and prev_status != status:
            changes.append(f"Nodo {node}: {prev_status} -> {status}")

    for vmid, info in current.get("containers", {}).items():
        prev_info = previous.get("containers", {}).get(vmid)
        if prev_info is not None and prev_info["status"] != info["status"]:
            changes.append(
                f"Contenedor {info['name']} (vmid {vmid}): {prev_info['status']} -> {info['status']}"
            )

    return changes


async def check_once() -> list[str]:
    """Compara el estado actual contra el ultimo conocido. Notifica solo si hay cambios reales.

    Primera corrida (sin estado previo): guarda la linea base sin notificar,
    para no disparar una alerta falsa de "todo acaba de aparecer".
    """
    current = await _snapshot()

    if not STATE_PATH.exists():
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(current, indent=2))
        return []

    previous = json.loads(STATE_PATH.read_text())
    changes = _diff(previous, current)

    STATE_PATH.write_text(json.dumps(current, indent=2))

    if changes:
        raw = "\n".join(changes)
        notify.send_telegram(f"⚠️ *Cambio detectado en {NODE}*\n\n{raw}")

        try:
            result, _ = await diagnose(
                f"En el nodo Proxmox '{NODE}' se detectaron estos cambios de estado: "
                + "; ".join(changes)
                + ". Da una explicacion breve de que podria significar y si amerita revisar algo, "
                "basandote en la bitacora si es relevante. Si necesitas consultar el estado actual, "
                f"usa siempre node='{NODE}', no inventes otro nombre de nodo."
            )
            notify.send_telegram(f"🔎 *Diagnostico*\n\n{result.final_text}")
        except Exception as exc:  # noqa: BLE001 - la alerta cruda ya se envio, esto es best-effort
            notify.send_telegram(f"🔎 *Diagnostico*: no se pudo generar ({type(exc).__name__})")

    return changes
