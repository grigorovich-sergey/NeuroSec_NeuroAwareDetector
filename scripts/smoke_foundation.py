#!/usr/bin/env python3
"""Run the deterministic synthetic WP0 foundation smoke path."""

from __future__ import annotations

import argparse
from pathlib import Path

from neurosec.foundation.smoke import run_foundation_smoke


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/foundation_smoke_override.yaml"),
        help="optional partial YAML override",
    )
    parser.add_argument("--seed", type=int, help="override run.seed")
    parser.add_argument("--mode", choices=("practice",), default="practice")
    parser.add_argument("--run-id", help="override run.id; generated when omitted")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    result = run_foundation_smoke(
        repo_root=repo_root,
        default_config=repo_root / "configs/foundation.yaml",
        partial_config=args.config,
        seed=args.seed,
        mode=args.mode,
        run_id=args.run_id,
    )
    print(f"WP0 foundation smoke completed: {result.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
