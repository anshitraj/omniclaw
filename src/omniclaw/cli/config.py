from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import typer

CONFIG_DIR = Path(os.environ.get("OMNICLAW_CONFIG_DIR", Path.home() / ".omniclaw"))
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration from file."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def is_quiet() -> bool:
    if str(os.environ.get("OMNICLAW_CLI_HUMAN", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False

    flag = os.environ.get("OMNICLAW_CLI_QUIET") or os.environ.get("OMNICLAW_CLI_AGENT")
    if flag is None:
        return True
    return str(flag).strip().lower() not in {"0", "false", "no", "off"}


def get_client(*, owner: bool = False) -> httpx.Client:
    """Get HTTP client with auth."""
    config = load_config()
    server_url = os.environ.get("OMNICLAW_SERVER_URL") or config.get("server_url")
    token = os.environ.get("OMNICLAW_TOKEN") or config.get("token")
    owner_token = os.environ.get("OMNICLAW_OWNER_TOKEN") or config.get("owner_token")

    if not server_url:
        typer.echo("Error: Server URL not configured. Run 'omniclaw-cli configure'", err=True)
        raise typer.Exit(1)

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if owner:
        if not owner_token:
            typer.echo(
                "Error: Owner token not configured. Set OMNICLAW_OWNER_TOKEN or run 'omniclaw-cli configure --owner-token ...'",
                err=True,
            )
            raise typer.Exit(1)
        headers["X-Omniclaw-Owner-Token"] = owner_token

    return httpx.Client(base_url=server_url, headers=headers, timeout=30.0)
