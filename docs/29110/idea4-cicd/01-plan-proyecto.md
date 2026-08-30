# Plan de Proyecto — Idea 4: CI/CD con PR-reviewer de IA

Según proceso **PM.1** del Perfil Básico ISO/IEC 29110.

## Objetivo
Agregar un pipeline de CI/CD real a `devops-multiagent`: gate de tests automático en cada PR, más un review de código generado por IA que comenta sugerencias sin bloquear el merge — reusando la misma infraestructura local (`qwen3:14b` vía Ollama) que ya usan el Diagnostician y el Operator, en vez de depender de una API externa paga.

## Alcance

**Incluye:**
- Repo elegido: `devops-multiagent` (más movimiento reciente del roadmap, ya tiene evals reutilizables como gate).
- Runner self-hosted de GitHub Actions en la workstation, scoped solo a este repo, corriendo como servicio systemd (sobrevive reboot).
- Workflow `pull_request` con dos jobs: `test` (unit tests del guardrail, deterministas, sin red ni LLM) y `ai-review` (diff de la PR → `qwen3:14b` local → comentario en la PR vía `gh pr comment`).
- Guardrail de seguridad: ambos jobs restringidos a PRs del mismo repo (`head.repo.full_name == github.repository`), para no exponer el runner self-hosted a RCE desde un fork.
- El review de IA es advisorio: nunca marca la PR como fallida, incluso si Ollama no responde.

**No incluye (fuera de alcance v1):**
- Correr `evals/scenarios.py` (integración real contra Ollama + MCP servers) en CI — requeriría que el runner tenga acceso a los AppRoles de Vault de `proxmox-mcp-server`/`rag-mcp-server`, no resuelto todavía.
- Replicar el pipeline en los otros repos del ecosistema — se documenta como patrón reusable, no se aplica todavía a los demás.
- "Require approval for all outside collaborators" en Settings → Actions — recomendado antes de aceptar colaboradores externos, pero no aplicable hoy (repo de un solo mantenedor).

## Entregables
1. `.github/workflows/ci.yml` + `.github/scripts/pr_review.py` en `devops-multiagent`.
2. Runner self-hosted registrado y corriendo como servicio systemd en la workstation.
3. README actualizado con la sección de CI/CD (arquitectura, riesgo de seguridad documentado, mitigación aplicada).
4. Esta serie de documentos 29110 + bitácora.

## Riesgos identificados
| Riesgo | Mitigación |
|---|---|
| Runner self-hosted en repo público = RCE si corre workflows de un fork | `if: head.repo.full_name == github.repository` en ambos jobs del workflow. |
| Un LLM local caído o lento bloquea el pipeline | `pr_review.py` atrapa cualquier excepción y termina en éxito sin comentar; nunca falla el job. |
| Diff de PR muy grande excede el contexto útil del prompt | Truncado a 15000 caracteres, con nota explícita en el comentario si se truncó. |
| Runner apagado = CI no corre nunca | Aceptado como trade-off del enfoque "100% local"; documentado en README, no resuelto con fallback a runner de GitHub. |

## Criterios de aceptación
- El runner queda registrado, scoped solo a este repo, y sobrevive un restart del servicio (systemd, no un proceso manual).
- Una PR real dispara el workflow: el job `test` corre `gate_unit_tests.py` y pasa.
- El job `ai-review` genera un comentario real en la PR con contenido relevante al diff (no un mensaje genérico/vacío).
- Ninguno de los dos jobs corre si la PR viene de un fork (verificado por diseño del `if`, no probado con un fork real por no tener uno disponible).
