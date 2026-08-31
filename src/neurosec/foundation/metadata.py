"""Run metadata, project/environment capture, hashes, and file inventory."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .records import _json_value


class ExecutionMode(str, Enum):
    PRACTICE = "practice"
    EXPERIMENTAL = "experimental"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def deterministic_identifier(value: Mapping[str, Any], length: int = 16) -> str:
    if length < 8 or length > 64:
        raise ValueError("deterministic identifier length must be between 8 and 64")
    normalized = _json_value(value, "identifier input")
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def capture_project_state(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    try:
        commit = _git(root, "rev-parse", "HEAD")
        porcelain = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"cannot capture Git project state at {root}") from error
    changes = porcelain.splitlines() if porcelain else []
    return {"commit": commit, "working_tree_clean": not changes, "working_tree_changes": changes}


def capture_environment_identity(package_names: Sequence[str]) -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for name in package_names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": versions,
    }


def inventory_files(root: str | Path, excluded_names: Sequence[str] = ()) -> list[dict[str, Any]]:
    directory = Path(root)
    excluded = set(excluded_names)
    inventory: list[dict[str, Any]] = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in excluded:
            continue
        inventory.append(
            {"name": relative, "size_bytes": path.stat().st_size, "sha256": file_sha256(path)}
        )
    return inventory


@dataclass(slots=True)
class RunMetadata:
    run_id: str
    mode: str
    status: RunStatus
    started_at: str
    resolved_config: Mapping[str, Any]
    invocation: tuple[str, ...]
    project_state: Mapping[str, Any]
    environment: Mapping[str, Any]
    rng_seed: int | None
    completed_at: str | None = None
    source_datasets: list[Mapping[str, Any]] = field(default_factory=list)
    input_and_split: Mapping[str, Any] | None = None
    attack: Mapping[str, Any] | None = None
    detector: Mapping[str, Any] | None = None
    victim: Mapping[str, Any] | None = None
    policy: Mapping[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)
    failure: Mapping[str, Any] | None = None
    generated_files: list[Mapping[str, Any]] = field(default_factory=list)
    component_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            self.mode = ExecutionMode(self.mode).value
        except ValueError as error:
            allowed = ", ".join(mode.value for mode in ExecutionMode)
            raise ValueError(f"run mode must be one of: {allowed}") from error

        configured_run = self.resolved_config.get("run")
        if isinstance(configured_run, Mapping):
            configured_mode = configured_run.get("mode")
            if configured_mode is not None and configured_mode != self.mode:
                raise ValueError("run metadata mode does not match resolved configuration")

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        mode: str,
        resolved_config: Mapping[str, Any],
        invocation: Sequence[str],
        project_state: Mapping[str, Any],
        environment: Mapping[str, Any],
        rng_seed: int | None,
        component_metadata: Mapping[str, Any] | None = None,
    ) -> "RunMetadata":
        return cls(
            run_id=run_id,
            mode=mode,
            status=RunStatus.RUNNING,
            started_at=utc_now(),
            resolved_config=resolved_config,
            invocation=tuple(invocation),
            project_state=project_state,
            environment=environment,
            rng_seed=rng_seed,
            component_metadata={} if component_metadata is None else component_metadata,
        )

    def mark_completed(self) -> None:
        self.status = RunStatus.COMPLETED
        self.completed_at = utc_now()
        self.failure = None

    def mark_failed(self, message: str, kind: str = "error") -> None:
        self.status = RunStatus.FAILED
        self.completed_at = utc_now()
        self.failure = {"kind": kind, "message": message}

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return _json_value(value, "run metadata")  # type: ignore[return-value]


def write_run_metadata(
    metadata: RunMetadata,
    path: str | Path,
    *,
    inventory_root: str | Path | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if inventory_root is not None:
        root = Path(inventory_root)
        excluded = (
            [destination.relative_to(root).as_posix()]
            if destination.is_relative_to(root)
            else []
        )
        metadata.generated_files = inventory_files(root, excluded)
    payload = metadata.to_dict()
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
    return destination
