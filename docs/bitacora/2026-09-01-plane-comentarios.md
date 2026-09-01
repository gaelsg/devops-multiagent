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

## Pendiente de verificar

No se confirmó si Plane envía webhook de *delete* para comentarios (solo se confirmó, en la
integración anterior, que NO lo hace para issues) -- el manejo de delete queda implementado
igual, por si acaso.
