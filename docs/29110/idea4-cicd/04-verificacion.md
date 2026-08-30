# Verificación — Idea 4: CI/CD con PR-reviewer de IA

Según proceso **SI.5** del Perfil Básico ISO/IEC 29110. Casos mapeados a los criterios de aceptación del [plan de proyecto](01-plan-proyecto.md).

| # | Caso de prueba | Resultado |
|---|---|---|
| 1 | Runner registrado, scoped solo a este repo, sobrevive un restart del servicio | ✅ Registrado vía `config.sh --url .../gaelsg/devops-multiagent` (no a nivel org/cuenta). Instalado con `sudo ./svc.sh install` + `start` → servicio systemd `actions.runner.gaelsg-devops-multiagent.workstation-cachyos.service`, `enabled`, `Active: active (running)`. |
| 2 | PR real dispara el workflow; job `test` corre `gate_unit_tests.py` y pasa | ✅ PR #1 (`test/ci-pipeline`), run [33298110891](https://github.com/gaelsg/devops-multiagent/actions/runs/33298110891): job `test` completado en 6s, conclusión `success`. |
| 3 | Job `ai-review` genera un comentario real y relevante al diff | ✅ Job completado en 22s. Comentario publicado en la PR con 3 observaciones puntuales sobre el diff real (riesgo de fork-PR ya mitigado, falta de test para fallos de Ollama, claridad del README sobre disponibilidad del runner) — no un texto genérico. |
| 4 | Ningún job corre en PRs de forks | ⚠️ Verificado por diseño (`if: head.repo.full_name == github.repository`, documentado en `03-diseno.md`), **no probado con un fork real** — no hay uno disponible en este repo de un solo mantenedor. Pendiente re-verificar el día que exista una PR externa real. |

## Incidentes durante la implementación

**Bloque de comandos de registro del runner mal pegado en fish.** El primer bloque entregado usaba continuaciones de línea (`\`) estilo bash; al pegarse en una terminal fish con paste no siempre en modo bracketed, `curl` se comió la línea siguiente como argumento (`curl: (6) Could not resolve host: echo`). No dejó estado parcial (el directorio del runner quedó vacío). Corregido reescribiendo el bloque sin continuaciones, un comando por línea.

**Sintaxis de variables de bash usada por error en un shell fish.** `REG_TOKEN=$(...)` no es válido en fish (requiere `set REG_TOKEN (...)`). Mismo bloque, mismo fix.

**Identidad de git perdida.** Al momento de commitear, `git config --global user.name`/`user.email` estaban vacíos — se habían perdido en algún punto entre la Idea 3 y esta (causa no determinada, no es parte del alcance de este proyecto investigarla). El asistente no toca `git config` global por su cuenta ([[feedback-credential-handling]] aplica el mismo principio de no tocar configuración sensible sin que el usuario la ejecute él mismo); se le pidió al usuario que la reconfigurara, usando el mismo autor que ya tenían los commits previos del proyecto.

## Conclusión
3 de 4 criterios verificados de punta a punta contra infraestructura real (runner real, PR real, comentario real generado por el modelo real). El cuarto (aislamiento de forks) está implementado y su lógica es correcta por inspección, pero queda marcado como no verificado empíricamente hasta que exista una PR externa real — mismo criterio ya aplicado en la Idea 3 con la regla `VaultSealed` (no afirmar como "verificado" lo que no se probó contra el sistema real).
