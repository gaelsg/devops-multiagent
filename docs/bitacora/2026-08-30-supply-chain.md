# 2026-08-30 — Escaneo de dependencias en el CI (Idea 8, post-roadmap)

Parte de la Idea 8 (ver `k8s-mcp-server/docs/29110/idea8-supply-chain/` para el detalle completo). Esta entrada es solo el lado de este repo.

## Cambio
Nuevo paso de Trivy (`scan-type: fs`, `scan-ref: uv.lock`) en el job `test` de `.github/workflows/ci.yml`, con `--ignore-unfixed` + `exit-code: 1` — mismo criterio que `k8s-mcp-server`: falla solo sobre CVEs con parche disponible, no sobre lo que nadie puede arreglar hoy. De paso, `actions/checkout` pasó de `@v4` (tag mutable) a fijado por SHA de commit.

## Verificado
PR de prueba real (#2): paso "Trivy -- dependencias" en verde en el runner self-hosted, sin falsos positivos (línea base del repo: 0 HIGH/CRITICAL en `uv.lock`).
