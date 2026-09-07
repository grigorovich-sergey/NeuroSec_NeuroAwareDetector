"""Versioned run provenance and file identities; no scientific computations."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

METADATA_PATH = "results/run_meta.json"


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
    if not 8 <= length <= 64:
        raise ValueError("identifier length must be between 8 and 64")
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def capture_project_state(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    try:
        commit = _git(root, "rev-parse", "HEAD")
        ref = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        changes = _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"cannot capture Git project state at {root}") from error
    return {
        "commit": commit,
        "ref": None if ref == "HEAD" else ref,
        "working_tree_clean": not changes,
        "working_tree_changes": changes,
    }


def capture_environment_identity(
    package_names: Sequence[str] = ("neurosec-core", "numpy", "PyYAML"),
) -> dict[str, Any]:
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


def inventory_files(root: str | Path) -> list[dict[str, Any]]:
    """Hash all regular output files except the metadata itself.

    Symlinks are rejected so completed artifacts cannot depend on mutable files
    outside their run. Metadata cannot include its own checksum.
    """
    directory = Path(root)
    inventory = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"run artifacts must not be symlinks: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"run artifact must be a regular file: {path}")
        name = path.relative_to(directory).as_posix()
        if name != METADATA_PATH:
            inventory.append(
                {"name": name, "size_bytes": path.stat().st_size, "sha256": file_sha256(path)}
            )
    return inventory


@dataclass(slots=True)
class RunMetadata:
    run_id: str
    mode: str
    status: RunStatus
    started_at: str
    resolved_config: dict[str, Any]
    invocation: tuple[str, ...]
    project_state: dict[str, Any]
    environment: dict[str, Any]
    rng_seed: int
    data_kind: str
    cohort_role: str
    schema_version: int = field(default=1, init=False)
    finished_at: str | None = None
    inputs: list[dict[str, Any]] = field(default_factory=list)
    components: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)
    failure: dict[str, str] | None = None
    generated_files: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = RunStatus(self.status)
        if not all(isinstance(value, dict) for value in (
            self.resolved_config, self.project_state, self.environment
        )):
            raise ValueError("config, project_state, and environment must be mappings")
        self.resolved_config = deepcopy(self.resolved_config)
        self.project_state = deepcopy(self.project_state)
        self.environment = deepcopy(self.environment)
        if self.mode not in ("practice", "experimental"):
            raise ValueError("mode must be practice or experimental")
        if type(self.rng_seed) is not int or self.rng_seed < 0:
            raise ValueError("rng_seed must be a nonnegative integer")
        configured_run = self.resolved_config.get("run", {})
        if (
            not isinstance(configured_run, dict)
            or configured_run.get("mode") != self.mode
            or type(configured_run.get("seed")) is not int
            or configured_run.get("seed") != self.rng_seed
        ):
            raise ValueError("metadata mode/seed must match the resolved configuration")
        if self.data_kind not in ("real", "synthetic"):
            raise ValueError("data_kind must be real or synthetic")
        if self.cohort_role not in ("development", "report"):
            raise ValueError("cohort_role must be development or report")
        if self.data_kind == "synthetic" and self.cohort_role == "report":
            raise ValueError("synthetic inputs cannot be report evidence")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunMetadata":
        """Read this version's complete record; absent/unknown fields fail."""
        if (
            not isinstance(value, dict)
            or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
        ):
            raise ValueError("unsupported or missing metadata schema_version")
        fields = {key: item for key, item in value.items() if key != "schema_version"}
        try:
            metadata = cls(**fields)
            metadata.to_dict()
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid run metadata: {error}") from error
        return metadata

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        resolved_config: dict[str, Any],
        invocation: Sequence[str],
        project_state: dict[str, Any],
        environment: dict[str, Any],
        data_kind: str,
        cohort_role: str,
    ) -> "RunMetadata":
        return cls(
            run_id=run_id,
            mode=resolved_config["run"]["mode"],
            status=RunStatus.RUNNING,
            started_at=utc_now(),
            resolved_config=resolved_config,
            invocation=tuple(invocation),
            project_state=project_state,
            environment=environment,
            rng_seed=resolved_config["run"]["seed"],
            data_kind=data_kind,
            cohort_role=cohort_role,
        )

    def _finish(self, status: RunStatus, failure: dict[str, str] | None = None) -> None:
        if self.status != RunStatus.RUNNING:
            raise ValueError("a finished run cannot change status; start a new run")
        self.status = status
        self.finished_at = utc_now()
        self.failure = failure

    def mark_completed(self) -> None:
        self._finish(RunStatus.COMPLETED)

    def mark_failed(self, message: str) -> None:
        self._finish(RunStatus.FAILED, {"kind": "error", "message": message})

    def mark_interrupted(self, message: str) -> None:
        self._finish(RunStatus.INTERRUPTED, {"kind": "interrupted", "message": message})

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        # Explicit JSON conversion rejects arrays, arbitrary objects, and NaN.
        return json.loads(json.dumps(value, allow_nan=False))
