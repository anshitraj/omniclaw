from __future__ import annotations

import json
from typing import Any

import httpx
import typer

from ..config import get_client, is_quiet, load_config


def status() -> dict[str, Any]:
    """Get agent status and health."""
    client = get_client()
    config = load_config()

    try:
        # Get multiple stats for a complete status report
        health = client.get("/api/v1/health").json()
        balance_data = client.get("/api/v1/balance").json()
        addr_data = client.get("/api/v1/address").json()

        status_data = {
            "Agent": config.get("wallet", "unknown"),
            "Wallet": addr_data.get("address"),
            "Balance": f"${balance_data.get('available')} available",
            "Guards": "active" if health.get("status") == "ok" else "degraded",
            "Circle": "connected" if health.get("status") == "ok" else "disconnected",
            "Circuit": "CLOSED" if health.get("status") == "ok" else "OPEN",
        }

        if is_quiet():
            typer.echo(json.dumps(status_data, indent=2))
        else:
            typer.echo(f"Agent:     {status_data['Agent']}")
            typer.echo(f"Wallet:    {status_data['Wallet']}")
            typer.echo(f"Balance:   {status_data['Balance']}")
            typer.echo(f"Guards:    {status_data['Guards']}")
            circle_icon = "ok" if status_data["Circle"] == "connected" else "err"
            circuit_icon = "ok" if status_data["Circuit"] == "CLOSED" else "warn"
            typer.echo(f"Circle:    {status_data['Circle']} ({circle_icon})")
            typer.echo(f"Circuit:   {status_data['Circuit']} ({circuit_icon})")

        return status_data
    except Exception as e:
        typer.echo(f"Error fetching status: {e}", err=True)
        raise typer.Exit(1) from e


def ping() -> dict[str, Any]:
    """Health check."""
    from omniclaw import __version__

    client = get_client()

    try:
        response = client.get("/api/v1/health")
        response.raise_for_status()
        data = response.json()
        data["version"] = __version__
        typer.echo(json.dumps(data, indent=2))
        return data
    except httpx.HTTPStatusError as e:
        typer.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        raise typer.Exit(1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    app.command()(status)
    app.command()(ping)

    if group is not None and group is not app:
        group.command()(status)
        group.command()(ping)
