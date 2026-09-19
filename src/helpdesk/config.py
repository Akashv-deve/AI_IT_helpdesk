"""Central configuration.

Every tunable value lives here and can be overridden with an environment
variable or a ``.env`` file, so nothing important is hard-coded in the
middle of the application logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repository root = three levels up from this file (src/helpdesk/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def _env_str(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env_str(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env_str(key, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    """Application settings.

    Deliberately *not* frozen. Every module imports the same ``settings``
    instance, so a test (or a future CLI flag) can redirect ``db_path`` or
    ``escalation_threshold`` on that one object and have the whole application
    follow, without threading a config argument through every function.
    """

    # --- Local LLM (Ollama) ---
    ollama_model: str = _env_str("OLLAMA_MODEL", "qwen2.5:3b")
    ollama_base_url: str = _env_str("OLLAMA_BASE_URL", "http://localhost:11434")
    llm_temperature: float = _env_float("LLM_TEMPERATURE", 0.1)
    llm_max_tokens: int = _env_int("LLM_MAX_TOKENS", 512)
    llm_timeout_seconds: int = _env_int("LLM_TIMEOUT_SECONDS", 120)

    # --- Data locations ---
    kb_path: Path = PROJECT_ROOT / _env_str("KB_PATH", "data/helpdesk_kb.json")
    db_path: Path = PROJECT_ROOT / _env_str("DB_PATH", "data/helpdesk.db")

    # --- Retrieval / routing behaviour ---
    kb_top_k: int = _env_int("KB_TOP_K", 3)
    escalation_threshold: float = _env_float("ESCALATION_THRESHOLD", 0.35)

    @property
    def offline_forced(self) -> bool:
        """True when the user has explicitly asked to skip Ollama entirely."""
        return _env_str("HELPDESK_OFFLINE", "0").lower() in ("1", "true", "yes")


settings = Settings()
