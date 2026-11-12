from __future__ import annotations

import json
import logging
import os
from logging import FileHandler, Formatter, StreamHandler, getLogger
from urllib.parse import urlparse

try:
    from webcreeper.agents.atlas.atlas import Atlas as _Atlas
except ImportError as exc:
    raise ImportError(
        "Webly requires the installed 'webcreeper==0.2.0' dependency. "
        "For development, initialize the submodule and run 'python -m pip install ./webcreeper'."
    ) from exc


class Atlas(_Atlas):
    """Compatibility adapter for WebCreeper 0.2.0's authority normalization.

    Its host-comparison helper also strips www/ports and must not be used to
    rewrite the actual fetch destination. Keep upstream query/fragment rules,
    but retain the caller's authority (including IPv6 brackets and userinfo).
    Remove this override once the pinned dependency preserves authorities.
    """

    def _normalize_url(self, url: str) -> str:
        if not url:
            return url
        parsed = urlparse(url)
        # Do not feed an authority to the upstream host-comparison helper: it
        # can produce an unparsable URL for bracketed IPv6 addresses as well.
        normalized = super()._normalize_url(parsed._replace(netloc="").geturl())
        userinfo, separator, authority = parsed.netloc.rpartition("@")
        netloc = (userinfo + separator if separator else "") + authority.lower()
        return urlparse(normalized)._replace(netloc=netloc).geturl()


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
