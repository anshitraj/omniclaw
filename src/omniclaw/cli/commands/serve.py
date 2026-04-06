from __future__ import annotations

import base64
import json
import os
import subprocess
from urllib.parse import urlencode

import typer

from ..config import get_client, is_quiet

try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse

    _FASTAPI_AVAILABLE = True
except Exception:
    FastAPI = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]
    _FASTAPI_AVAILABLE = False


def serve(
    price: float = typer.Option(..., "--price", help="Price per request in USDC"),
    endpoint: str = typer.Option(..., "--endpoint", help="Endpoint path to expose"),
    exec_cmd: str = typer.Option(..., "--exec", help="Command to execute on success"),
    port: int = typer.Option(8000, "--port", help="Local port to listen on"),
) -> None:
    """Expose a local service behind an x402 payment gate.

    Uses the production GatewayMiddleware for full x402 v2 protocol compliance:
    - Returns proper 402 responses with all required fields
    - Parses PAYMENT-SIGNATURE headers
    - Settles atomically via Circle Gateway /settle
    """
    try:
        import uvicorn
    except ImportError as err:
        typer.echo("Error: FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn")
        raise typer.Exit(1) from err
    if not _FASTAPI_AVAILABLE:
        typer.echo("Error: FastAPI not installed. Run: pip install fastapi", err=True)
        raise typer.Exit(1)

    server_app = FastAPI(title="OmniClaw x402 Payment Gate")
    ctrl_client = get_client()

    # Price string in USD format
    price_usd = f"${price}"

    @server_app.api_route(endpoint, methods=["GET", "POST", "PUT", "DELETE"])
    async def payment_gate(request: Request):
        try:
            headers = dict(request.headers)
            sig_header = headers.get("payment-signature") or headers.get("PAYMENT-SIGNATURE")

            if not sig_header:
                requirements_resp = ctrl_client.post(
                    "/api/v1/x402/requirements",
                    json={
                        "amount": price_usd,
                        "resource": str(request.url),
                    },
                )
                requirements_resp.raise_for_status()
                requirements = requirements_resp.json()
                return JSONResponse(
                    status_code=requirements.get("status_code", 402),
                    content=requirements.get("detail", {}),
                    headers=requirements.get("headers", {}),
                )

            verify_resp = ctrl_client.post(
                "/api/v1/x402/verify",
                json={
                    "signature": sig_header,
                    "amount": str(price),
                    "sender": headers.get("x-forwarded-for", ""),
                    "resource": str(request.url),
                },
            )
            verify_resp.raise_for_status()
            verify_data = verify_resp.json()
            if not verify_data.get("valid"):
                requirements_resp = ctrl_client.post(
                    "/api/v1/x402/requirements",
                    json={
                        "amount": price_usd,
                        "resource": str(request.url),
                    },
                )
                requirements_resp.raise_for_status()
                requirements = requirements_resp.json()
                return JSONResponse(
                    status_code=402,
                    content=requirements.get("detail", {"error": verify_data.get("error")}),
                    headers=requirements.get("headers", {}),
                )

            # Payment settled successfully — execute the command
            try:
                env = os.environ.copy()
                env["OMNICLAW_PAYER_ADDRESS"] = verify_data.get("sender") or "unknown"
                env["OMNICLAW_AMOUNT_USD"] = str(price)
                env["OMNICLAW_TX_HASH"] = verify_data.get("transaction") or ""
                env["OMNICLAW_REQUEST_METHOD"] = request.method
                env["OMNICLAW_REQUEST_PATH"] = request.url.path
                env["OMNICLAW_REQUEST_URL"] = str(request.url)
                env["OMNICLAW_REQUEST_QUERY"] = urlencode(list(request.query_params.multi_items()))

                raw_body = await request.body()
                env["OMNICLAW_REQUEST_BODY_BASE64"] = base64.b64encode(raw_body).decode()
                if raw_body:
                    try:
                        env["OMNICLAW_REQUEST_BODY_TEXT"] = raw_body.decode("utf-8")
                    except UnicodeDecodeError:
                        env["OMNICLAW_REQUEST_BODY_TEXT"] = ""
                else:
                    env["OMNICLAW_REQUEST_BODY_TEXT"] = ""

                result = subprocess.run(
                    exec_cmd, shell=True, capture_output=True, text=True, env=env
                )
                media_type = "text/plain"
                stripped = result.stdout.lstrip()
                if stripped.startswith("{") or stripped.startswith("["):
                    media_type = "application/json"
                response = Response(content=result.stdout, media_type=media_type)
            except Exception as e:
                response = JSONResponse(
                    status_code=500,
                    content={"detail": f"Execution failed: {e}"},
                )

            response.headers["PAYMENT-RESPONSE"] = base64.b64encode(
                json.dumps(
                    {
                        "success": True,
                        "transaction": verify_data.get("transaction", ""),
                        "network": "",
                        "payer": verify_data.get("sender", ""),
                    }
                ).encode()
            ).decode()

            return response
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"detail": f"Payment processing failed: {e}"},
            )

    if not is_quiet():
        typer.echo(f"OmniClaw service exposed at http://localhost:{port}{endpoint}")
        typer.echo(f"Price: ${price} USDC per request")
        typer.echo(f"Exec: {exec_cmd}")
        typer.echo("x402 v2 Protocol — Circle Gateway settlement")
        typer.echo("")

    uvicorn.run(server_app, host="0.0.0.0", port=port)


def register(app: typer.Typer, group: typer.Typer | None = None) -> None:
    app.command()(serve)
    if group is not None and group is not app:
        group.command()(serve)
