import os
from pathlib import Path


def get_app_data_dir(app_name: str = "PythonTrainer") -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / ".local" / "share"
    app_dir = base / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_progress_path() -> Path:
    return get_app_data_dir() / "progress.json"
