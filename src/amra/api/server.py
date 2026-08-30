"""ASGI application factory for uvicorn and containers."""

from amra.adapters.artifacts.local import LocalArtifactStore
from amra.adapters.clock import SystemClock
from amra.api.app import create_app
from amra.config import Settings
from amra.observability import configure_json_logging

settings = Settings()
configure_json_logging()
app = create_app(
    LocalArtifactStore(settings.artifact_root, SystemClock()),
    tool_paths=(settings.cadical_path, settings.drat_trim_path, settings.cake_lpr_path),
)
