import os
from pathlib import Path

os.environ["MACPAD_CONFIG"] = str(Path(__file__).parent / "fixtures" / "mapping.yaml")
