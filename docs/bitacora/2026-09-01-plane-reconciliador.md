# 2026-09-01 — Reconciliador diario: limpia del RAG lo que ya se borró en Plane

Último pendiente explícito de la integración Plane→RAG. Como Plane nunca avisa vía webhook
cuando se borra un issue o un comentario (confirmado dos veces: para issues y, por separado, para
comentarios — ver bitácoras anteriores), el corpus local podía acumular contenido fantasma
indefinidamente. Este reconciliador cierra ese hueco con el mismo patrón que el resto del
portafolio: un timer de systemd, no un proceso corriendo todo el tiempo.

## Diseño

`devops-agent plane-reconcile` (nuevo subcomando): recorre **todos los proyectos del workspace**,
no solo "Documentación" — el webhook es a nivel workspace, cualquier proyecto puede haber
sincronizado algo. Para cada proyecto lista issues y, para cada issue, sus comentarios (paginado
real vía `cursor`, no asumido de una sola página). Compara el conjunto de ids que **sí existen**
en Plane contra las claves del `_index.json` local; lo que sobra se borra del corpus y del índice.
Si borró algo, dispara `index_corpus()`; si no, no reindexa innecesariamente.

Usa credenciales propias (`PLANE_VAULT_ROLE_ID`/`PLANE_VAULT_SECRET_ID`, mismo AppRole `plane` de
solo lectura que ya usa `pm-agent`, secret_id nuevo generado para este consumidor) cargadas solo
para este subcomando (`load_plane_secrets_from_vault()`) — el resto del CLI
(`diagnose`/`operate`/`watch`/`webhook`) no necesita hablarle a la API de Plane, así que no carga
ese AppRole.

Timer diario (`plane-reconcile.timer`, `OnCalendar=daily`), mismo patrón que
`vault-secrets/systemd/vault-backup.timer`.

## Verificado

Ciclo real completo: creado un issue de prueba en Plane → sincronizado solo (webhook) →
borrado en Plane (sin webhook, confirmado que el archivo local seguía ahí) → corrido
`plane-reconcile` → detectó el huérfano y lo borró, reindexó el RAG. Segunda corrida inmediata:
"nada para borrar", no reindexa de más. Los 2 issues reales (agente de voz, pm-agent) no se
tocaron — solo se removió exactamente el que ya no existía en Plane.
