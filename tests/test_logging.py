import json
import logging

from stock_agent.core.logging import ContextFilter, JsonFormatter, log_context


def test_json_formatter_includes_context_and_extra_fields():
    logger = logging.getLogger("test.logging.formatter")
    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=10,
        msg="analysis_run_started",
        args=(),
        exc_info=None,
        extra={"event": "analysis_run_started", "status": "SUCCESS"},
    )

    with log_context(run_id="RUN-123", ticker="TCS.NS", provider="yfinance", retry_attempt=2):
        ContextFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))

    assert payload["run_id"] == "RUN-123"
    assert payload["ticker"] == "TCS.NS"
    assert payload["provider"] == "yfinance"
    assert payload["retry_attempt"] == 2
    assert payload["event"] == "analysis_run_started"
    assert payload["status"] == "SUCCESS"
