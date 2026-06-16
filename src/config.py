"""Configuration loader for GeoAnalysis Agent."""
import os
import yaml
from pathlib import Path
from typing import Any, Dict


def _resolve_env(value: str) -> str:
    """Resolve ${ENV_VAR} placeholders in config values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load and resolve YAML configuration. Auto-loads .env file if present."""
    # Load .env into os.environ if dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except Exception:
        pass

    path = Path(config_path)
    if not path.exists():
        # Try parent directory
        path = Path(__file__).parent.parent / config_path
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Resolve env var placeholders recursively
    def resolve(obj):
        if isinstance(obj, dict):
            return {k: resolve(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve(v) for v in obj]
        elif isinstance(obj, str):
            return _resolve_env(obj)
        return obj

    return resolve(config)


def get_llm_config(config: dict) -> dict:
    """Extract LLM configuration for LiteLLMModel."""
    llm = config["llm"]
    return {
        "model_id": llm["model_id"],
        "api_key": llm["api_key"],
        "temperature": llm.get("temperature", 0.1),
        "max_tokens": llm.get("max_tokens", 4096),
    }


def get_db_config(config: dict) -> dict:
    """Extract database configuration."""
    return config["database"]


# Singleton
_config: Dict[str, Any] | None = None


def get_config() -> Dict[str, Any]:
    global _config
    if _config is None:
        _config = load_config()
    return _config
