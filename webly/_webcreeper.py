from __future__ import annotations

import json
import logging
import os
import sys
from logging import FileHandler, Formatter, StreamHandler, getLogger
from pathlib import Path


def _ensure_local_webcreeper_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    webcreeper_root = repo_root / "webcreeper"
    if not webcreeper_root.exists():
        return
    root_str = str(webcreeper_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_ensure_local_webcreeper_path()

try:
    from webcreeper.agents.atlas.atlas import Atlas
except ImportError as exc:
    raise ImportError(
        "Webly requires the sibling 'webcreeper' package. Initialize the submodule and ensure "
        "'webcreeper/' is present, or install the 'webcreeper' package in the environment."
    ) from exc


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    module_name: str,
    log_file: str = "./log/crawler.log",
    json_output: bool = False,
    level: int = logging.INFO,
):
    """
    Webly-owned logging compatibility wrapper.

    `Atlas` and crawler internals come from the external `webcreeper` submodule,
    but Webly keeps its richer logging behavior here so upstream logger API drift
    does not break the app or tests.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = getLogger(module_name)
    if not logger.handlers:
        use_json = json_output or os.environ.get("WEBLY_LOG_JSON", "").lower() == "1"

        stream_handler = StreamHandler()
        stream_handler.setFormatter(
            JsonFormatter() if use_json else Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(stream_handler)

        try:
            file_handler = FileHandler(log_file)
        except OSError:
            file_handler = None
        if file_handler is not None:
            file_handler.setFormatter(Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(file_handler)

    logger.setLevel(level)
    return logger


__all__ = ["Atlas", "JsonFormatter", "configure_logging"]
