"""Shared configuration, records, and run-provenance foundations."""

from .config import ConfigError, resolve_config
from .metadata import RunMetadata, RunStatus, deterministic_identifier, file_sha256
from .records import (
    AttackManifest,
    DatasetReference,
    DetectorPolicyOutput,
    EventMarker,
    SourceFileReference,
    TrialRecord,
    WindowScore,
    read_trial_record_json,
    write_record_json,
)
from .runs import ExecutionMode, RunLayout

__all__ = [
    "AttackManifest",
    "ConfigError",
    "DatasetReference",
    "DetectorPolicyOutput",
    "EventMarker",
    "ExecutionMode",
    "RunLayout",
    "RunMetadata",
    "RunStatus",
    "SourceFileReference",
    "TrialRecord",
    "WindowScore",
    "deterministic_identifier",
    "file_sha256",
    "read_trial_record_json",
    "resolve_config",
    "write_record_json",
]
