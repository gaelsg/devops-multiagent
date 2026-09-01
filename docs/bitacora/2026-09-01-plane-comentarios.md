# 2026-09-01 — Comentarios de issues también se sincronizan al RAG

Pedido explícito del usuario: extender `/webhook/plane` (mismo endpoint que ya sincroniza
issues) para que también sincronice comentarios (`issue_comment`). Mismo webhook de Plane, no uno
nuevo — el modelo `Webhook` tiene un flag booleano por recurso (`issue`, `issue_comment`, `module`,
`cycle`, `project`); solo hace falta activar "Comment"/"issue_comment" en el webhook ya creado
desde la UI, no crear otro.

## Diseño

`plane_sync.sync_comment()`: a diferencia de un issue, un comentario no tiene un `sequence_id`
corto y estable -- se le asigna un contador propio (`_counter` dentro del mismo `_index.json`
que ya usan los issues, sin colisión porque los UUID de Plane nunca matchean esa clave) la primera
vez que se ve su `id`, y se reusa el mismo nombre de archivo en updates siguientes. Cada comentario
queda como `<n>-<workspace_slug>-comentario.md`, con una primera línea que da contexto legible
("## Comentario en: <título del issue>") leyendo la primera línea del archivo del issue padre si
ya está sincronizado (mismo índice).

`webhook.py`: ahora acepta `event in ("issue", "issue_comment")`, ruteando a `sync_issue()` o
`sync_comment()` según corresponda; el resto del flujo (firma, reindex) es idéntico.

## Verificado

Test unitario offline de `sync_comment` (crear → mismo archivo en un update → `unlink` real en un
delete) antes de tocar el servicio en vivo. Índice local reconstruido desde el estado real de
Plane (se había perdido en una limpieza de archivos de prueba) consultando la API en vez de
asumirlo.

## Incidente real: `comment_stripped` no viene en el payload

Primer test end-to-end (comentario real vía API): el archivo se sincronizó con el contexto
correcto ("Comentario en: <issue>") pero el contenido quedó vacío. Depurado con un dump temporal
del payload crudo: a diferencia de un issue (que sí trae `description_stripped` calculado), el
payload de `issue_comment` **no incluye `comment_stripped` en absoluto** -- solo `comment_html`.
El modelo `IssueComment.save()` sí calcula `comment_stripped` server-side (`strip_tags`), pero el
serializer del webhook no lo expone. Corregido derivándolo del lado de `pm-agent`/
`devops-multiagent` con un `re.sub("<[^>]+>", "", html)` propio -- no se sumó una dependencia de
parsing HTML para algo tan simple. Reprobado: contenido correcto, verificado además con búsqueda
semántica real (top resultado para una consulta sobre el contenido del comentario).

## Confirmado: tampoco hay webhook de delete para comentarios

Se crearon y luego se borraron dos comentarios de prueba reales vía API -- ninguno de los dos
delete disparó el webhook (mismo patrón ya confirmado para issues, ahora verificado también para
`issue_comment`, no solo asumido por analogía). Los archivos huérfanos quedaron hasta la limpieza
manual de esta sesión.
