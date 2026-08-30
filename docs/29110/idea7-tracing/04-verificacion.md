# Verificación — Idea 7: Tracing distribuido del sistema de agentes

Según proceso **SI.5** del Perfil Básico ISO/IEC 29110. Casos mapeados a los criterios de aceptación del [plan de proyecto](01-plan-proyecto.md).

| # | Caso de prueba | Resultado |
|---|---|---|
| 1 | Una consulta real que dispare los 3 servidores MCP produce un único trace_id en Jaeger | ✅ `uv run devops-agent diagnose "..."` (consulta real tocando Proxmox, Kubernetes y RAG en una sola conversación) → **24 spans, un solo trace_id**, confirmado via `/api/traces` de la API de Jaeger, no solo la UI. |
| 2 | Los tiempos reportados son reales y consistentes | ✅ `search_knowledge` reportó 838ms en el span padre; sus dos hijos (`ollama.embed` 32ms + `qdrant.query_points` 31ms) suman una fracción menor del total, consistente con el resto siendo overhead real de red/stdio entre procesos — no números inventados o redondeados sospechosamente. |
| 3 | Al menos un servidor MCP con spans internos más allá del automático | ✅ `rag-mcp-server`: `ollama.embed` y `qdrant.query_points` como hijos reales de `tools/call search_knowledge`, verificado en una segunda corrida real. |

## Casos adicionales verificados (no en los criterios formales, pero relevantes)

- **`operate()` genera su span correctamente incluso cuando la tool queda bloqueada** (sin aprobación): `uv run devops-agent operate "reinicia el contenedor 100"` sin `--approve` → trace con span `operate` real en Jaeger, atributo `operator.approved=False`.
- **El servicio `devops-webhook.service` (systemd, corriendo en producción) toma la instrumentación nueva tras un restart** sin errores — confirmado `systemctl --user is-active` → `active`.
- **`gate_unit_tests.py` sigue en verde (5/5)** tras todos los cambios — la instrumentación no rompió el guardrail determinista existente.

## Incidente durante la implementación

**La imagen de Jaeger planeada (v1) resultó estar EOL.** Ver `observability/docs/bitacora/2026-08-30-jaeger.md` para el detalle — descubierto en el propio log de arranque del contenedor (aviso explícito de fin de soporte, dic-2025), sumado a un error de permisos real no relacionado. Se migró a v2 antes de seguir, en vez de silenciar el aviso y quedarse con lo que "ya andaba".

## Conclusión
3 de 3 criterios de aceptación formales verificados contra infraestructura real (Jaeger real, servidores MCP reales, LLM real). El hallazgo más significativo de esta idea no fue un incidente sino una simplificación real: investigar el SDK antes de escribir instrumentación manual completa evitó construir una capa entera de propagación de contexto que el propio SDK de MCP ya resolvía.
