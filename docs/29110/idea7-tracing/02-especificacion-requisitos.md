# Especificación de Requisitos — Idea 7: Tracing distribuido del sistema de agentes

Según proceso **SI.2** del Perfil Básico ISO/IEC 29110.

## Requisitos funcionales

| ID | Requisito |
|---|---|
| RF1 | Cada invocación de `diagnose`, `operate`, `watch` o el webhook de Alertmanager genera un span raíz único (nueva raíz de trace, nadie les propaga contexto desde afuera). |
| RF2 | Cada llamada a una tool via `ToolRegistry.call()` propaga el contexto de trace activo al servidor MCP correspondiente. |
| RF3 | Cada servidor MCP (`proxmox-mcp-server`, `rag-mcp-server`, `k8s-mcp-server`) reporta un span por `tools/call`, anidado bajo el trace del llamador. |
| RF4 | Cada llamada a Ollama (chat o embeddings) genera su propio span, con atributos `gen_ai.system`, `gen_ai.request.model`. |
| RF5 | Los spans y traces son visibles e inspeccionables en Jaeger (UI y API), no solo en logs locales. |

## Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF1 | El tracing es opcional: si `OTEL_EXPORTER_OTLP_ENDPOINT` no está configurado, el sistema funciona exactamente igual que sin esta idea. |
| RNF2 | El envío de spans no bloquea el flujo principal de una request (procesamiento asíncrono en lote). |
| RNF3 | Un mismo vocabulario de atributos semánticos (`gen_ai.*`) en todo el trace, no convenciones distintas inventadas por repo. |
| RNF4 | Cero cambios al comportamiento observable del sistema (mismas respuestas, mismos guardrails) — el tracing es puramente aditivo. |

## Fuera de alcance
- Sampling configurable (hoy se traza el 100% de las requests — volumen bajo en un homelab, no justifica la complejidad de un sampler).
- Alertas basadas en traces (ej. "avisar si `ollama.chat` tarda más de N segundos") — posible extensión futura sobre Grafana Tempo/Grafana Alerting, no construida aquí.
- Instrumentación de Qdrant/Proxmox API/Kubernetes API como servicios propios con sus spans de servidor (solo se instrumenta el lado cliente, dentro de cada MCP server).
