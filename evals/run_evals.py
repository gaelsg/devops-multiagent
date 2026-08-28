import asyncio
import sys

import gate_unit_tests
import scenarios

if __name__ == "__main__":
    print("=== Gate unit tests ===")
    unit_ok = gate_unit_tests.run()

    print("\n=== Integration scenarios (Ollama + MCP reales) ===")
    integration_ok = asyncio.run(scenarios.run_all())

    print(f"\nResultado: {'TODO OK' if unit_ok and integration_ok else 'HAY FALLOS'}")
    sys.exit(0 if unit_ok and integration_ok else 1)
