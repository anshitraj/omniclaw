#!/usr/bin/env python3
from __future__ import annotations

from omniclaw.facilitator import (
    create_exact_facilitator_app,
    load_exact_facilitator_config_from_env,
)


config = load_exact_facilitator_config_from_env()
app = create_exact_facilitator_app(config)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port)
