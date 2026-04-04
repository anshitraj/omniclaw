from __future__ import annotations

import os
import subprocess
from typing import Any

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

    circle_api_key = os.environ.get("CIRCLE_API_KEY", "").strip()
    if not circle_api_key:
        typer.echo(
            "Error: CIRCLE_API_KEY is required for omniclaw-cli serve. "
            "Start serve in a shell/container that has the seller Circle credentials.",
            err=True,
        )
        raise typer.Exit(1)

    server_app = FastAPI(title="OmniClaw x402 Payment Gate")
    ctrl_client = get_client()

    # Price string in USD format for GatewayMiddleware
    price_usd = f"${price}"

    # We'll initialize the middleware lazily on first request
    _middleware_holder: dict[str, Any] = {}

    async def _get_middleware():
        """Lazily initialize GatewayMiddleware with seller's nano address."""
        if "mw" in _middleware_holder:
            return _middleware_holder["mw"]

        from omniclaw.protocols.nanopayments.client import NanopaymentClient
        from omniclaw.protocols.nanopayments.middleware import GatewayMiddleware

        # Get the seller's nano address from the Financial Policy Engine
        try:
            nano_resp = ctrl_client.get("/api/v1/nano-address")
            if nano_resp.status_code == 200:
                seller_address = nano_resp.json().get("address")
            else:
                addr_resp = ctrl_client.get("/api/v1/address")
                seller_address = addr_resp.json().get("address")
        except Exception:
            addr_resp = ctrl_client.get("/api/v1/address")
            seller_address = addr_resp.json().get("address")

        if not seller_address:
            raise RuntimeError("Could not resolve seller address from Financial Policy Engine")

        # Initialize Circle nanopayment client
        nano_client = NanopaymentClient(api_key=circle_api_key)

        # Build production middleware
        mw = GatewayMiddleware(
            seller_address=seller_address,
            nanopayment_client=nano_client,
        )

        _middleware_holder["mw"] = mw
        if not is_quiet():
            typer.echo(f"  Seller address: {seller_address}")
        return mw

    @server_app.api_route(endpoint, methods=["GET", "POST", "PUT", "DELETE"])
    async def payment_gate(request: Request):
        from omniclaw.protocols.nanopayments.middleware import PaymentRequiredHTTPError

        try:
            middleware = await _get_middleware()
            headers = dict(request.headers)

            # GatewayMiddleware.handle() does the full x402 v2 flow:
            # - If no PAYMENT-SIGNATURE: raises PaymentRequiredHTTPError (402)
            # - If valid signature: settles via Circle Gateway and returns PaymentInfo
            payment_info = await middleware.handle(headers, price_usd)

            # Payment settled successfully — execute the command
            try:
                env = os.environ.copy()
                env["OMNICLAW_PAYER_ADDRESS"] = payment_info.payer or "unknown"
                env["OMNICLAW_AMOUNT_USD"] = str(price)
                env["OMNICLAW_TX_HASH"] = payment_info.transaction or ""

                result = subprocess.run(
                    exec_cmd, shell=True, capture_output=True, text=True, env=env
                )
                response = Response(content=result.stdout, media_type="text/plain")
            except Exception as e:
                response = JSONResponse(
                    status_code=500,
                    content={"detail": f"Execution failed: {e}"},
                )

            # Add PAYMENT-RESPONSE header (x402 v2 spec requirement)
            payment_resp_headers = middleware.payment_response_headers(payment_info)
            for k, v in payment_resp_headers.items():
                response.headers[k] = v

            return response

        except PaymentRequiredHTTPError as exc:
            # Return 402 with proper x402 v2 requirements
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )
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
