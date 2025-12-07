import json
import os
import yaml
from pathlib import Path


class AppConfig(dict):
    @property
    def app(self):
        return self["app"]

    @property
    def llm(self):
        return self["llm"]

    @property
    def stt(self):
        return self["stt"]

    @property
    def tts(self):
        return self["tts"]

    @property
    def actions(self):
        return self["actions"]


def load_config(path: str | None = None) -> AppConfig:
    cfg_path = Path(path) if path else None
    if cfg_path is None:
        default_json = Path("config.json")
        cfg_path = default_json if default_json.exists() else Path("config.yaml")

    _load_env_file(Path(".env"))
    loader = _load_json if cfg_path.suffix.lower() == ".json" else _load_yaml
    data = loader(cfg_path)
    data = _apply_env_overrides(data or {})
    return AppConfig(data or {})


def _load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_env_file(path: Path):
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


def _apply_env_overrides(cfg: dict) -> dict:
    porcupine_key = os.getenv("PORCUPINE_ACCESS_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if porcupine_key:
        cfg.setdefault("app", {})["porcupine_access_key"] = porcupine_key
    if gemini_key:
        cfg.setdefault("llm", {})["gemini_api_key"] = gemini_key
    return cfg
