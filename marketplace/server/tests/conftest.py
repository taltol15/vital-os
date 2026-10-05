import os
import sys
from pathlib import Path

os.environ["VITAL_MARKET_TESTING"] = "1"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "python"))
