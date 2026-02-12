import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBCREEPER = ROOT / "webcreeper"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WEBCREEPER) not in sys.path:
    sys.path.insert(0, str(WEBCREEPER))
