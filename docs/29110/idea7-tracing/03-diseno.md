# Diseño — Idea 7: Tracing distribuido del sistema de agentes

Según proceso **SI.3** del Perfil Básico ISO/IEC 29110.

## Componentes

```
devops-multiagent (entry points: diagnose / operate / watch / webhook)
   │
   ├── span raiz (gen_ai.operation.name = diagnose|operate|watch|webhook)
   │
   ├── ollama.chat (span manual, agent.py)  ──► Ollama (qwen3:14b)
   │
   └── ToolRegistry.call()
          │
          ├── span "tool_call <name>" (manual)
          ├── propagate.inject(meta)  ──► meta["traceparent"]
          │
          └── client.call_tool(name, arguments, meta=meta)  [stdio]
                 │
                 ▼
          MCP server (proxmox-mcp-server / rag-mcp-server / k8s-mcp-server)
                 │
                 ├── OpenTelemetryMiddleware (SDK, automatico)
                 │      extrae traceparent de _meta ──► span "tools/call <name>"
                 │
                 └── (rag-mcp-server) spans manuales adicionales:
                        ├── ollama.embed  ──► Ollama (bge-m3)
                        └── qdrant.query_points  ──► Qdrant
                 │
                 ▼
          OTLP exporter ──► Jaeger (observability, 192.168.8.90:4317)
```

## Decisiones de diseño

**Se investigó el SDK real antes de escribir instrumentación manual completa.** El plan inicial asumía tener que envolver cada tool function individualmente (agregar un parámetro de contexto, extraer/inyectar manualmente). Antes de hacerlo, se inspeccionó el código fuente instalado de `mcp[cli]` y se encontró que el middleware de OpenTelemetry ya viene integrado (`mcp.server._otel.OpenTelemetryMiddleware`), envolviendo cada `tools/call` automáticamente. Resultado: cero cambios a las funciones de las tools en los 3 servidores — solo configurar el `TracerProvider` al arrancar.

**Propagación via el campo `_meta` del protocolo MCP, no un argumento de tool.** El SDK expone `Client.call_tool(..., meta=RequestParamsMeta)`, un mapa abierto (`TypedDict` con `extra_items=Any`) pensado exactamente para metadata de este tipo. Usar esto en vez de agregar un argumento oculto a cada tool evita ensuciar el schema que ve el LLM (un parámetro extra ahí confundiría al modelo o requeriría lógica para ocultarlo).

**`opentelemetry.propagate.inject()` directo, no el helper privado del SDK.** `mcp.shared._otel.inject_trace_context()` existe y hace exactamente esto, pero es una API privada (prefijo `_otel`, sin garantía de estabilidad entre versiones) — es un wrapper de una línea sobre la función pública de OpenTelemetry, así que se llama a esa función pública directamente.

**`tracing.py` duplicado por repo, no una librería compartida.** Mismo criterio que `secrets_loader.py`: cada repo es independiente, sin un paquete interno compartido en este ecosistema. El archivo es idéntico salvo el nombre de servicio pasado como argumento — duplicar 20 líneas es más simple de auditar que introducir un paquete privado nuevo solo para esto.

**Spans raíz en los 4 entry points, no un único span global "sistema."** `diagnose`, `operate`, `watch.check_once` y `webhook.alertmanager` son, cada uno, el punto donde una interacción externa (usuario, timer, Alertmanager) entra al sistema — ninguno tiene un llamador que le propague contexto. Tratarlos como raíces separadas refleja la realidad: son 4 flujos de trabajo distintos, no ejecuciones del mismo proceso continuo.

**`ollama.chat`/`ollama.embed` con convenciones `gen_ai.*`, las mismas que ya usa el middleware del SDK para las tool calls.** Evita que el trace tenga dos vocabularios de atributos distintos (uno "inventado" para las llamadas al LLM, otro heredado del SDK para las tools) — un lector del trace en Jaeger ve un único esquema de atributos consistente en todo el árbol.

**Tracing 100% opcional, no un requisito duro.** `configure_tracing()` no hace nada si `OTEL_EXPORTER_OTLP_ENDPOINT` no está seteado — el sistema tiene que poder correr exactamente igual sin el LXC de observability levantado (mismo criterio que Vault: opcional en desarrollo, fail-fast solo si está configurado pero no responde — acá ni siquiera eso, tracing ausente nunca es un error).

**Jaeger con storage en memoria, no persistente.** Ver `01-plan-proyecto.md` — v2 requiere un config.yaml de pipeline (extension `jaeger_storage`) para persistencia, un salto de complejidad no justificado para datos de diagnóstico más efímeros que métricas o secretos.
