from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from opentelemetry import trace

from devops_multiagent import notify, plane_sync
from devops_multiagent.diagnostician import diagnose

app = FastAPI(title="devops-multiagent alertmanager webhook")
_tracer = trace.get_tracer("devops-multiagent")

WEBHOOK_SHARED_SECRET = os.environ.get("WEBHOOK_SHARED_SECRET", "")
PLANE_WEBHOOK_SECRET = os.environ.get("PLANE_WEBHOOK_SECRET", "")


def _looks_like_alertmanager_payload(payload: Any) -> bool:
    """Chequeo de forma, no autenticacion criptografica - Alertmanager no
    firma sus webhooks nativamente. La defensa real es el shared secret en
    la query string; esto solo descarta ruido que no tiene ni la forma
    correcta antes de gastar una llamada al Diagnostician."""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("alerts"), list)
        and len(payload["alerts"]) > 0
        and all("labels" in a and "status" in a for a in payload["alerts"])
    )


@app.post("/webhook/alertmanager")
async def alertmanager_webhook(request: Request, token: str = Query(...)) -> dict[str, str]:
    # Alertmanager no propaga contexto de trace -- este webhook siempre es
    # una raiz nueva, igual que diagnose()/operate()/watch().
    with _tracer.start_as_current_span(
        "webhook.alertmanager", attributes={"gen_ai.operation.name": "webhook"}
    ):
        return await _handle_alertmanager_webhook(request, token)


async def _handle_alertmanager_webhook(request: Request, token: str) -> dict[str, str]:
    if not WEBHOOK_SHARED_SECRET or token != WEBHOOK_SHARED_SECRET:
        raise HTTPException(status_code=403, detail="token invalido")

    payload = await request.json()
    if not _looks_like_alertmanager_payload(payload):
        raise HTTPException(status_code=400, detail="payload no tiene forma de alerta de Alertmanager")

    # Un mismo payload puede traer una mezcla de alertas firing y resolved
    # (Alertmanager las agrupa) -- status es por-alerta, no del payload entero.
    firing = [a for a in payload["alerts"] if a["status"] == "firing"]
    resolved = [a for a in payload["alerts"] if a["status"] == "resolved"]

    def _summarize(alerts: list[dict[str, Any]]) -> str:
        return "; ".join(
            f"{a['labels'].get('alertname', '?')}: {a.get('annotations', {}).get('summary', '')}"
            for a in alerts
        )

    # Resuelta no necesita investigacion -- es una notificacion simple, sin
    # gastar una llamada al Diagnostician en explicar que algo volvio a la
    # normalidad.
    if resolved:
        notify.send_telegram(f"✅ *Alerta resuelta*\n\n{_summarize(resolved)}")

    if firing:
        alert_text = _summarize(firing)
        notify.send_telegram(f"⚠️ *Alerta de Prometheus*\n\n{alert_text}")

        try:
            result, _ = await diagnose(
                "Prometheus/Alertmanager dispararon esta alerta: "
                + alert_text
                + ". Da una explicacion breve de que podria significar y si amerita revisar algo, "
                "basandote en el estado real de la infraestructura y la bitacora si es relevante."
            )
            notify.send_telegram(f"🔎 *Diagnostico*\n\n{result.final_text}")
        except Exception as exc:  # noqa: BLE001 - la alerta cruda ya se mando, esto es best-effort
            notify.send_telegram(f"🔎 *Diagnostico*: no se pudo generar ({type(exc).__name__})")

    return {"status": "ok"}


# Solo el evento "issue" por ahora (create/update/delete) -- alcance acotado
# a proposito, ver docs/bitacora/. Plane no soporta webhooks para Pages en
# esta version, asi que ese contenido queda para un poller periodico futuro,
# no para este endpoint.
@app.post("/webhook/plane")
async def plane_webhook(request: Request) -> dict[str, str]:
    with _tracer.start_as_current_span("webhook.plane", attributes={"gen_ai.operation.name": "webhook"}):
        return await _handle_plane_webhook(request)


async def _handle_plane_webhook(request: Request) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("x-plane-signature", "")
    if not plane_sync.verify_signature(PLANE_WEBHOOK_SECRET, raw_body, signature):
        raise HTTPException(status_code=403, detail="firma invalida")

    payload = await request.json()
    event = payload.get("event")
    if event != "issue":
        return {"status": "ignored", "event": str(event)}

    action = payload.get("action", "")
    data = payload.get("data") or {}
    workspace_slug = payload.get("workspace_slug", "")

    path = plane_sync.sync_issue(workspace_slug, action, data)
    if path is None:
        return {"status": "skipped", "reason": "sin sequence_id"}

    try:
        await plane_sync.trigger_reindex()
    except Exception as exc:  # noqa: BLE001 - el archivo ya quedo escrito, el reindex es best-effort
        return {"status": "synced_no_reindex", "error": f"{type(exc).__name__}: {exc}"}

    return {"status": "ok", "action": action, "file": str(path)}
