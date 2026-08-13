"""Typed isolated-process execution port."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    cpu_seconds: int = 60
    wall_seconds: float = 60.0
    memory_bytes: int = 512 * 1024 * 1024
    output_bytes: int = 16 * 1024 * 1024
    process_count: int = 32
    file_size_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: bytes
    stderr: bytes
    wall_time_seconds: float
    peak_memory_bytes: int | None


class ExecutionPort(Protocol):
    def execute(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        limits: ResourceLimits,
        environment: Mapping[str, str] | None = None,
    ) -> ProcessResult: ...
