from __future__ import annotations

import json
import os

import typer

from ..config import CONFIG_FILE, _mask_secret, is_quiet, load_config, save_config


def configure(
    server_url: str | None = typer.Option(
        None, "--server-url", help="OmniClaw Financial Policy Engine URL"
    ),
    token: str | None = typer.Option(None, "--token", help="Agent token"),
    wallet: str | None = typer.Option(None, "--wallet", help="Wallet alias"),
    owner_token: str | None = typer.Option(None, "--owner-token", help="Owner token"),
    show: bool = typer.Option(False, "--show", help="Show current config"),
    show_raw: bool = typer.Option(False, "--show-raw", help="Show raw secrets"),
    interactive: bool = typer.Option(False, "--interactive", help="Prompt for missing values"),
) -> None:
    """Configure omniclaw-cli with server details."""
    if show or show_raw:
        config = load_config()
        if not config:
            typer.echo("No configuration found. Run 'omniclaw-cli configure --server-url ...'")
            return
        if show_raw:
            typer.echo(json.dumps(config, indent=2))
        else:
            safe = dict(config)
            safe["token"] = _mask_secret(safe.get("token"))
            safe["owner_token"] = _mask_secret(safe.get("owner_token"))
            typer.echo(json.dumps(safe, indent=2))
        return

    config = load_config()
    if interactive:
        default_url = (
            server_url
            or config.get("server_url")
            or os.environ.get("OMNICLAW_SERVER_URL", "http://localhost:8080")
        )
        server_url = typer.prompt("Server URL", default=default_url)
        default_wallet = wallet or config.get("wallet") or "primary"
        wallet = typer.prompt("Wallet alias", default=default_wallet)
        token_default = token or config.get("token") or os.environ.get("OMNICLAW_TOKEN")
        if token_default:
            token = typer.prompt("Agent token", default=token_default, hide_input=True)
        else:
            token = typer.prompt("Agent token", hide_input=True)
        owner_default = (
            owner_token or config.get("owner_token") or os.environ.get("OMNICLAW_OWNER_TOKEN") or ""
        )
        owner_token = typer.prompt("Owner token (optional)", default=owner_default, hide_input=True)

    if server_url:
        config["server_url"] = server_url.rstrip("/")
    if token:
        config["token"] = token
    if wallet:
        config["wallet"] = wallet
    if owner_token:
        config["owner_token"] = owner_token

    if not config.get("server_url") or not config.get("token") or not config.get("wallet"):
        typer.echo(
            "Error: server_url, token, and wallet are required. Use --interactive or pass flags.",
            err=True,
        )
        raise typer.Exit(1)

    save_config(config)
    if is_quiet():
        result = {
            "ok": True,
            "config_path": str(CONFIG_FILE),
            "server_url": config.get("server_url"),
            "wallet": config.get("wallet"),
            "owner_token_set": bool(config.get("owner_token")),
        }
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(f"Configuration saved to {CONFIG_FILE}")
        typer.echo(f"Server: {config.get('server_url')}")
        typer.echo(f"Wallet: {config.get('wallet')}")


def register(app: typer.Typer) -> None:
    app.command()(configure)
