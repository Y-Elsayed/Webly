import json
import logging
import os

import pytest

from webly.webcreeper.creeper_core.utils import JsonFormatter, configure_logging


def _make_record(msg: str, level: int = logging.INFO, exc_info=None) -> logging.LogRecord:
    r = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    return r


def test_json_formatter_produces_valid_json():
    fmt = JsonFormatter()
    record = _make_record("hello world")
    output = fmt.format(record)
    data = json.loads(output)
    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert "timestamp" in data


def test_json_formatter_no_exc_info_key_when_no_exception():
    fmt = JsonFormatter()
    record = _make_record("clean message")
    data = json.loads(fmt.format(record))
    assert "exc_info" not in data


def test_json_formatter_includes_exc_info_when_present():
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc = sys.exc_info()
    record = _make_record("error msg", exc_info=exc)
    data = json.loads(fmt.format(record))
    assert "exc_info" in data
    assert "ValueError" in data["exc_info"]


def test_configure_logging_returns_named_logger(tmp_path):
    log_file = str(tmp_path / "test.log")
    logger = configure_logging("test_module_xyz", log_file=log_file)
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module_xyz"


def test_configure_logging_creates_log_dir(tmp_path):
    log_file = str(tmp_path / "subdir" / "app.log")
    configure_logging("test_module_subdir", log_file=log_file)
    assert os.path.exists(os.path.dirname(log_file))


def test_configure_logging_json_output_uses_json_formatter(tmp_path, monkeypatch):
    monkeypatch.delenv("WEBLY_LOG_JSON", raising=False)
    log_file = str(tmp_path / "j.log")
    logger = configure_logging("test_json_mod", log_file=log_file, json_output=True)
    stream_handler = next(h for h in logger.handlers if isinstance(h, logging.StreamHandler)
                          and not isinstance(h, logging.FileHandler))
    assert isinstance(stream_handler.formatter, JsonFormatter)


def test_configure_logging_env_var_enables_json(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBLY_LOG_JSON", "1")
    log_file = str(tmp_path / "env.log")
    logger = configure_logging("test_env_json_mod", log_file=log_file)
    stream_handler = next(h for h in logger.handlers if isinstance(h, logging.StreamHandler)
                          and not isinstance(h, logging.FileHandler))
    assert isinstance(stream_handler.formatter, JsonFormatter)
