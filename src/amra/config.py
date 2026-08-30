"""Validated Phase 1 settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMRA_", extra="forbid")

    artifact_root: Path = Path(".amra/artifacts")
    workspace_root: Path = Path(".amra/workspaces")
    cadical_path: Path = Path("build/toolchain/bin/cadical")
    drat_trim_path: Path = Path("build/toolchain/bin/drat-trim")
    cake_lpr_path: Path = Path("build/toolchain/bin/cake_lpr")
    database_url: str = "postgresql+psycopg://amra:amra@localhost:5432/amra"
    api_url: str = "http://127.0.0.1:8000"
    temporal_address: str = "127.0.0.1:7233"
    temporal_task_queue: str = "amra-phase1-sat"
    worker_build_id: str = "amra-phase1-v1"
