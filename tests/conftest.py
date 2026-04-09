import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEBCREEPER_ROOT = ROOT / "webcreeper"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if WEBCREEPER_ROOT.exists() and str(WEBCREEPER_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBCREEPER_ROOT))


@pytest.fixture(autouse=True)
def patch_webcreeper_test_logging(monkeypatch):
    try:
        import webcreeper.creeper_core.base_agent as base_agent_module
    except ImportError:
        return

    def _test_logger(module_name: str, *_args, **_kwargs):
        logger = logging.getLogger(f"test.{module_name}")
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
        return logger

    monkeypatch.setattr(base_agent_module, "configure_logging", _test_logger)
