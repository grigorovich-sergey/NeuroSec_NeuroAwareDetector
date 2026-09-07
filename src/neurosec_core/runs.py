"""Single-writer practice/study lifecycle, with verified finalization."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from .metadata import METADATA_PATH, RunMetadata, RunStatus, inventory_files


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id):
        raise ValueError("run ID must start with a letter/digit and use only letters, digits, ._-")


def new_run_id(prefix: str = "run") -> str:
    _validate_run_id(prefix)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _relative_file(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("artifact name must be a relative POSIX path")
    path = PurePosixPath(name)
    if (
        not name or path.is_absolute() or ".." in path.parts or "\\" in name
        or path.as_posix() != name or name == "."
    ):
        raise ValueError(f"invalid artifact name: {name!r}")
    return name


@dataclass(frozen=True, slots=True)
class RunLayout:
    repo_root: Path
    smoke_root: Path
    pilot_root: Path
    study_staging_root: Path
    study_root: Path

    @classmethod
    def from_config(cls, repo_root: str | Path, paths: Mapping[str, str]) -> "RunLayout":
        root = Path(repo_root).resolve()
        keys = ("smoke", "pilot", "study_staging", "study")
        if set(paths) != set(keys):
            raise ValueError(f"paths must contain exactly {', '.join(keys)}")
        resolved = {}
        for name in keys:
            value = Path(paths[name])
            destination = (root / value).resolve()
            boundary = root / "outputs" / name
            if value.is_absolute() or not destination.is_relative_to(boundary):
                raise ValueError(f"paths.{name} must remain under outputs/{name}")
            resolved[name] = destination
        # Fixed, disjoint boundaries keep all practice and staging writes ignored.
        return cls(root, *(resolved[name] for name in keys))

    def _mode_for(self, run_path: str | Path) -> tuple[Path, str]:
        source = Path(run_path)
        if source.is_symlink():
            raise ValueError("run directory must not be a symlink")
        source = source.resolve()
        if source.parent in (self.smoke_root, self.pilot_root):
            mode = "practice"
        elif source.parent == self.study_staging_root:
            mode = "experimental"
        else:
            raise ValueError("writes require a direct smoke, pilot, or study_staging run")
        _validate_run_id(source.name)
        if not source.is_dir():
            raise FileNotFoundError(source)
        return source, mode

    def create_practice(self, kind: str, run_id: str | None = None) -> Path:
        if kind not in ("smoke", "pilot"):
            raise ValueError("practice kind must be smoke or pilot")
        return self._create_unique(
            self.smoke_root if kind == "smoke" else self.pilot_root,
            new_run_id(kind) if run_id is None else run_id,
        )

    def create_experimental_staging(self, run_id: str | None = None) -> Path:
        identifier = new_run_id("study") if run_id is None else run_id
        _validate_run_id(identifier)
        destination = self.study_root / identifier
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"completed run already exists: {identifier}")
        return self._create_unique(self.study_staging_root, identifier)

    def write_metadata(self, run_path: str | Path, metadata: RunMetadata) -> Path:
        """Write a running/terminal snapshot only in practice or staging."""
        source, mode = self._mode_for(run_path)
        if metadata.run_id != source.name or metadata.mode != mode:
            raise ValueError("metadata ID/mode must match its run directory")
        destination = source / METADATA_PATH
        # Inventory first also rejects symlinked metadata or parent directories.
        metadata.generated_files = inventory_files(source)
        if destination.exists():
            previous = json.loads(destination.read_text(encoding="utf-8"))
            if previous.get("status") != RunStatus.RUNNING.value:
                raise ValueError("finished metadata cannot be overwritten; start a new run")
        # Revalidate the snapshot so mutation since construction cannot change its contract.
        payload = json.dumps(
            RunMetadata.from_dict(metadata.to_dict()).to_dict(),
            indent=2, sort_keys=True, allow_nan=False
        ) + "\n"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".json.tmp")
        # An interrupted metadata write is an error to inspect, not silently erase.
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(payload)
        temporary.replace(destination)
        return destination

    def finalize_experimental(
        self, staging_path: str | Path, *, required_files: Sequence[str]
    ) -> Path:
        """Verify all bytes and the runner's required outputs before one rename.

        This is an artifact-integrity gate. Scientific schema/content validation
        and study approval remain responsibilities of the component/gate owners.
        """
        source, mode = self._mode_for(staging_path)
        if mode != "experimental":
            raise ValueError("only experimental staging can be finalized")
        if isinstance(required_files, str) or not required_files:
            raise ValueError("the runner must declare nonempty required_files")
        required = {_relative_file(name) for name in required_files}
        actual = inventory_files(source)
        try:
            metadata = json.loads((source / METADATA_PATH).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"missing or unreadable {METADATA_PATH}") from error
        record = RunMetadata.from_dict(metadata)
        if record.run_id != source.name or record.mode != "experimental":
            raise ValueError("metadata ID/mode must match experimental staging")
        if record.status != RunStatus.COMPLETED or not record.finished_at or record.failure:
            raise ValueError("run metadata is not marked completed with a finish time")
        if record.data_kind != "real" or record.cohort_role != "report":
            raise ValueError("only real report-cohort runs can enter completed study output")
        if not record.project_state.get("commit") or not record.environment.get("python"):
            raise ValueError("completed runs require recorded Git and Python identities")
        recorded = record.generated_files
        if not isinstance(recorded, list) or json.dumps(recorded, sort_keys=True) != json.dumps(actual, sort_keys=True):
            raise ValueError("file inventory does not match current artifacts (name/size/SHA-256)")
        if not required.issubset({item["name"] for item in actual}):
            raise ValueError("required output files are missing from the verified inventory")
        destination = self.study_root / source.name
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"completed run already exists: {source.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return destination

    @staticmethod
    def _create_unique(parent: Path, run_id: str) -> Path:
        _validate_run_id(run_id)
        destination = parent / run_id
        destination.mkdir(parents=True, exist_ok=False)
        return destination
