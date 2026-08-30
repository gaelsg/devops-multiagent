from __future__ import annotations

from dotenv import load_dotenv

from devops_multiagent.secrets_loader import load_secrets_from_vault

# Tiene que correr ANTES de importar diagnostician/operator/watcher: esos
# modulos importan notify.py, que lee TELEGRAM_* de os.environ en tiempo de
# import (no perezoso) -- si Vault no puso las variables antes de esos
# imports, notify.py se queda con valores vacios para siempre en este proceso.
load_dotenv()
load_secrets_from_vault()

import argparse
import asyncio
import logging

from devops_multiagent.diagnostician import diagnose
from devops_multiagent.operator import operate
from devops_multiagent.watcher import check_once


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="devops-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_diag = sub.add_parser("diagnose", help="Consulta de solo lectura (infra + RAG)")
    p_diag.add_argument("message")

    p_op = sub.add_parser("operate", help="Accion sobre infraestructura (gated)")
    p_op.add_argument("message")
    p_op.add_argument("--approve", action="store_true", help="Autoriza ejecutar tools de escritura")

    sub.add_parser("watch", help="Chequeo unico de estado (para systemd timer), notifica si hay cambios")

    p_serve = sub.add_parser("serve", help="Dashboard web (FastAPI + htmx), solo localhost")
    p_serve.add_argument("--port", type=int, default=8000)

    p_webhook = sub.add_parser(
        "webhook", help="Receptor de webhooks de Alertmanager (LAN, protegido por shared secret)"
    )
    p_webhook.add_argument("--port", type=int, default=8090)

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn

        # Bind solo a localhost a proposito: no hay auth en el dashboard, y
        # Diagnostician igual habla con infra real - mismo modelo de confianza
        # que correr el CLI a mano, no pensado para exponerse en LAN/Tailscale.
        uvicorn.run("devops_multiagent.web.app:app", host="127.0.0.1", port=args.port)
        return

    if args.command == "webhook":
        import uvicorn

        # Bind 0.0.0.0 a proposito, a diferencia de "serve": Alertmanager
        # corre en otro LXC y necesita alcanzar esto por LAN. Superficie
        # angosta a cambio (un solo endpoint, protegido por shared secret,
        # sin panel ni capacidad de escritura) - ver docs/29110 de observability.
        uvicorn.run("devops_multiagent.webhook:app", host="0.0.0.0", port=args.port)
        return

    async def run() -> None:
        if args.command == "diagnose":
            result, registry = await diagnose(args.message)
            print(result.final_text)
            print("\n--- tool calls ---")
            for record in registry.trace:
                estado = "ejecutado" if record.executed else "BLOQUEADO (sin aprobacion)"
                print(f"{record.tool}({record.arguments}) -> {estado}")
        elif args.command == "operate":
            result, registry = await operate(args.message, approved=args.approve)
            print(result.final_text)
            print("\n--- tool calls ---")
            for record in registry.trace:
                estado = "ejecutado" if record.executed else "BLOQUEADO (sin aprobacion)"
                print(f"{record.tool}({record.arguments}) -> {estado}")
        elif args.command == "watch":
            changes = await check_once()
            print(f"cambios detectados: {len(changes)}")
            for change in changes:
                print(f"  - {change}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
