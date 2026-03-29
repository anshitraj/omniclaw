"""Command-line interface for OmniClaw operator utilities."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import os

from omniclaw.onboarding import print_doctor_status


ENV_VARS = {
    "required": {
        "CIRCLE_API_KEY": "Circle API key for wallet/payment operations",
        "ENTITY_SECRET": "Entity secret for transaction signing",
    },
    "optional": {
        "OMNICLAW_RPC_URL": "RPC endpoint for trust gate (ERC-8004)",
        "OMNICLAW_STORAGE_BACKEND": "Storage backend: memory or redis",
        "OMNICLAW_REDIS_URL": "Redis connection URL (when using redis)",
        "OMNICLAW_LOG_LEVEL": "Logging: DEBUG, INFO, WARNING, ERROR",
    },
    "production": {
        "OMNICLAW_ENV": "Set to production for mainnet/strict mode",
        "OMNICLAW_STRICT_SETTLEMENT": "Enable strict settlement validation",
        "OMNICLAW_WEBHOOK_VERIFICATION_KEY": "Public key for webhook signatures",
        "OMNICLAW_SELLER_NONCE_REDIS_URL": "Redis for distributed nonce (multi-instance)",
    },
}


def print_env_vars():
    """Print all available environment variables."""
    print("\n=== OmniClaw Environment Variables ===\n")

    print("Required:")
    for var, desc in ENV_VARS["required"].items():
        value = os.environ.get(var, "")
        status = f"✓ {value[:20]}..." if value else "✗ not set"
        print(f"  {var}")
        print(f"    {desc}")
        print(f"    {status}\n")

    print("\nOptional:")
    for var, desc in ENV_VARS["optional"].items():
        value = os.environ.get(var, "")
        status = f"✓ {value[:30]}..." if value else "○ default"
        print(f"  {var}")
        print(f"    {desc}")
        print(f"    {status}\n")

    print("\nProduction:")
    for var, desc in ENV_VARS["production"].items():
        value = os.environ.get(var, "")
        status = f"✓ {value[:30]}..." if value else "○ not set"
        print(f"  {var}")
        print(f"    {desc}")
        print(f"    {status}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the OmniClaw CLI parser."""
    parser = argparse.ArgumentParser(prog="omniclaw")
    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Inspect OmniClaw setup, managed credentials, and recovery state",
    )
    doctor_parser.add_argument("--api-key", help="Override CIRCLE_API_KEY for diagnostics")
    doctor_parser.add_argument(
        "--entity-secret",
        help="Override ENTITY_SECRET for diagnostics",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    subparsers.add_parser(
        "env",
        help="List all available environment variables",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the OmniClaw CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        print_doctor_status(
            api_key=args.api_key,
            entity_secret=args.entity_secret,
            as_json=args.json,
        )
        return 0

    if args.command == "env":
        print_env_vars()
        return 0

    parser.print_help()
    print("\nCommands:")
    print("  doctor  - Inspect setup and credentials")
    print("  env     - List all environment variables")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
