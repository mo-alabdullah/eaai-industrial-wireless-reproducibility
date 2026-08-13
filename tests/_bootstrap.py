from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "simulation"
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))
