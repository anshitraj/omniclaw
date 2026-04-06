#!/usr/bin/env python3
"""Startup script for Cloud Run honoring the PORT environment variable."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")

    print(f"Starting OmniClaw MCP Server on {host}:{port}")
    print(f"Environment: {os.environ.get('ENVIRONMENT', 'not set')}")

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
