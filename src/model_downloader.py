from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional


def ensure_models(config) -> None:
    _ensure_llm(config)
    _ensure_tts(config)
    _ensure_stt(config)


def _ensure_llm(config):
    path = Path(config.llm.get("model_path", ""))
    if path.exists():
        return
    repo = config.llm.get("hf_repo", "").strip()
    filename = config.llm.get("hf_file", "").strip()
    rev = config.llm.get("hf_revision", "").strip() or None
    if repo and filename:
        _hf_download_file(repo, filename, path, revision=rev, label="LLM")
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el modelo LLM en {path}. Revisa hf_repo/hf_file o descarga manualmente."
        )


def _ensure_tts(config):
    path = Path(config.tts.get("voice_path", ""))
    json_path = path.with_suffix(path.suffix + ".json")
    if path.exists() and json_path.exists():
        return
    repo = config.tts.get("hf_repo", "").strip()
    filename = config.tts.get("hf_file", "").strip()
    rev = config.tts.get("hf_revision", "").strip() or None
    if repo and filename:
        _hf_download_file(repo, filename, path, revision=rev, label="TTS")
        _hf_download_file(repo, filename + ".json", json_path, revision=rev, label="TTS config")
    if not path.exists() or not json_path.exists():
        raise FileNotFoundError(
            f"No se encontró el modelo TTS en {path} o {json_path}. Revisa tts.hf_repo/tts.hf_file o descarga manualmente."
        )


def _ensure_stt(config):
    path = Path(config.stt.get("model_path", ""))
    if path.exists():
        return
    repo = config.stt.get("hf_repo", "").strip()
    rev = config.stt.get("hf_revision", "").strip() or None
    if repo:
        _hf_snapshot(repo, path, revision=rev, label="STT")
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el modelo STT en {path}. Revisa stt.hf_repo o descarga manualmente."
        )


def _hf_download_file(repo_id: str, filename: str, dest: Path, revision: Optional[str], label: str = ""):
    try:
        from huggingface_hub import hf_hub_download
    except Exception as e:
        print(f"[Download] {label} requiere huggingface_hub ({e})")
        return

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(hf_hub_download(repo_id=repo_id, filename=filename, revision=revision, repo_type="model"))
        shutil.copyfile(tmp, dest)
        print(f"[Download] {label} -> {dest}")
    except Exception as e:
        print(f"[Download] Falló {label} desde HF: {e}")


def _hf_snapshot(repo_id: str, dest_dir: Path, revision: Optional[str], label: str = ""):
    try:
        from huggingface_hub import snapshot_download
    except Exception as e:
        print(f"[Download] {label} requiere huggingface_hub ({e})")
        return

    try:
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            repo_type="model",
            local_dir=dest_dir,
            local_dir_use_symlinks=False,
        )
        print(f"[Download] {label} -> {dest_dir}")
    except Exception as e:
        print(f"[Download] Falló {label} snapshot HF: {e}")
