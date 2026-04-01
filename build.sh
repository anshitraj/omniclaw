#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "Building OmniClaw release artifacts..."

if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv is required to run build.sh"
    echo "Install it from https://docs.astral.sh/uv/"
    exit 1
fi

echo "Cleaning previous build artifacts..."
rm -rf dist build .pytest_cache
find . -maxdepth 2 -type d \( -name "*.egg-info" -o -name "*.dist-info" \) -prune -exec rm -rf {} +

echo "Running release-oriented SDK checks..."
uv run pytest tests/test_setup.py tests/test_payment_intents.py tests/test_client.py tests/test_webhook_verification.py

echo "Building sdist and wheel..."
uv run python3 -m build

echo "Validating package metadata..."
uv run twine check dist/*

echo
echo "Build complete."
echo "Artifacts:"
ls -1 dist
echo
echo "Next:"
echo "  1. Inspect dist/"
echo "  2. Upload with: uv run twine upload dist/*"
