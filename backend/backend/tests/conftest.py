from __future__ import annotations

import os
import sys
from pathlib import Path

# Force mock AI in tests — real AI calls belong in tests/integration/
os.environ["AI_PROVIDER"] = "mock"
# Force mock vision in tests — prevents factory from picking up .env VISION_PROVIDER
os.environ["VISION_PROVIDER"] = "mock"
os.environ["IMAGE_EXTRACT_MODE"] = "vision"
os.environ["VISION_IMAGE_MAX_SIDE"] = "720"
os.environ["VISION_IMAGE_JPEG_QUALITY"] = "70"
os.environ["IMAGE_EXTRACT_TIMEOUT_SECONDS"] = "120"
os.environ["IMAGE_EXTRACT_CACHE_TTL_SECONDS"] = "3600"
os.environ["DEBUG_AI_EXTRACT"] = "false"
# Force non-production so internal_images router guard behaves correctly in tests
os.environ.setdefault("APP_ENV", "testing")
# Mark as testing environment so rate limiters fail-open even when Redis is up
os.environ["APP_ENV"] = "testing"
# Keep auth tests code-scoped unless a test explicitly enables fixed mock login.
os.environ["WECHAT_MOCK_OPENID"] = ""

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
