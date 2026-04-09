import json
import logging
import os
from logging import FileHandler, Formatter, StreamHandler, getLogger


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
    Configures and returns a logger that writes to both console and a log file.

    Set json_output=True (or env var WEBLY_LOG_JSON=1) to emit JSON lines on
    the console stream. The file handler always uses plain text.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = getLogger(module_name)
    if not logger.handlers:
        use_json = json_output or os.environ.get("WEBLY_LOG_JSON", "").lower() == "1"

        stream_handler = StreamHandler()
        stream_handler.setFormatter(
            JsonFormatter() if use_json
            else Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        logger.addHandler(stream_handler)
        try:
            file_handler = FileHandler(log_file)
        except OSError:
            file_handler = None
        if file_handler is not None:
            file_handler.setFormatter(
                Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            logger.addHandler(file_handler)

    logger.setLevel(level)
    return logger
