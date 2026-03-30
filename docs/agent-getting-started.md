# OmniClaw: Zero-Friction Onboarding

OmniClaw is designed for **instant deployment**. The Agent takes full responsibility for its own environment setup.

---

## 🛡️ Phase 1: Human Owner (Control Plane)
*Host your secure Financial Firewall. One command to rule them all.*

1.  **Configure API Key**:
    Add your `CIRCLE_API_KEY` to your environment or `.env` file.

2.  **Start the Firewall**:
    ```bash
    docker compose -f docker-compose.agent.yml up -d
    ```

3.  **Provide Connection Details**:
    Ensure your Agent has access to these three environment variables:
    - `OMNICLAW_SERVER_URL`: Where your firewall is running.
    - `OMNICLAW_TOKEN`: Your agent's authorization token.
    - `OMNICLAW_WALLET`: (Optional) The wallet alias (default: `primary`).

---

## 🤖 Phase 2: AI Agent (Autonomous Setup)
*The Agent is self-bootstrapping. It installs and configures itself.*

1.  **Skill Injection**:
    The Owner drops the `omniclaw-cli` skill folder into the agent's environment.

2.  **Self-Bootstrap**:
    The agent autonomously executes its **Bootstrap Protocol**:
    - **Runs `install_cli.sh`**: Installs the latest CLI tool.
    - **Runs `configure_cli.sh`**: Links itself to the Owner's Firewall using the provided env vars.

3.  **Ready for Action**:
    The agent is now live. It can check balances and execute payments entirely through the CLI.

---

## 🏁 Result
- **Zero Human Friction**: The owner only starts the server and sets env vars.
- **Agent Responsibility**: The agent manages its own tools and connection.
- **Pure Security**: Private keys never leave the Owner's Docker container.
