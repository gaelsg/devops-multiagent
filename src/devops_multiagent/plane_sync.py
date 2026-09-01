from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any, Iterator

import requests

from devops_multiagent.diagnostician import RAG_SERVER
from devops_multiagent.mcp_tools import ToolRegistry

PLANE_HOST = os.environ.get("PLANE_HOST", "http://192.168.8.93")

# Un archivo .md por issue, nombrado por sequence_id (numero corto y
# estable dentro del proyecto, no el UUID) -- se sobreescribe en cada
# update. index_corpus() en rag-mcp-server reindexa TODO lo que haya en
# este directorio junto con las bitacoras existentes, mismo patron de
# "corpus = archivos en disco" que ya usa el resto del portafolio, sin
# inventar un pipeline de indexado incremental nuevo.
CORPUS_DIR = Path.home() / "projects" / "rag-mcp-server" / "docs" / "plane-sync"

# Verificado empiricamente (tabla webhook_logs en Postgres, 2026-09-01):
# Plane NUNCA envia un webhook para el delete de un ISSUE en esta version
# -- solo "created"/"updated" aparecen en el log de entregas, pese a que
# webhook_task.py tiene codigo preparado para un payload de delete
# ({"id": event_id} si verb == "deleted"). El branch de abajo para
# action in ("delete", "deleted") queda por las dudas (defensivo, sin
# costo) pero HOY es codigo muerto para issues -- dejan un archivo huerfano
# en el corpus hasta una limpieza manual o un futuro reconciliador
# periodico. No se re-verifico el mismo comportamiento para comentarios
# (issue_comment) por separado -- asumido igual hasta ver lo contrario.
# Ver docs/bitacora/.
_INDEX_PATH = CORPUS_DIR / "_index.json"


def _strip_html(text: str) -> str:
    # El payload de "issue_comment" trae comment_html pero, a diferencia de
    # los issues, NO trae comment_stripped ya calculado (verificado con el
    # payload real -- el campo simplemente no esta en el serializer de
    # comentarios) -- se deriva aca con el mismo criterio que usa Plane
    # server-side (strip_tags), sin sumar una dependencia de parsing HTML
    # para algo tan simple.
    return re.sub(r"<[^>]+>", "", text).strip()


def verify_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    """HMAC-SHA256 sobre el body crudo -- mismo calculo que hace Plane en
    webhook_task.py (hmac.new(secret, json.dumps(payload).encode(), sha256)),
    verificado aca sobre los bytes tal cual llegaron, no re-serializando el
    JSON (evita cualquier diferencia de orden de claves/espacios)."""
    if not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _load_index() -> dict[str, str]:
    if _INDEX_PATH.is_file():
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    return {}


def _save_index(index: dict[str, str]) -> None:
    _INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")


def sync_issue(workspace_slug: str, action: str, data: dict[str, Any]) -> Path | None:
    issue_id = data.get("id")
    if issue_id is None:
        return None

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    index = _load_index()

    if action in ("delete", "deleted"):
        filename = index.pop(issue_id, None)
        if filename is None:
            return None
        path = CORPUS_DIR / filename
        path.unlink(missing_ok=True)
        _save_index(index)
        return path

    sequence_id = data.get("sequence_id")
    if sequence_id is None:
        return None

    # index_corpus() en rag-mcp-server solo indexa archivos que EMPIEZAN con
    # un digito (glob "[0-9]*.md", pensado originalmente para nombres tipo
    # bitacora "2026-08-30-*.md") -- el nombre tiene que arrancar con
    # sequence_id, no con el slug, o el reindex los ignora en silencio
    # (incidente real: primer test end-to-end escribio el archivo pero
    # nunca aparecio en Qdrant hasta corregir esto).
    filename = f"{sequence_id}-{workspace_slug}.md"
    path = CORPUS_DIR / filename

    name = data.get("name", "(sin titulo)")
    state = (data.get("state") or {}).get("name", "?")
    priority = data.get("priority") or "sin prioridad"
    description = data.get("description_stripped") or "(sin descripcion)"

    content = (
        f"## {name}\n\n"
        f"Workspace: {workspace_slug} | Issue #{sequence_id} | Estado: {state} | Prioridad: {priority}\n\n"
        f"{description}\n"
    )
    path.write_text(content, encoding="utf-8")

    index[issue_id] = filename
    _save_index(index)
    return path


def sync_comment(workspace_slug: str, action: str, data: dict[str, Any]) -> Path | None:
    comment_id = data.get("id")
    if comment_id is None:
        return None

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    index = _load_index()

    if action in ("delete", "deleted"):
        filename = index.pop(comment_id, None)
        if filename is None:
            return None
        path = CORPUS_DIR / filename
        path.unlink(missing_ok=True)
        _save_index(index)
        return path

    # A diferencia de un issue, un comentario no tiene un sequence_id corto
    # -- se asigna un contador propio la primera vez que se ve su id (mismo
    # indice que ya se usa para issues, distinta clave: los UUID de Plane
    # no colisionan con la clave reservada "_counter"). El nombre queda
    # estable entre updates del mismo comentario (se reusa si ya existia).
    filename = index.get(comment_id)
    if filename is None:
        counter = int(index.get("_counter", "0")) + 1
        index["_counter"] = str(counter)
        filename = f"{counter}-{workspace_slug}-comentario.md"

    path = CORPUS_DIR / filename
    comment_text = data.get("comment_stripped") or _strip_html(data.get("comment_html", "")) or "(sin contenido)"

    # Da contexto legible del issue padre si ya esta sincronizado (mismo
    # indice, la entrada del issue guarda su propio archivo -- se lee su
    # primer linea, que siempre es "## <titulo>").
    issue_context = f"issue {data.get('issue', '?')}"
    issue_filename = index.get(data.get("issue", ""))
    if issue_filename:
        issue_path = CORPUS_DIR / issue_filename
        if issue_path.is_file():
            first_line = issue_path.read_text(encoding="utf-8").splitlines()[0]
            issue_context = first_line.lstrip("#").strip()

    content = f"## Comentario en: {issue_context}\n\n{comment_text}\n"
    path.write_text(content, encoding="utf-8")

    index[comment_id] = filename
    _save_index(index)
    return path


def _paginated_get(url: str, headers: dict[str, str]) -> Iterator[dict[str, Any]]:
    params: dict[str, str] = {}
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        yield from data.get("results", [])
        if not data.get("next_page_results"):
            return
        params["cursor"] = data["next_cursor"]


def reconcile() -> dict[str, Any]:
    """Compara el estado real de Plane (todos los proyectos del workspace,
    no solo "Documentacion" -- el webhook es a nivel workspace) contra el
    indice local, y borra del corpus lo que ya no existe en Plane. Pensado
    para correr periodicamente (systemd timer), no en cada webhook -- Plane
    nunca avisa via webhook cuando se borra un issue o un comentario
    (verificado dos veces, ver docs/bitacora/), asi que esta es la unica
    forma de que el RAG no acumule contenido fantasma indefinidamente.
    Requiere PLANE_API_TOKEN/PLANE_WORKSPACE_SLUG en el entorno (ver
    secrets_loader.load_plane_secrets_from_vault)."""
    token = os.environ["PLANE_API_TOKEN"]
    slug = os.environ["PLANE_WORKSPACE_SLUG"]
    headers = {"x-api-key": token}

    live_ids: set[str] = set()
    projects = list(_paginated_get(f"{PLANE_HOST}/api/v1/workspaces/{slug}/projects/", headers))
    for project in projects:
        project_id = project["id"]
        issues = list(
            _paginated_get(f"{PLANE_HOST}/api/v1/workspaces/{slug}/projects/{project_id}/issues/", headers)
        )
        for issue in issues:
            live_ids.add(issue["id"])
            comments = _paginated_get(
                f"{PLANE_HOST}/api/v1/workspaces/{slug}/projects/{project_id}"
                f"/work-items/{issue['id']}/comments/",
                headers,
            )
            for comment in comments:
                live_ids.add(comment["id"])

    index = _load_index()
    stale_ids = [id_ for id_ in index if id_ != "_counter" and id_ not in live_ids]

    removed: list[str] = []
    for id_ in stale_ids:
        filename = index.pop(id_)
        path = CORPUS_DIR / filename
        if path.is_file():
            path.unlink()
            removed.append(filename)

    if stale_ids:
        _save_index(index)

    return {"projects": len(projects), "live_ids": len(live_ids), "removed": removed}


async def trigger_reindex() -> dict[str, Any]:
    registry = ToolRegistry()
    try:
        await registry.connect("rag", RAG_SERVER)
        return await registry.call("index_corpus", {})
    finally:
        await registry.close()
