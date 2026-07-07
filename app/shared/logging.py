from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"my_autowork.{name}")


def safe_log_value(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:200]


def log_module_event(
    logger: logging.Logger,
    *,
    module: str,
    action: str,
    session_id: str = "",
    input_filename: str = "",
    output_filename: str = "",
    elapsed_ms: int | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    fields: dict[str, object] = {
        "module": safe_log_value(module),
        "action": safe_log_value(action),
    }
    if session_id:
        fields["session_id"] = safe_log_value(session_id)
    if input_filename:
        fields["input_filename"] = safe_log_value(input_filename)
    if output_filename:
        fields["output_filename"] = safe_log_value(output_filename)
    if elapsed_ms is not None:
        fields["elapsed_ms"] = elapsed_ms
    for key, value in (extra or {}).items():
        fields[safe_log_value(key)] = safe_log_value(value)

    message = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info(message)
