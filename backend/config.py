"""Application paths, catalog limits and environment loading."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = ROOT / "frontend"
MIN_YEAR = 2000
CURRENT_YEAR = 2026


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().replace("_", "").isalnum():
            os.environ.setdefault(name.strip(), value.strip().strip("'\""))


load_env()
