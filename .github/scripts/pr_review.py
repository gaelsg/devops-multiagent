"""Review de PR generado por qwen3:14b local (Ollama), corriendo en el
runner self-hosted. Solo lee el diff y comenta -- nunca aprueba, nunca
bloquea el merge. El guardrail humano sigue siendo el que decide.
"""

import os
import subprocess
import sys

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:14b"
MAX_DIFF_CHARS = 15000

DISCLAIMER = (
    "🤖 **Review automático (qwen3:14b, Ollama local)** — sugerencia, no bloquea el "
    "merge. Un humano debe validar antes de aprobar.\n\n---\n\n"
)

PROMPT_TEMPLATE = """Sos un revisor de codigo senior. Revisa el siguiente diff de un pull \
request y comenta SOLO lo que sea relevante:
- Bugs o casos borde no manejados.
- Problemas de seguridad (secretos hardcodeados, inyeccion, permisos de mas).
- Tests faltantes para el cambio.
- Legibilidad/mantenibilidad, solo si es realmente confuso.

Si no encontras nada relevante, respondé exactamente: "Sin observaciones."
Se conciso, en español, en formato de lista. No repitas el diff.

Diff:
```
{diff}
```
"""


def get_pr_diff(pr_number: str) -> str:
    result = subprocess.run(
        ["gh", "pr", "diff", pr_number], capture_output=True, text=True, check=True
    )
    return result.stdout


def strip_reasoning(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def review(diff: str) -> str:
    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        diff = diff[:MAX_DIFF_CHARS]
    prompt = PROMPT_TEMPLATE.format(diff=diff)
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    text = strip_reasoning(content) or "Sin observaciones."
    if truncated:
        text += "\n\n_(diff truncado a los primeros 15000 caracteres para el review)_"
    return text


def post_comment(pr_number: str, body: str) -> None:
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", DISCLAIMER + body],
        check=True,
    )


def main() -> int:
    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        print("PR_NUMBER no seteado, nada que revisar.")
        return 0

    diff = get_pr_diff(pr_number)
    if not diff.strip():
        print("Diff vacio, nada que revisar.")
        return 0

    try:
        text = review(diff)
    except Exception as exc:
        print(f"No se pudo generar el review con Ollama: {type(exc).__name__}: {exc}")
        return 0  # advisorio, nunca bloquea el merge

    post_comment(pr_number, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
