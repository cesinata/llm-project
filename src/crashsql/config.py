from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_CSV = DATA_DIR / "raw" / "victorian_road_crash_data.csv"
SAMPLE_CSV = DATA_DIR / "sample" / "crashes_sample.csv"
DBT_DIR = ROOT / "dbt"
EVALS_DIR = ROOT / "evals"

CRASH_DATA_URL = (
    "https://discover.data.vic.gov.au/dataset/victoria-road-crash-data/resource/"
    "5df1f373-0c90-48f5-80e1-7b2a35507134/download/victorian_road_crash_data.csv"
)

AGENT_SCHEMA = "marts"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines into the environment without overriding variables already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def warehouse_path() -> Path:
    return Path(os.environ.get("CRASHSQL_DB", DATA_DIR / "warehouse.duckdb"))


@dataclass(frozen=True)
class Provider:
    base_url: str
    api_key_env: str | None
    default_model: str


# All of these expose an OpenAI-compatible chat completions API with tool calling.
PROVIDERS: dict[str, Provider] = {
    "groq": Provider("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "gemini": Provider(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
        "gemini-2.5-flash",
    ),
    "anthropic": Provider("https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY", "claude-haiku-4-5"),
    # qwen2.5-coder's Ollama template emits tool calls as plain text, so use the instruct model.
    "ollama": Provider("http://localhost:11434/v1", None, "qwen2.5:7b"),
}
