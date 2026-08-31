"""Separated practice and staged/completed experimental run locations."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .metadata import RunStatus


class ExecutionMode(str, Enum):
    PRACTICE = "practice"
    EXPERIMENTAL = "experimental"


def new_run_id(prefix: str = "run") -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", prefix):
        raise ValueError("run ID prefix contains unsupported characters")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id):
        raise ValueError("run ID must contain only letters, digits, dot, underscore, and hyphen")


def _resolve_relative(root: Path, value: str | Path) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError("run locations must be repository-relative")
    destination = (root / relative).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("run location escapes the repository root")
    return destination


@dataclass(frozen=True, slots=True)
class RunLayout:
    repo_root: Path
    practice_root: Path
    experimental_staging_root: Path
    experimental_completed_root: Path

    @classmethod
    def from_config(cls, repo_root: str | Path, paths: dict[str, str]) -> "RunLayout":
        root = Path(repo_root).resolve()
        return cls(
            repo_root=root,
            practice_root=_resolve_relative(root, paths["practice"]),
            experimental_staging_root=_resolve_relative(root, paths["experimental_staging"]),
            experimental_completed_root=_resolve_relative(root, paths["experimental_completed"]),
        )

    def create_practice(self, run_id: str | None = None) -> Path:
        identifier = new_run_id("practice") if run_id is None else run_id
        return self._create_unique(self.practice_root, identifier)

    def create_experimental_staging(self, run_id: str | None = None) -> Path:
        identifier = new_run_id("experiment") if run_id is None else run_id
        if (self.experimental_completed_root / identifier).exists():
            raise FileExistsError(f"completed experimental run already exists: {identifier}")
        return self._create_unique(self.experimental_staging_root, identifier)

    def finalize_experimental(self, staging_path: str | Path, status: RunStatus) -> Path:
        source = Path(staging_path).resolve()
        if source.parent != self.experimental_staging_root:
            raise ValueError("only a direct experimental staging run can be finalized")
        if status is not RunStatus.COMPLETED:
            raise ValueError("only an explicitly completed run can enter experimental results")
        if not source.is_dir():
            raise FileNotFoundError(f"experimental staging run does not exist: {source}")
        metadata_path = source / "run_metadata.json"
        if not metadata_path.is_file():
            raise ValueError("experimental staging run has no run_metadata.json")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("experimental run metadata is not readable JSON") from error
        if metadata.get("run_id") != source.name:
            raise ValueError("experimental run metadata ID does not match its staging path")
        if metadata.get("status") != RunStatus.COMPLETED.value:
            raise ValueError("experimental run metadata is not marked completed")
        destination = self.experimental_completed_root / source.name
        if destination.exists():
            raise FileExistsError(f"completed experimental run already exists: {source.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return destination

    @staticmethod
    def _create_unique(parent: Path, run_id: str) -> Path:
        _validate_run_id(run_id)
        destination = parent / run_id
        destination.mkdir(parents=True, exist_ok=False)
        return destination
