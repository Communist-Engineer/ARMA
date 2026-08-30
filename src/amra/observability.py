"""Structured JSON logging with OpenTelemetry trace correlation."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from opentelemetry import trace


class JsonTraceFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        if span_context.is_valid:
            payload["span_id"] = format(span_context.span_id, "016x")
            payload["trace_id"] = format(span_context.trace_id, "032x")
        for field in (
            "program_id",
            "obligation_id",
            "attempt_id",
            "workflow_id",
            "artifact_digest",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_json_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonTraceFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
