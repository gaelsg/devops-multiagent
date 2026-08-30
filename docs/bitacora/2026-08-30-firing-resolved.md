# 2026-08-30 — Diferenciar mensajes de Telegram firing/resolved

Cierra el pendiente documentado en la Idea 3 (`docs/bitacora/2026-08-29-webhook.md`): "diferenciar el mensaje de Telegram entre alerta disparada y resuelta".

## Cambio
`webhook.py` agrupa las alertas de un mismo payload por `status` (Alertmanager puede mandar una mezcla de `firing` y `resolved` en un solo POST, agrupadas — no es un status por payload, es por alerta):

- **`resolved`:** un solo mensaje simple (`✅ Alerta resuelta`), sin invocar al Diagnostician — no hace falta gastar una llamada al LLM en explicar que algo volvió a la normalidad.
- **`firing`:** mismo comportamiento que antes (`⚠️ Alerta de Prometheus` + diagnóstico del Diagnostician).

## Verificado
POST real con una alerta `resolved` de prueba contra el servicio corriendo (`devops-webhook.service`, reiniciado con el código nuevo): respuesta `200 OK` en menos de un segundo (confirma que no se llamó a `diagnose()`, que toma varios segundos), y el mensaje `✅ Alerta resuelta` llegó a Telegram, sin un segundo mensaje de diagnóstico — confirmado por el usuario.
