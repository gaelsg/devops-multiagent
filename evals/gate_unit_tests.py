"""Pruebas unitarias del guardrail de aprobacion, sin red ni LLM: prueban
directamente la logica de Python que decide si una tool de escritura se
ejecuta o no. Corren instantaneo y no dependen de Ollama/Proxmox estando
disponibles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from devops_multiagent.diagnostician import READ_ONLY_TOOLS, _diagnostician_gate
from devops_multiagent.operator import WRITE_TOOLS, _make_operator_gate

CASES = []


def case(name):
    def decorator(fn):
        CASES.append((name, fn))
        return fn

    return decorator


@case("diagnostician_gate: permite tools de solo lectura")
def _t1():
    for tool in READ_ONLY_TOOLS:
        assert _diagnostician_gate(tool, {}) is True


@case("diagnostician_gate: bloquea las 3 tools de escritura")
def _t2():
    for tool in WRITE_TOOLS:
        assert _diagnostician_gate(tool, {}) is False


@case("operator_gate(approved=False): bloquea escritura")
def _t3():
    gate = _make_operator_gate(approved=False)
    for tool in WRITE_TOOLS:
        assert gate(tool, {}) is False


@case("operator_gate(approved=True): permite escritura")
def _t4():
    gate = _make_operator_gate(approved=True)
    for tool in WRITE_TOOLS:
        assert gate(tool, {}) is True


@case("operator_gate: nunca bloquea lectura, aprobado o no")
def _t5():
    for approved in (True, False):
        gate = _make_operator_gate(approved=approved)
        for tool in READ_ONLY_TOOLS:
            assert gate(tool, {}) is True


def run() -> bool:
    ok = True
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            ok = False
            print(f"  FAIL  {name}: {exc}")
    return ok


if __name__ == "__main__":
    print("=== Gate unit tests ===")
    success = run()
    sys.exit(0 if success else 1)
