# Plan de Proyecto — Idea 7: Tracing distribuido del sistema de agentes

Según proceso **PM.1** del Perfil Básico ISO/IEC 29110. Primera idea después de cerrar el roadmap de 6 ([[project-roadmap2-bigtech]]) — parte de una fase de consolidación del portafolio, elegida entre 3 direcciones propuestas (profundizar tracing del sistema de agentes, seguridad de supply chain, o un roadmap nuevo).

## Objetivo
Reemplazar "el sistema de agentes hizo algo" por trazabilidad real: un solo trace_id que atraviesa el Diagnostician/Operator/Watcher/webhook, los 3 servidores MCP (procesos separados, conectados via stdio), y cada llamada al LLM (Ollama), visible como un árbol de spans en un backend de tracing real.

## Alcance

**Incluye:**
- Backend de tracing (Jaeger v2) en el LXC `observability`, recolectando via OTLP.
- Instrumentación de los 4 puntos de entrada del sistema de agentes (`diagnose`, `operate`, `watch`, `webhook.alertmanager`) como spans raíz.
- Propagación de contexto de trace desde `devops-multiagent` hacia los 3 servidores MCP (`proxmox-mcp-server`, `rag-mcp-server`, `k8s-mcp-server`).
- Spans para cada llamada a Ollama (chat y embeddings), con convenciones semánticas `gen_ai.*`.
- Spans internos adicionales donde agregan información real (ej. separar embedding de consulta a Qdrant dentro de `search_knowledge`).

**No incluye (fuera de alcance v1):**
- Storage persistente de traces — Jaeger en memoria, ver riesgos.
- Dashboards derivados de traces en Grafana (métricas agregadas tipo p95/p99 por operación).
- Instrumentación con el mismo nivel de detalle en `operator.py` (tools de escritura) — comparte el patrón general pero no se verificó con una escritura real aprobada.

## Entregables
1. `jaeger` nuevo en `observability/docker-compose.yml`.
2. `tracing.py` en los 4 repos (`devops-multiagent`, `proxmox-mcp-server`, `rag-mcp-server`, `k8s-mcp-server`).
3. Instrumentación de los 4 puntos de entrada + `ToolRegistry.call()` + `agent.py` en `devops-multiagent`.
4. Spans internos adicionales en `rag-mcp-server`.
5. Esta serie de documentos 29110 + bitácoras en los 5 repos tocados.

## Riesgos identificados
| Riesgo | Mitigación |
|---|---|
| La imagen de Jaeger planeada (v1) está EOL desde dic-2025 | Migrado a v2 antes de seguir, no se ignoró el aviso. |
| Storage en memoria pierde los traces en cada restart del contenedor | Aceptado — los traces son datos de diagnóstico más efímeros que métricas o secretos; documentado como límite, no un descuido. |
| Instrumentación manual mal hecha podría generar spans huérfanos o trace_ids que no correlacionan | Verificado contra Jaeger real (no solo "el código compila") antes de dar por cerrada cada pieza. |
| Overhead de tracing en cada llamada | `BatchSpanProcessor` (envío asíncrono en lote, no bloqueante por request) + tracing completamente opcional (no hace nada si `OTEL_EXPORTER_OTLP_ENDPOINT` no está seteado). |

## Criterios de aceptación
- Una consulta real que dispare los 3 servidores MCP produce un único trace_id en Jaeger, con los spans correctamente anidados (no 4 traces sueltos sin relación).
- Los tiempos reportados por los spans son reales y consistentes con el comportamiento observado (ej. el tool call que tarda ~800ms en los logs muestra ~800ms en el span).
- Al menos un servidor MCP tiene spans internos más allá del span automático de la tool call, mostrando desglose real de dónde se va el tiempo.
