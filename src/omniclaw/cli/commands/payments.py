from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import typer

from ..config import get_client, is_quiet


def pay(
    recipient: str = typer.Option(..., "--recipient", help="Payment recipient (address or URL)"),
    amount: str | None = typer.Option(
        None, "--amount", help="Amount in USDC (optional for x402 URLs)"
    ),
    purpose: str | None = typer.Option(None, "--purpose", help="Payment purpose"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="Idempotency key"),
    destination_chain: str | None = typer.Option(
        None, "--destination-chain", help="Target network"
    ),
    fee_level: str | None = typer.Option(
        None, "--fee-level", help="Gas fee level (LOW, MEDIUM, HIGH)"
    ),
    check_trust: bool = typer.Option(False, "--check-trust", help="Run Trust Gate check"),
    skip_guards: bool = typer.Option(False, "--skip-guards", help="Skip guards (OWNER ONLY)"),
    method: str = typer.Option("GET", "--method", help="HTTP method for x402 requests"),
    body: str | None = typer.Option(None, "--body", help="JSON body for x402 requests"),
    header: list[str] = typer.Option([], "--header", help="Additional headers for x402 requests"),
    output: str | None = typer.Option(None, "--output", help="Save response to file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate first"),
) -> dict[str, Any]:
    """Execute a payment or pay for an x402 service."""
    if dry_run:
        return simulate(
            recipient=recipient,
            amount=amount or "0.00",
            idempotency_key=idempotency_key,
            destination_chain=destination_chain,
            fee_level=fee_level,
            check_trust=check_trust,
            skip_guards=skip_guards,
        )

    client = get_client()

    # If recipient is a URL, handle x402 flow
    if recipient.startswith("http"):
        if not is_quiet():
            typer.echo(f"Paying for x402 service: {recipient}")
        payload: dict[str, Any] = {
            "url": recipient,
            "method": method,
        }
        if body:
            payload["body"] = body
        if header:
            parsed_headers: dict[str, str] = {}
            for raw in header:
                key, sep, value = raw.partition(":")
                if not sep:
                    typer.echo(
                        f"Error: Invalid header '{raw}'. Use 'Header: value' format.",
                        err=True,
                    )
                    raise typer.Exit(1)
                parsed_headers[key.strip()] = value.strip()
            payload["headers"] = parsed_headers
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key

        try:
            response = client.post("/api/v1/x402/pay", json=payload)
            response.raise_for_status()
            data = response.json()
            requires_confirmation = data.get("requires_confirmation") or data.get(
                "confirmation_required"
            )
            if not is_quiet() and requires_confirmation:
                confirmation_id = data.get("confirmation_id")
                if confirmation_id:
                    typer.echo("Payment requires confirmation.")
                    typer.echo(f"Run: omniclaw-cli confirmations approve --id {confirmation_id}")
            if output:
                Path(output).write_text(json.dumps(data, indent=2))
                if not is_quiet():
                    typer.echo(f"Response saved to {output}")
                if is_quiet():
                    typer.echo(json.dumps(data, indent=2))
            else:
                typer.echo(json.dumps(data, indent=2))
            return data
        except httpx.HTTPStatusError as e:
            typer.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
            raise typer.Exit(1) from e
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from e

    # Standard direct transfer
    if not amount:
        if is_quiet():
            typer.echo("Error: --amount is required for direct transfers", err=True)
            raise typer.Exit(1)
        amount = typer.prompt("Amount (USDC)")

    payload = {
        "recipient": recipient,
        "amount": amount,
    }
    if purpose:
        payload["purpose"] = purpose
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
        response = client.post("/api/v1/pay", json=payload)
        response.raise_for_status()
        data = response.json()
        requires_confirmation = data.get("requires_confirmation") or data.get(
            "confirmation_required"
        )
        if not is_quiet() and requires_confirmation:
            confirmation_id = data.get("confirmation_id")
            if confirmation_id:
                typer.echo("Payment requires confirmation.")
                typer.echo(f"Run: omniclaw-cli confirmations approve --id {confirmation_id}")
        typer.echo(json.dumps(data, indent=2))
        return data
    except httpx.HTTPStatusError as e:
        typer.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        raise typer.Exit(1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


def simulate(
    recipient: str = typer.Option(..., "--recipient", help="Recipient to simulate"),
    amount: str = typer.Option(..., "--amount", help="Amount to simulate"),
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
    """Simulate a payment without executing."""
    client = get_client()

    payload: dict[str, Any] = {
        "recipient": recipient,
        "amount": amount,
    }
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
        response = client.post("/api/v1/simulate", json=payload)
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


def can_pay(
    recipient: str = typer.Option(..., "--recipient", help="Recipient to check"),
) -> dict[str, Any]:
    """Check if recipient is allowed."""
    client = get_client()

    try:
        response = client.get("/api/v1/can-pay", params={"recipient": recipient})
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


def can_pay_alias(
    recipient: str = typer.Option(..., "--recipient", help="Recipient to check"),
) -> dict[str, Any]:
    """Alias for can-pay."""
    return can_pay(recipient=recipient)


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    app.command()(pay)
    app.command()(simulate)
    app.command("can-pay")(can_pay)
    app.command(name="can_pay", help="Alias for can-pay")(can_pay_alias)

    if group is not None and group is not app:
        group.command()(pay)
        group.command()(simulate)
        group.command("can-pay")(can_pay)
        group.command(name="can_pay", help="Alias for can-pay")(can_pay_alias)
