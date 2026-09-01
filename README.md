# devops-multiagent

Sistema multi-agente sobre infraestructura propia (Proxmox VE), corriendo 100% local y gratis: modelo de tool-calling vía Ollama, dos agentes especializados con separación de privilegios, y una suite de evals que verifica el comportamiento con aserciones deterministas sobre el trace de tool-calls — no "se ve bien en la demo", sino "hicimos exactamente las llamadas correctas, con los guardrails correctos".

Fase 4 del roadmap de agentes, construido sobre [proxmox-mcp-server](https://github.com/gaelsg/proxmox-mcp-server), [rag-mcp-server](https://github.com/gaelsg/rag-mcp-server) y [k8s-mcp-server](https://github.com/gaelsg/k8s-mcp-server).

## Arquitectura

- **Modelo:** `qwen3:14b` vía Ollama, local, en la RTX 5080. Elegido sobre DeepSeek-R1-distill por soporte de tool-calling estructurado más maduro en Ollama.
- **Cliente MCP real:** este proyecto no es un servidor MCP — es un *host/cliente* que habla el protocolo MCP contra `proxmox-mcp-server`, `rag-mcp-server` y `k8s-mcp-server` como subprocesos, usando el SDK oficial (`mcp.client.Client`).
- **Diagnostician:** solo lectura. Las tools de escritura ni siquiera se le anuncian al modelo (filtradas en `ToolRegistry.connect`, no solo bloqueadas). Desde la Idea 6 del segundo roadmap, también lee el cluster de Kubernetes (`k3s`) via `k8s-mcp-server` — tools con prefijo `k8s_` para no chocar con las de Proxmox.
- **Operator:** puede ejecutar `start_resource`/`stop_resource`/`restart_resource`, pero solo si `approved=True` se pasó explícitamente al invocarlo. Sin aprobación, el modelo puede intentar la llamada (se le anuncia la tool) pero el `ToolRegistry` la bloquea antes de tocar Proxmox — el guardrail vive en código, no en el criterio del modelo.
- **Watcher:** chequeo determinista de estado (sin LLM) cada 15 min via systemd timer. Solo si detecta un cambio real (no en cada poll) manda una alerta cruda a Telegram y despues invoca al Diagnostician para dar contexto.
- **Dashboard:** FastAPI + htmx, solo localhost. Diagnostician con trace de tool-calls en vivo (SSE) + historial de auditoría. Ver sección propia más abajo.
- **Webhook de Alertmanager:** servicio separado (`devops-agent webhook`, LAN, puerto 8090) que conecta [`observability`](https://github.com/gaelsg/observability) (Prometheus/Alertmanager) con el Diagnostician — una alerta real dispara una explicación en lenguaje natural por Telegram. Bind `0.0.0.0` a propósito, a diferencia del dashboard — ver su propia sección.
- **CI/CD:** GitHub Actions con runner self-hosted en la workstation. Cada PR corre los unit tests del guardrail y un review automático de IA (mismo `qwen3:14b` local). Ver sección propia más abajo.
- **Tracing distribuido:** cada consulta genera un solo trace (OpenTelemetry) que cruza los 3 servidores MCP y cada llamada a Ollama, visible en Jaeger. Ver sección propia más abajo.

## Setup

Requiere `proxmox-mcp-server` y `rag-mcp-server` ya configurados (ver sus propios README), y Ollama con `qwen3:14b`:

```bash
ollama pull qwen3:14b
uv sync
cp .env.example .env  # completar VAULT_ROLE_ID/VAULT_SECRET_ID (ver vault-secrets/scripts/onboard-devops-multiagent.sh)
```

Los secretos reales (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WEBHOOK_SHARED_SECRET`) viven en Vault (`secret/devops-multiagent`) desde la consolidación del portafolio, no en `.env` — mismo patrón que el resto del roadmap. `cli.py` carga Vault **antes** de importar `watcher`/`operator`/`diagnostician` (que a su vez importan `notify.py`, que lee esas variables al importarse, no de forma perezosa) — si se llama a `load_secrets_from_vault()` después de esos imports, quedan vacías para siempre en ese proceso.

## Uso

```bash
uv run devops-agent diagnose "cual es el estado del contenedor de nextcloud?"
uv run devops-agent operate "reinicia el contenedor 100"              # queda bloqueado, sin --approve
uv run devops-agent operate "reinicia el contenedor 100" --approve    # se ejecuta de verdad
uv run devops-agent watch                                             # chequeo unico, notifica si hay cambios
uv run devops-agent serve                                             # dashboard web, http://127.0.0.1:8000
uv run devops-agent webhook                                           # receptor de Alertmanager, http://0.0.0.0:8090
```

## Dashboard web

FastAPI + htmx, sin build step ni frontend framework. Dos cosas:

- **Diagnostician con trace en vivo:** el formulario dispara una conexión SSE (`htmx-ext-sse`) que va mostrando cada tool-call en cuanto se ejecuta, no solo la respuesta final — la misma info que hoy solo se ve al terminar en el CLI.
- **Historial de auditoría:** lee directo `proxmox-mcp-server/docs/audit/actions.jsonl` (las acciones de escritura reales quedan ahí, ver ese repo) y se refresca cada 30s.

Solo expone Diagnostician (solo lectura) — no hay panel de Operator todavía, decisión deliberada para no sumar un botón de "reiniciar" en una UI sin autenticación. Ver [decisión completa](docs/bitacora/2026-08-29-idea4.md).

**Bind solo a `127.0.0.1`, a propósito.** No tiene login: el modelo de confianza es el mismo que correr el CLI a mano en la propia máquina. No exponer en LAN/Tailscale sin agregar auth antes.

## Webhook de Alertmanager (systemd --user, LAN)

`src/devops_multiagent/webhook.py` — un único endpoint (`POST /webhook/alertmanager`), protegido por un shared secret (`WEBHOOK_SHARED_SECRET`, vive en Vault vía [`vault-secrets`](https://github.com/gaelsg/vault-secrets)) pasado como query param, más un chequeo de forma del payload (no cualquier POST dispara el Diagnostician). Bind `0.0.0.0` a propósito, a diferencia del dashboard — Alertmanager corre en otro LXC y necesita alcanzarlo por LAN. Requiere abrir el puerto en el firewall del host (`sudo ufw allow from 192.168.8.0/24 to any port 8090 proto tcp`).

```bash
mkdir -p ~/.config/systemd/user
ln -sf ~/projects/devops-multiagent/systemd/devops-webhook.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now devops-webhook.service
```

## Webhook de Plane → RAG (mismo servicio, puerto 8090)

`POST /webhook/plane` — cuando se crea/actualiza un *issue* en [Plane](http://192.168.8.93)
(gestión de proyectos del track de automatización, ver `proxmox-iac`), este endpoint valida la
firma `X-Plane-Signature` (HMAC-SHA256, secreto `PLANE_WEBHOOK_SECRET` vía Vault), sincroniza el
contenido a un `.md` en `rag-mcp-server/docs/plane-sync/` y dispara `index_corpus()` en
`rag-mcp-server` vía el mismo `ToolRegistry` que usa el Diagnostician — Plane pasa a ser una
fuente más del corpus, sin pipeline de indexado nuevo. Solo el evento `issue` por ahora (no
comentarios). Requiere que la URL destino esté en `WEBHOOK_ALLOWED_IPS` de Plane (protección SSRF
real contra IPs privadas por defecto). Tres incidentes reales (SSRF, naming del archivo ignorado
por el indexador, delete de issues que Plane nunca llega a enviar) documentados en
`docs/bitacora/2026-09-01-plane-webhook.md`.

## CI/CD (GitHub Actions, runner self-hosted)

`.github/workflows/ci.yml` corre en cada PR contra este repo, en un runner self-hosted registrado en la workstation (systemd, `sudo ./svc.sh install/start` — sobrevive reboot). Dos jobs:

- **`test`:** `evals/gate_unit_tests.py` — solo la lógica del guardrail, sin red ni LLM, instantáneo.
- **`ai-review`:** `.github/scripts/pr_review.py` — le pasa el diff de la PR al mismo `qwen3:14b` local (vía Ollama, `localhost:11434`) con un prompt de revisor senior, y postea el resultado como comentario en la PR (`gh pr comment`). **Es advisorio, nunca bloquea el merge** — mismo principio que el Operator: la IA sugiere, un humano decide.

**Por qué self-hosted y no runners de GitHub:** sigue la filosofía "100% local y gratis" del proyecto — el review usa el mismo modelo que ya corre en la RTX 5080, sin pagar una API externa. El costo es que el runner tiene que estar prendido para que el CI corra.

**Riesgo de seguridad documentado:** un runner self-hosted en un repo público ejecuta código arbitrario de cualquier PR que dispare el workflow — si algún día este repo acepta PRs externas, un fork podría lograr RCE en la workstation. Mitigación aplicada: ambos jobs tienen `if: github.event.pull_request.head.repo.full_name == github.repository` (solo corren en PRs del mismo repo, nunca de forks). El toggle granular "Require approval for all outside collaborators" (Settings → Actions) **no existe para repos de cuenta personal** — solo está disponible en repos de una organización de GitHub (confirmado vía API: `gh api repos/gaelsg/devops-multiagent/actions/permissions` no expone ese campo). En su lugar, GitHub ya exige aprobación manual para el primer workflow run de cualquier colaborador externo en un repo público de cuenta personal, sin posibilidad de ajustarlo — es la protección real vigente hoy, sumada al `if` del workflow.

## Tracing distribuido (OpenTelemetry + Jaeger)

Cada `diagnose`/`operate`/`watch`/webhook abre un span raíz; `ToolRegistry.call()` propaga ese contexto a cada servidor MCP via el campo `_meta` del protocolo (`meta={"traceparent": ...}`). **No hizo falta instrumentar cada tool a mano** — el SDK de MCP ya trae un middleware de OpenTelemetry embebido que envuelve cada `tools/call` en un span y extrae el `traceparent` automáticamente. Las llamadas a Ollama (`ollama.chat` en este repo, `ollama.embed` en `rag-mcp-server`) usan las mismas convenciones semánticas `gen_ai.*` que el middleware del SDK — un solo vocabulario de atributos en todo el trace.

```bash
# En .env: OTEL_EXPORTER_OTLP_ENDPOINT=http://192.168.8.90:4317 (opcional -- sin esto, tracing no hace nada)
uv run devops-agent diagnose "..."
```

UI de Jaeger: `curl -H "Host: jaeger.homelab.local" http://192.168.8.92/` (o configurar esa entrada DNS/hosts localmente). Desde la Idea 9, Jaeger corre en el cluster k3s (no ya en el LXC `observability`), gestionado por GitOps — ver [`observability`](https://github.com/gaelsg/observability#jaeger-sobre-k3s-gestionado-por-gitops-idea-9-post-roadmap). Storage en memoria (los traces no sobreviven un restart del pod, aceptado como límite: son datos de diagnóstico más efímeros que métricas o secretos).

## Watcher proactivo (systemd --user timer)

```bash
loginctl enable-linger $USER   # para que corra sin sesion activa
mkdir -p ~/.config/systemd/user
ln -sf ~/projects/devops-multiagent/systemd/devops-watcher.service ~/.config/systemd/user/
ln -sf ~/projects/devops-multiagent/systemd/devops-watcher.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now devops-watcher.timer

systemctl --user list-timers devops-watcher.timer     # ver proxima corrida
journalctl --user -u devops-watcher.service -f         # seguir logs en vivo
```

## Evals

```bash
uv run python evals/run_evals.py
```

Dos capas:
- `evals/gate_unit_tests.py` — lógica del guardrail en aislamiento, sin red ni LLM, instantáneo.
- `evals/scenarios.py` — escenarios reales contra Ollama + los MCP servers reales, verificando que el modelo elige las tools correctas y que el guardrail de escritura se activa en una conversación real. **Nunca ejecuta una escritura real** (Operator siempre se prueba con `approved=False`) — evita reiniciar infraestructura real en cada corrida de evals; la ejecución real ya se validó a mano en la bitácora de `proxmox-mcp-server`.

## Nota conocida

`qwen3:14b` (modelo híbrido de razonamiento) frecuentemente deja el campo `content` vacío y pone la respuesta final en `thinking` cuando no hay más tool-calls que hacer. `agent.py` hace fallback a `thinking` si `content` viene vacío — sin este fix, ~50-75% de las respuestas finales llegaban vacías pese a que el modelo sí había razonado la respuesta correcta.

## Supply chain

Ver [k8s-mcp-server](https://github.com/gaelsg/k8s-mcp-server#tracing) para el pipeline completo de build+scan+SBOM+firma (Idea 8).
