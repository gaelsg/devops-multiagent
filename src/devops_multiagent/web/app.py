from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from devops_multiagent.diagnostician import diagnose

AUDIT_LOG = Path("/home/gaelsg/projects/proxmox-mcp-server/docs/audit/actions.jsonl")
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="devops-multiagent dashboard")


def _read_audit(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_LOG.exists():
        return []
    lines = [line for line in AUDIT_LOG.read_text().splitlines() if line.strip()]
    entries = [json.loads(line) for line in lines[-limit:]]
    entries.reverse()
    return entries


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"audit": _read_audit()})


@app.get("/audit", response_class=HTMLResponse)
async def audit(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "_audit.html", {"audit": _read_audit()})


@app.get("/diagnose/start", response_class=HTMLResponse)
async def diagnose_start(request: Request, message: str = Query(...)) -> HTMLResponse:
    return templates.TemplateResponse(request, "_trace_container.html", {"message": message})


def _sse(event_type: str, html: str) -> str:
    # SSE no soporta multilinea en "data:" sin repetir el prefijo por linea.
    data = "".join(f"data: {chunk}\n" for chunk in html.splitlines()) or "data: \n"
    return f"event: {event_type}\n{data}\n"


async def _diagnose_events(message: str):
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_event(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            result, _registry = await diagnose(message, on_event=on_event)
            await queue.put({"type": "final", "text": result.final_text})
        except Exception as exc:  # noqa: BLE001 - se reporta al cliente, no se oculta
            await queue.put({"type": "error", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            if event["type"] == "tool_call":
                html = templates.get_template("_tool_call_event.html").render(event=event)
                yield _sse("tool_call", html)
            elif event["type"] == "final":
                html = templates.get_template("_final_event.html").render(event=event)
                yield _sse("final", html)
            else:
                html = templates.get_template("_error_event.html").render(event=event)
                yield _sse("final", html)
        # Cierra la conexion SSE del lado servidor; htmx-ext-sse no reconecta
        # sola sin esto y quedaria "escuchando" un stream ya terminado.
        yield _sse("close", "")
    finally:
        await task


@app.get("/diagnose/stream")
async def diagnose_stream(message: str = Query(...)) -> StreamingResponse:
    return StreamingResponse(_diagnose_events(message), media_type="text/event-stream")
