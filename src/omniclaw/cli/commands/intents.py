from __future__ import annotations

import json
from typing import Any

import httpx
import typer

from ..config import get_client


def create_intent(
    recipient: str = typer.Option(..., "--recipient", help="Recipient"),
    amount: str = typer.Option(..., "--amount", help="Amount"),
    purpose: str | None = typer.Option(None, "--purpose", help="Purpose"),
    expires_in: int | None = typer.Option(None, "--expires-in", help="Expiry in seconds"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    destination_chain: str | None = typer.Option(
        None, "--destination-chain", help="Target network"
    ),
    fee_level: str | None = typer.Option(
        None, "--fee-level", help="Gas fee level (LOW, MEDIUM, HIGH)"
    ),
    check_trust: bool = typer.Option(False, "--check-trust", help="Run Trust Gate check"),
    skip_guards: bool = typer.Option(False, "--skip-guards", help="Skip guards (OWNER ONLY)"),
) -> dict[str, Any]:
    """Create a payment intent (authorize)."""
    client = get_client()

    payload: dict[str, Any] = {
        "recipient": recipient,
        "amount": amount,
    }
    if purpose:
        payload["purpose"] = purpose
    if expires_in:
        payload["expires_in"] = expires_in
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    if destination_chain:
        payload["destination_chain"] = destination_chain
    if fee_level:
        payload["fee_level"] = fee_level
    if check_trust:
        payload["check_trust"] = True
    if skip_guards:
        payload["skip_guards"] = True

    try:
        response = client.post("/api/v1/intents", json=payload)
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


def create_intent_alias(
    recipient: str = typer.Option(..., "--recipient", help="Recipient"),
    amount: str = typer.Option(..., "--amount", help="Amount"),
    purpose: str | None = typer.Option(None, "--purpose", help="Purpose"),
    expires_in: int | None = typer.Option(None, "--expires-in", help="Expiry in seconds"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    destination_chain: str | None = typer.Option(
        None, "--destination-chain", help="Target network"
    ),
    fee_level: str | None = typer.Option(
        None, "--fee-level", help="Gas fee level (LOW, MEDIUM, HIGH)"
    ),
    check_trust: bool = typer.Option(False, "--check-trust", help="Run Trust Gate check"),
    skip_guards: bool = typer.Option(False, "--skip-guards", help="Skip guards (OWNER ONLY)"),
) -> dict[str, Any]:
    """Alias for create-intent."""
    return create_intent(
        recipient=recipient,
        amount=amount,
        purpose=purpose,
        expires_in=expires_in,
        idempotency_key=idempotency_key,
        destination_chain=destination_chain,
        fee_level=fee_level,
        check_trust=check_trust,
        skip_guards=skip_guards,
    )


def confirm_intent(
    intent_id: str = typer.Option(..., "--intent-id", help="Intent ID to confirm"),
) -> dict[str, Any]:
    """Confirm a payment intent (capture)."""
    client = get_client()

    try:
        response = client.post(f"/api/v1/intents/{intent_id}/confirm")
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


def confirm_intent_alias(
    intent_id: str = typer.Option(..., "--intent-id", help="Intent ID to confirm"),
) -> dict[str, Any]:
    """Alias for confirm-intent."""
    return confirm_intent(intent_id=intent_id)


def get_intent(
    intent_id: str = typer.Option(..., "--intent-id", help="Intent ID to fetch"),
) -> dict[str, Any]:
    """Get a payment intent."""
    client = get_client()

    try:
        response = client.get(f"/api/v1/intents/{intent_id}")
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


def get_intent_alias(
    intent_id: str = typer.Option(..., "--intent-id", help="Intent ID to fetch"),
) -> dict[str, Any]:
    """Alias for get-intent."""
    return get_intent(intent_id=intent_id)


def cancel_intent(
    intent_id: str = typer.Option(..., "--intent-id", help="Intent ID to cancel"),
    reason: str | None = typer.Option(None, "--reason", help="Cancel reason"),
) -> dict[str, Any]:
    """Cancel a payment intent."""
    client = get_client()

    try:
        response = client.delete(
            f"/api/v1/intents/{intent_id}", params={"reason": reason} if reason else {}
        )
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


def cancel_intent_alias(
    intent_id: str = typer.Option(..., "--intent-id", help="Intent ID to cancel"),
    reason: str | None = typer.Option(None, "--reason", help="Cancel reason"),
) -> dict[str, Any]:
    """Alias for cancel-intent."""
    return cancel_intent(intent_id=intent_id, reason=reason)


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    app.command("create-intent")(create_intent)
    app.command(name="create_intent", help="Alias for create-intent")(create_intent_alias)
    app.command("confirm-intent")(confirm_intent)
    app.command(name="confirm_intent", help="Alias for confirm-intent")(confirm_intent_alias)
    app.command("get-intent")(get_intent)
    app.command(name="get_intent", help="Alias for get-intent")(get_intent_alias)
    app.command("cancel-intent")(cancel_intent)
    app.command(name="cancel_intent", help="Alias for cancel-intent")(cancel_intent_alias)

    if group is not None and group is not app:
        group.command("create-intent")(create_intent)
        group.command(name="create_intent", help="Alias for create-intent")(create_intent_alias)
        group.command("confirm-intent")(confirm_intent)
        group.command(name="confirm_intent", help="Alias for confirm-intent")(confirm_intent_alias)
        group.command("get-intent")(get_intent)
        group.command(name="get_intent", help="Alias for get-intent")(get_intent_alias)
        group.command("cancel-intent")(cancel_intent)
        group.command(name="cancel_intent", help="Alias for cancel-intent")(cancel_intent_alias)
