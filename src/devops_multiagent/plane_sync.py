from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from devops_multiagent.diagnostician import RAG_SERVER
from devops_multiagent.mcp_tools import ToolRegistry

# Un archivo .md por issue, nombrado por sequence_id (numero corto y
# estable dentro del proyecto, no el UUID) -- se sobreescribe en cada
# update. index_corpus() en rag-mcp-server reindexa TODO lo que haya en
# este directorio junto con las bitacoras existentes, mismo patron de
# "corpus = archivos en disco" que ya usa el resto del portafolio, sin
# inventar un pipeline de indexado incremental nuevo.
CORPUS_DIR = Path.home() / "projects" / "rag-mcp-server" / "docs" / "plane-sync"

# Verificado empiricamente (tabla webhook_logs en Postgres, 2026-09-01):
# Plane NUNCA envia un webhook para el delete de un issue en esta version
# -- solo "created"/"updated" aparecen en el log de entregas, pese a que
# webhook_task.py tiene codigo preparado para un payload de delete
# ({"id": event_id} si verb == "deleted"). El branch de abajo para
# action in ("delete", "deleted") queda por las dudas (defensivo, sin
# costo) pero HOY es codigo muerto -- issues borrados en Plane dejan un
# archivo huerfano en el corpus hasta una limpieza manual o un futuro
# reconciliador periodico. Ver docs/bitacora/.
_INDEX_PATH = CORPUS_DIR / "_index.json"


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


async def trigger_reindex() -> dict[str, Any]:
    registry = ToolRegistry()
    try:
        await registry.connect("rag", RAG_SERVER)
        return await registry.call("index_corpus", {})
    finally:
        await registry.close()
