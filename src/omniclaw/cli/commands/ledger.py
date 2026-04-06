from __future__ import annotations

import json
from typing import Any

import httpx
import typer

from ..config import get_client


def ledger(
    limit: int = typer.Option(20, "--limit", help="Number of transactions to fetch"),
) -> dict[str, Any]:
    """List transaction history."""
    return list_tx(limit=limit)


def list_tx(
    limit: int = typer.Option(20, "--limit", help="Number of transactions to fetch"),
) -> dict[str, Any]:
    """List transaction history."""
    client = get_client()

    try:
        response = client.get("/api/v1/transactions", params={"limit": limit})
        response.raise_for_status()
        data = response.json()
        typer.echo(json.dumps(data, indent=2))
        return data
    except httpx.HTTPStatusError as e:
        typer.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        raise typer.Exit(1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


def list_tx_alias(
    limit: int = typer.Option(20, "--limit", help="Number of transactions to fetch"),
) -> dict[str, Any]:
    """Alias for list-tx."""
    return list_tx(limit=limit)


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    app.command()(ledger)
    app.command("list-tx")(list_tx)
    app.command(name="list_tx", help="Alias for list-tx")(list_tx_alias)

    if group is not None and group is not app:
        group.command()(ledger)
        group.command("list-tx")(list_tx)
        group.command(name="list_tx", help="Alias for list-tx")(list_tx_alias)
