# Especificación de Requisitos — Idea 4: CI/CD con PR-reviewer de IA

Según proceso **SI.2** del Perfil Básico ISO/IEC 29110.

## Requisitos funcionales

| ID | Requisito |
|---|---|
| RF1 | Cada PR contra `master` dispara automáticamente un workflow de CI. |
| RF2 | El workflow corre los unit tests del guardrail (`evals/gate_unit_tests.py`) y marca el job como fallido si alguno no pasa. |
| RF3 | El workflow genera un review de código con IA sobre el diff de la PR y lo publica como comentario en la PR. |
| RF4 | El review de IA nunca hace fallar el pipeline, sea cual sea su contenido o si el LLM no responde. |
| RF5 | El pipeline no ejecuta código de PRs que no vengan del mismo repositorio (sin soporte de forks en v1). |

## Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF1 | El review de IA usa exclusivamente cómputo local (Ollama, `qwen3:14b`) — cero llamadas a APIs externas de pago. |
| RNF2 | El runner self-hosted sobrevive un reboot de la workstation sin intervención manual (servicio systemd, no proceso ad-hoc). |
| RNF3 | El runner queda scoped únicamente a `devops-multiagent`, no a la cuenta u organización completa de GitHub. |
| RNF4 | El diff enviado al modelo se trunca a un tamaño acotado (15000 caracteres) para evitar prompts desproporcionados. |
| RNF5 | Ningún secreto de larga vida queda en el repo — el token usado para comentar en la PR es el `GITHUB_TOKEN` efímero que provee Actions por corrida, con permisos mínimos (`pull-requests: write`, `contents: read`), no un PAT personal. |

## Fuera de alcance
- Bloquear merges basándose en el contenido del review de IA (deliberadamente advisorio, no un quality gate).
- Soporte para PRs desde forks (requeriría un modelo de aprobación manual adicional, no implementado en v1).
- Ejecutar los evals de integración (`scenarios.py`) en CI.
