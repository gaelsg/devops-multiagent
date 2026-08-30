# 2026-08-30 — Corrección: "Require approval for outside collaborators" no aplica a este repo

Pendiente desde la Idea 4 (`docs/bitacora/2026-08-30-idea4-cicd.md`): activar ese toggle en Settings → Actions antes de aceptar colaboradores externos. Al ir a resolverlo (consolidación del portafolio), se encontró que la premisa del pendiente era incorrecta.

## Lo que se investigó
`gh api repos/gaelsg/devops-multiagent/actions/permissions` no expone ningún campo de aprobación por colaborador. Confirmado además que el owner del repo es `User` (cuenta personal), no una organización — ese toggle granular (elegir entre "todos los colaboradores externos" / "solo primera vez" / "sin aprobación") es una funcionalidad exclusiva de repos de **organización** en GitHub, no de cuenta personal.

## Estado real
GitHub ya exige, sin excepción y sin poder desactivarlo, aprobación manual para el primer workflow run de cualquier colaborador externo en un repo público de cuenta personal. No hay nada que "activar" — la protección ya está ahí por defecto, simplemente no es configurable (no se puede ni aflojar ni volver más estricta) fuera de una organización.

## Corrección
README y docs 29110 actualizados para reflejar esto en vez de dejar un pendiente que nunca se iba a poder resolver tal como estaba escrito. La mitigación real contra el riesgo de RCE via fork sigue siendo la del diseño original: el `if: head.repo.full_name == github.repository` en el workflow, que no depende de esta configuración de GitHub en absoluto.
