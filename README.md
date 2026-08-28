# devops-multiagent

Sistema multi-agente sobre infraestructura propia (Proxmox VE), corriendo 100% local y gratis: modelo de tool-calling vía Ollama, dos agentes especializados con separación de privilegios, y una suite de evals que verifica el comportamiento con aserciones deterministas sobre el trace de tool-calls — no "se ve bien en la demo", sino "hicimos exactamente las llamadas correctas, con los guardrails correctos".

Fase 4 del roadmap de agentes, construido sobre [proxmox-mcp-server](https://github.com/gaelsg/proxmox-mcp-server) y [rag-mcp-server](https://github.com/gaelsg/rag-mcp-server).

## Arquitectura

- **Modelo:** `qwen3:14b` vía Ollama, local, en la RTX 5080. Elegido sobre DeepSeek-R1-distill por soporte de tool-calling estructurado más maduro en Ollama.
- **Cliente MCP real:** este proyecto no es un servidor MCP — es un *host/cliente* que habla el protocolo MCP contra `proxmox-mcp-server` y `rag-mcp-server` como subprocesos, usando el SDK oficial (`mcp.client.Client`).
- **Diagnostician:** solo lectura. Las tools de escritura ni siquiera se le anuncian al modelo (filtradas en `ToolRegistry.connect`, no solo bloqueadas).
- **Operator:** puede ejecutar `start_resource`/`stop_resource`/`restart_resource`, pero solo si `approved=True` se pasó explícitamente al invocarlo. Sin aprobación, el modelo puede intentar la llamada (se le anuncia la tool) pero el `ToolRegistry` la bloquea antes de tocar Proxmox — el guardrail vive en código, no en el criterio del modelo.
- **Watcher:** chequeo determinista de estado (sin LLM) cada 15 min via systemd timer. Solo si detecta un cambio real (no en cada poll) manda una alerta cruda a Telegram y despues invoca al Diagnostician para dar contexto.

## Setup

Requiere `proxmox-mcp-server` y `rag-mcp-server` ya configurados (ver sus propios README), y Ollama con `qwen3:14b`:

```bash
ollama pull qwen3:14b
uv sync
cp .env.example .env  # completar TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID si usas el watcher
```

## Uso

```bash
uv run devops-agent diagnose "cual es el estado del contenedor de nextcloud?"
uv run devops-agent operate "reinicia el contenedor 100"              # queda bloqueado, sin --approve
uv run devops-agent operate "reinicia el contenedor 100" --approve    # se ejecuta de verdad
uv run devops-agent watch                                             # chequeo unico, notifica si hay cambios
```

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
