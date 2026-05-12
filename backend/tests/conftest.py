from __future__ import annotations

import os
import sys
from pathlib import Path

# Force mock AI in tests — real AI calls belong in tests/integration/
os.environ["AI_PROVIDER"] = "mock"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# On Windows, pytest.exe may pick up a stale venv from a different project.
# Ensure the correct project venv's site-packages comes first.
# Paths are relative to ROOT — no machine-specific hardcoding.
for _sp in [
    ROOT / ".venv" / "Lib" / "site-packages",              # Windows (uv)
    *sorted((ROOT / ".venv" / "lib").glob("*/site-packages")),  # Linux/Mac
]:
    if _sp.exists() and str(_sp) not in sys.path:
        sys.path.insert(1, str(_sp))
        break
