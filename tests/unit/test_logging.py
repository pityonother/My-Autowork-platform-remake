from __future__ import annotations

import logging

from app.shared.logging import get_logger, log_module_event, safe_log_value


def test_safe_log_value_removes_newlines_and_truncates() -> None:
    value = safe_log_value("hello\nworld" + "x" * 300)

    assert "\n" not in value
    assert len(value) == 200


def test_log_module_event_emits_structured_fields(caplog) -> None:
    logger = get_logger("test")

    with caplog.at_level(logging.INFO, logger=logger.name):
        log_module_event(
            logger,
            module="booking",
            action="upload",
            session_id="abc123",
            input_filename="booking.xlsx",
            output_filename="result.xlsx",
            elapsed_ms=15,
        )

    assert "module=booking" in caplog.text
    assert "action=upload" in caplog.text
    assert "session_id=abc123" in caplog.text
    assert "input_filename=booking.xlsx" in caplog.text
    assert "output_filename=result.xlsx" in caplog.text
