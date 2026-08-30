from __future__ import annotations

import os

import requests


def load_secrets_from_vault() -> None:
    """Trae los secretos reales (Telegram, shared secret del webhook) desde
    Vault via AppRole y los inyecta en os.environ -- mismo patron que
    proxmox-mcp-server/secrets_loader.py y k8s-mcp-server/secrets_loader.py.

    No hace nada si no hay VAULT_ROLE_ID (permite correr con lo que ya haya
    en el entorno, ej. desarrollo local sin Vault). Falla rapido si Vault
    esta configurado pero no responde.
    """
    role_id = os.environ.get("VAULT_ROLE_ID")
    secret_id = os.environ.get("VAULT_SECRET_ID")
    if not role_id or not secret_id:
        return

    addr = os.environ["VAULT_ADDR"]
    cacert = os.environ.get("VAULT_CACERT")
    verify: bool | str = cacert if cacert else True

    login = requests.post(
        f"{addr}/v1/auth/approle/login",
        json={"role_id": role_id, "secret_id": secret_id},
        verify=verify,
        timeout=10,
    )
    login.raise_for_status()
    token = login.json()["auth"]["client_token"]

    resp = requests.get(
        f"{addr}/v1/secret/data/devops-multiagent",
        headers={"X-Vault-Token": token},
        verify=verify,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()["data"]["data"]

    for key, value in data.items():
        os.environ[key] = value
