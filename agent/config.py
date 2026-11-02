"""Settings: reads the .env file and decides which AI model and which mode to use.

provider = "mock"  -> offline rule-based practice model (no key, no internet, NOT for final submission numbers)
provider = "api"   -> a real LLM through an OpenAI-compatible API (needs LLM_API_KEY in .env)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Tiny .env reader so beginners do not need an extra package."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    provider: str
    api_key: str
    base_url: str
    model: str
    security_enabled: bool          # False = Assignment 1 mode, True = Assignment 2 mode
    runtime_dir: Path               # where memory, logs, tickets, approvals are written
    max_tool_rounds: int = 5        # stop the agent loop after this many model calls


def get_settings(security_enabled: bool, provider: str | None = None,
                 runtime_dir: Path | None = None) -> Settings:
    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    chosen = (provider or os.environ.get("LLM_PROVIDER", "")).strip().lower()
    if not chosen:
        chosen = "api" if api_key else "mock"
    if runtime_dir is None:
        name = "assignment2" if security_enabled else "assignment1"
        runtime_dir = ROOT / "runtime" / name
    return Settings(
        provider=chosen,
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL", "").strip(),
        model=os.environ.get("LLM_MODEL", "").strip(),
        security_enabled=security_enabled,
        runtime_dir=Path(runtime_dir),
    )
