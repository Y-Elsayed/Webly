import os
from logging import INFO, FileHandler, Formatter, StreamHandler, getLogger


def configure_logging(module_name: str, log_file: str = "./log/crawler.log"):
    """
    Configures and returns a logger that writes to both console and a log file.
    """
    # Check if the log directory exists and create it if it doesn't
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = getLogger(module_name)
    if not logger.handlers:
        # StreamHandler for console output
        stream_handler = StreamHandler()
        stream_formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        stream_handler.setFormatter(stream_formatter)

        # FileHandler for file output
        file_handler = FileHandler(log_file)
        file_formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)

        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    logger.setLevel(INFO)
    return logger
