"""Thin CLI for implemented operations; scientific commands arrive with owners."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .config import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NeuroSec Core v0 bootstrap")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check-config", help="validate and print resolved configuration; no experiment is run"
    )
    check.add_argument("--config", type=Path, help="optional partial YAML override")
    check.add_argument("--mode", choices=("practice", "experimental"))
    check.add_argument("--seed", type=int)
    args = parser.parse_args(argv)
    try:
        resolved = load_config(
            Path.cwd(), args.config, mode=args.mode, seed=args.seed
        )
    except (ConfigError, OSError) as error:
        parser.error(str(error))
    print(yaml.safe_dump(resolved, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
