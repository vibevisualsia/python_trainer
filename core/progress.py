import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, List

from core.app_paths import get_progress_path

logger = logging.getLogger("PythonTrainer.progress")


def _template_progress_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent  # python_trainer/
    return base_dir / "data" / "progress.json"


def ensure_progress_file_exists() -> Path:
    path = get_progress_path()
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)

    if path.exists():
        return path

    template_path = _template_progress_path()
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _empty_data()

    _atomic_save(path, data)
    return path


def _empty_data() -> Dict:
    return {
        "exercises": {},
        "current": {
            "module_id": "module1",
            "lesson_id": "m1_l1",
            "exercise_id": "m1_l1_e1",
            "mode": "estudio",
        },
    }


def _atomic_save(path: Path, data: Dict) -> None:
    folder = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(folder), prefix="progress_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        logger.exception("Fallo guardando progreso (escritura atomica).")
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def load_progress() -> Dict:
    path = ensure_progress_file_exists()
    logger.info("Cargando progreso: %s", str(path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("Fallo leyendo progreso; usando valores por defecto.")
        data = _empty_data()
    if "exercises" not in data or not isinstance(data["exercises"], dict):
        data["exercises"] = {}
    if "current" not in data or not isinstance(data["current"], dict):
        data["current"] = _empty_data()["current"]
    return data


def save_progress(data: Dict) -> None:
    path = ensure_progress_file_exists()
    logger.info("Guardando progreso: %s", str(path))
    _atomic_save(path, data)


def _exercise_key(module_id: str, lesson_id: str, exercise_id: str) -> str:
    return f"{module_id}:{lesson_id}:{exercise_id}"


def record_attempt(module_id: str, lesson_id: str, exercise_id: str, code: str, ok: bool, error: str, mode: str = "estudio", duration_s: Optional[float] = None) -> Dict:
    data = load_progress()
    key = _exercise_key(module_id, lesson_id, exercise_id)
    now = datetime.now(timezone.utc).isoformat()
    record = data["exercises"].get(
        key,
        {
            "module_id": module_id,
            "lesson_id": lesson_id,
            "exercise_id": exercise_id,
            "attempts": 0,
            "created_at": now,
        },
    )

    record["attempts"] = int(record.get("attempts", 0)) + 1
    record["completed"] = bool(ok)
    record["last_code"] = code
    record["last_error"] = "" if ok else error
    record["updated_at"] = now
    record["mode"] = mode
    if duration_s is not None:
        record["last_duration_s"] = float(duration_s)

    data["exercises"][key] = record
    data["current"] = {
        "module_id": module_id,
        "lesson_id": lesson_id,
        "exercise_id": exercise_id,
        "mode": mode,
    }
    save_progress(data)
    return record


def get_record(progress: Dict, module_id: str, lesson_id: str, exercise_id: str) -> Optional[Dict]:
    key = _exercise_key(module_id, lesson_id, exercise_id)
    return progress.get("exercises", {}).get(key)


def is_exercise_completed(progress: Dict, module_id: str, lesson_id: str, exercise_id: str) -> bool:
    record = get_record(progress, module_id, lesson_id, exercise_id)
    return bool(record and record.get("completed") is True)


def module_completed(progress: Dict, module: Dict) -> bool:
    for lesson in module["lessons"]:
        for exercise in lesson["exercises"]:
            if not is_exercise_completed(progress, module["id"], lesson["id"], exercise["id"]):
                return False
    return True


def allowed_modules(modules: list, progress: Dict) -> Dict[str, bool]:
    allowed = {}
    for index, module in enumerate(modules):
        if index == 0:
            allowed[module["id"]] = True
        else:
            prev = modules[index - 1]
            allowed[module["id"]] = module_completed(progress, prev)
    return allowed


def get_current_position(progress: Dict) -> Tuple[str, str, str]:
    cur = progress.get("current") or {}
    return (
        cur.get("module_id", "module1"),
        cur.get("lesson_id", "m1_l1"),
        cur.get("exercise_id", "m1_l1_e1"),
    )


def set_current_position(progress: Dict, module_id: str, lesson_id: str, exercise_id: str, mode: Optional[str] = None) -> Dict:
    progress = dict(progress)
    progress["current"] = {
        "module_id": module_id,
        "lesson_id": lesson_id,
        "exercise_id": exercise_id,
        "mode": mode or progress.get("current", {}).get("mode", "estudio"),
    }
    save_progress(progress)
    return progress


def validate_current_pointer(modules: List[Dict], progress: Dict) -> Dict:
    cur_mod, cur_les, cur_ex = get_current_position(progress)

    def first_available() -> Tuple[str, str, str]:
        first_module = modules[0]
        first_lesson = first_module["lessons"][0]
        first_ex = first_lesson["exercises"][0]
        return first_module["id"], first_lesson["id"], first_ex["id"]

    # corrige modulo
    module = next((m for m in modules if m["id"] == cur_mod), None)
    if module is None:
        cur_mod, cur_les, cur_ex = first_available()
    else:
        lesson = next((l for l in module["lessons"] if l["id"] == cur_les), None)
        if lesson is None:
            cur_les = module["lessons"][0]["id"]
            cur_ex = module["lessons"][0]["exercises"][0]["id"]
        else:
            exercise = next((e for e in lesson["exercises"] if e["id"] == cur_ex), None)
            if exercise is None:
                cur_ex = lesson["exercises"][0]["id"]

    return set_current_position(progress, cur_mod, cur_les, cur_ex, progress.get("current", {}).get("mode", "estudio"))


def reset_module_progress(modules: List[Dict], module_id: str, progress: Optional[Dict] = None) -> Dict:
    data = progress or load_progress()
    # remove attempts for module
    new_ex = {}
    for key, rec in data.get("exercises", {}).items():
        if rec.get("module_id") != module_id:
            new_ex[key] = rec
    data["exercises"] = new_ex

    module = next((m for m in modules if m["id"] == module_id), None)
    if module:
        first_lesson = module["lessons"][0]
        first_ex = first_lesson["exercises"][0]
        data = set_current_position(data, module_id, first_lesson["id"], first_ex["id"], data.get("current", {}).get("mode", "estudio"))
    else:
        data = validate_current_pointer(modules, data)
    return data
