"""Run the executable Core 0.2 regressions replacing the historical gap probes.

The 2026-11-12 observations describe the old pushed baseline. This command tests
the corrected contracts using temporary files and deterministic providers.
"""

import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "-q", "tests/test_core_v2.py", "tests/test_evaluation_contract.py"],
            cwd=root,
        )
    )


if __name__ == "__main__":
    main()
