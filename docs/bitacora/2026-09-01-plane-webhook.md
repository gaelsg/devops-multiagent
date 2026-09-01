# 2026-09-01 — Webhook de Plane → reindexado del RAG

Nuevo endpoint `/webhook/plane` en el mismo servicio FastAPI del webhook de Alertmanager
(`devops-agent webhook`, puerto 8090). Cuando se crea o actualiza un *issue* en Plane
(`http://192.168.8.93`, ver `proxmox-iac/docs/bitacora/2026-09-01-plane.md`), Plane manda el
payload completo del issue ya serializado (no hace falta una llamada de vuelta a su API) con una
firma `X-Plane-Signature` (HMAC-SHA256 sobre el body crudo, secreto compartido). Verificada la
firma, se escribe un `.md` en `rag-mcp-server/docs/plane-sync/` y se dispara `index_corpus()` en
`rag-mcp-server` via el mismo `ToolRegistry`/conexion MCP stdio que ya usa el Diagnostician —
ningun pipeline de indexado nuevo, Plane es simplemente otra fuente de archivos del corpus.

Alcance deliberadamente acotado: solo el evento `issue` (no `issue_comment`, `module`, `cycle`,
`project`). Comentarios quedan como pendiente explicito para una iteracion futura.

## Incidentes reales

**1. SSRF: Plane rechazaba crear el webhook.** `Create webhook` fallaba con un error generico en
la UI. Causa (encontrada leyendo `plane/utils/ip_address.py` dentro del contenedor de la API):
Plane bloquea por defecto cualquier IP privada/RFC1918 como destino de webhook (proteccion SSRF
real, no un bug) salvo que este en `WEBHOOK_ALLOWED_IPS`. Corregido seteando
`WEBHOOK_ALLOWED_IPS=192.168.8.219/32` (la IP de la workstation) en `plane.env` y recreando
`api`/`worker`/`beat-worker`/`migrator`.

**2. El archivo se escribia pero nunca aparecia en Qdrant.** `index_corpus()` en rag-mcp-server
solo indexa archivos que empiezan con un digito (`glob("[0-9]*.md")`, pensado originalmente para
nombres tipo bitacora `2026-08-30-*.md`). El primer intento nombraba los archivos
`<workspace_slug>-<sequence_id>.md` (empieza con letra) -- el reindex los ignoraba en silencio,
sin error. Corregido invirtiendo el orden: `<sequence_id>-<workspace_slug>.md`.

**3. Los deletes de issues nunca llegan.** Se implemento un indice local `id -> archivo`
(`docs/plane-sync/_index.json`, no indexado por el glob) para poder borrar el archivo correcto en
un delete, ya que Plane no manda `sequence_id` en ese caso (solo `{"id": ...}`, confirmado leyendo
`webhook_task.py`). Al probarlo con un delete real via API, el archivo nunca se borro -- se
investigo consultando `webhook_logs` directo en Postgres: **Plane nunca intento enviar el
webhook de delete**, ni una sola vez en varias pruebas (la tabla solo tiene entregas `created`/
`updated`). No es un bug de este codigo: es una limitacion real de esta version de Plane para el
evento `issue`. El manejo de delete queda implementado (por si una version futura lo manda) pero
es codigo muerto hoy -- issues borrados en Plane dejan un archivo huerfano en el corpus hasta una
limpieza manual o un reconciliador periodico futuro.

## Verificado

Ciclo completo real: crear issue via API → webhook con firma valida recibido → archivo escrito con
el nombre correcto → `index_corpus()` disparado → busqueda semantica real (`_embed` + 
`query_points`) devuelve el issue sincronizado como resultado #1 para una consulta relacionada.
Probado tambien que un repo con `docs/29110/` (`observability`) uses distinto -- no aplica aca,
este endpoint no clasifica, solo sincroniza.

## Pendiente

Comentarios de issues (`issue_comment`); reconciliador periodico para limpiar archivos huerfanos
de issues borrados (dado que no hay webhook de delete); Pages de Plane (sin soporte de webhook en
absoluto en esta version, necesitaria polling).
