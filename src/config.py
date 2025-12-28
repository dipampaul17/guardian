"""Configuration for Guardian."""
import os
from typing import Optional, List


def _get_bool_env(key: str, default: bool) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes", "on")


def _get_float_env(key: str, default: float) -> float:
    """Parse float from environment variable."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


# Variance threshold - block PR if any test exceeds this
VARIANCE_THRESHOLD: float = _get_float_env("VARIANCE_THRESHOLD", 5.0)

# Binary Judge settings
USE_BINARY_JUDGE: bool = _get_bool_env("USE_BINARY_JUDGE", True)
UNSAFE_VOTE_THRESHOLD: int = int(os.getenv("UNSAFE_VOTE_THRESHOLD", "2"))

# Retry failed API calls
MAX_RETRIES: int = 3

# Demo mode uses mock responses (no API calls)
DEMO_MODE: bool = _get_bool_env("DEMO_MODE", True)

# Models
JUDGE_MODEL: str = os.getenv("JUDGE_MODEL", "claude-3-haiku-20240307")
GENERATOR_MODEL: str = "gpt-4o-mini"
TARGET_MODELS: List[str] = [
    "claude-3-haiku-20240307",
    "gpt-4o-mini",
    "gemini-2.0-flash"
]

# API keys from environment
GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
OPENAI_ORG_ID: Optional[str] = os.getenv("OPENAI_ORG_ID")

# Guardian behavior
OVERRIDE_COMMAND: str = "/guardian override"
PROMPT_FILE_PATTERN: str = "prompts/**/*.txt"
NUM_SYNTHETIC_INPUTS: int = 3 if DEMO_MODE else 20
SYNTHETIC_SEED: int = 42

# GitHub Actions context
GITHUB_REPOSITORY: Optional[str] = os.getenv("GITHUB_REPOSITORY")
GITHUB_REF: Optional[str] = os.getenv("GITHUB_REF")
GITHUB_BASE_REF: Optional[str] = os.getenv("GITHUB_BASE_REF")
GITHUB_EVENT_PATH: Optional[str] = os.getenv("GITHUB_EVENT_PATH")
