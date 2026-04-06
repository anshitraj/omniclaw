from __future__ import annotations

import json
from typing import Any

import httpx
import typer

from ..config import get_client


def get_confirmation(
    confirmation_id: str = typer.Option(..., "--id", help="Confirmation ID"),
) -> dict[str, Any]:
    """Get confirmation details."""
    client = get_client(owner=True)

    try:
        response = client.get(f"/api/v1/confirmations/{confirmation_id}")
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


def approve_confirmation(
    confirmation_id: str = typer.Option(..., "--id", help="Confirmation ID"),
) -> dict[str, Any]:
    """Approve a confirmation."""
    client = get_client(owner=True)

    try:
        response = client.post(f"/api/v1/confirmations/{confirmation_id}/approve")
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


def deny_confirmation(
    confirmation_id: str = typer.Option(..., "--id", help="Confirmation ID"),
) -> dict[str, Any]:
    """Deny a confirmation."""
    client = get_client(owner=True)

    try:
        response = client.post(f"/api/v1/confirmations/{confirmation_id}/deny")
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


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    # confirmations are owner-only; keep under group if provided
    if group is not None and group is not app:
        group.command("get")(get_confirmation)
        group.command("approve")(approve_confirmation)
        group.command("deny")(deny_confirmation)
