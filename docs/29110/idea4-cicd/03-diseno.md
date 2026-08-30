# Diseño — Idea 4: CI/CD con PR-reviewer de IA

Según proceso **SI.3** del Perfil Básico ISO/IEC 29110.

## Componentes

```
PR contra devops-multiagent
        │
        ▼
GitHub Actions (evento pull_request)
        │
        ▼
Runner self-hosted (workstation, systemd)
        │
        ├── job "test" ──────► evals/gate_unit_tests.py (sin red ni LLM)
        │
        └── job "ai-review" ─► gh pr diff → .github/scripts/pr_review.py
                                      │
                                      ▼
                              Ollama local (qwen3:14b, localhost:11434)
                                      │
                                      ▼
                              gh pr comment (GITHUB_TOKEN efímero)
```

## Decisiones de diseño

**Runner self-hosted en vez de GitHub-hosted.** Permite que `ai-review` llame a `localhost:11434` directo, sin exponer Ollama a internet ni pagar una API externa — coherente con el resto del proyecto ("100% local y gratis"). Costo aceptado: el runner tiene que estar prendido para que el CI corra; no hay fallback a un runner de GitHub.

**Dos jobs separados, no uno solo.** `test` es el gate real (determinista, puede fallar la PR). `ai-review` es advisorio y depende de un componente no determinista (el LLM) — separarlos evita que un review de IA lento o inconsistente contamine la señal de "¿pasan los tests?". `ai-review` tiene `needs: test`, así que ni siquiera corre si el gate ya falló (ahorra cómputo del LLM en una PR que de todas formas no se va a mergear tal cual).

**`pr_review.py` como script standalone, no parte del paquete `devops_multiagent`.** No necesita orquestación de tools ni el `ToolRegistry` — es un solo prompt de una sola pasada sobre un diff de texto. Meterlo en el paquete instalable hubiera sido una abstracción sin uso real fuera de CI.

**Guardrail de origen (`head.repo.full_name == github.repository`) en el `if` de cada job, no en un job previo de verificación.** Un job separado que otros `needs:` hubiera sido más "limpio" en apariencia, pero un self-hosted runner ya empieza a ejecutar `actions/checkout` (que trae el código del PR) en cuanto el job arranca — el `if` a nivel de job es lo que evita que ese checkout ocurra en absoluto para un PR de un fork, no algo que se pueda delegar a un paso posterior.

**Manejo de errores en `pr_review.py`: capturar todo, devolver 0.** Un LLM local puede no estar corriendo, tardar, o devolver algo raro. Ninguno de esos casos debe hacer fallar el pipeline — el review es una sugerencia, no un requisito. Se loggea el error para diagnóstico, pero el job termina en éxito sin comentar.

**Comentario con disclaimer explícito al inicio.** El texto generado por el modelo nunca se postea "a secas" — siempre lleva el prefijo "🤖 Review automático... sugerencia, no bloquea el merge", para que quede claro en la propia PR que no es una revisión humana ni un gate.

**Sin soporte de forks en v1.** Aceptar PRs externas en un repo con runner self-hosted en teoría se beneficiaría de "Require approval for all outside collaborators" (Settings → Actions) como defensa adicional — investigado post-hoc: ese toggle no existe para repos de cuenta personal (solo organizaciones). La mitigación real vigente es solo el `if: head.repo.full_name == github.repository` del workflow, más la aprobación manual obligatoria que GitHub ya impone por defecto a cualquier colaborador externo en un repo público personal.
