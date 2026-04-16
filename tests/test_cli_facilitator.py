from argparse import Namespace

from omniclaw.admin_cli import build_parser, handle_facilitator_exact


def test_facilitator_exact_parser_accepts_arc_profile() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "facilitator",
            "exact",
            "--network-profile",
            "ARC-TESTNET",
            "--network",
            "eip155:5042002",
            "--port",
            "4122",
        ]
    )

    assert args.command == "facilitator"
    assert args.facilitator_command == "exact"
    assert args.network_profile == "ARC-TESTNET"
    assert args.network == ["eip155:5042002"]
    assert args.port == 4122


def test_facilitator_exact_requires_private_key(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "OMNICLAW_X402_FACILITATOR_PRIVATE_KEY",
        "OMNICLAW_PRIVATE_KEY",
        "OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE",
        "OMNICLAW_X402_FACILITATOR_RPC_URL",
        "OMNICLAW_X402_FACILITATOR_NETWORKS",
        "OMNICLAW_NETWORK",
    ):
        monkeypatch.delenv(name, raising=False)

    args = Namespace(
        host="127.0.0.1",
        port=4022,
        network_profile="BASE-SEPOLIA",
        network=None,
        rpc_url="https://sepolia.base.org",
        private_key=None,
        title=None,
    )

    assert handle_facilitator_exact(args) == 1
    assert "OMNICLAW_X402_FACILITATOR_PRIVATE_KEY" in capsys.readouterr().out
