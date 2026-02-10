import logging
from logging.handlers import RotatingFileHandler

from core.app_paths import get_app_data_dir


def setup_logging(app_name: str = "PythonTrainer") -> None:
    root = logging.getLogger()
    if getattr(root, "_python_trainer_configured", False):
        return

    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    try:
        log_path = get_app_data_dir(app_name) / "app.log"
        file_handler = RotatingFileHandler(
            str(log_path), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception:
        # Logging must not break the app.
        pass

    root._python_trainer_configured = True
