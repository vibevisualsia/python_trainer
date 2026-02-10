import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("PythonTrainer.catalog")


def _is_valid_catalog(data: Dict) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("version") != 1:
        return False
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        return False
    for module in modules:
        if not isinstance(module, dict):
            return False
        if not isinstance(module.get("id"), str) or not module.get("id"):
            return False
        if not isinstance(module.get("title"), str):
            return False
        lessons = module.get("lessons")
        if not isinstance(lessons, list):
            return False
        for lesson in lessons:
            if not isinstance(lesson, dict):
                return False
            if not isinstance(lesson.get("id"), str) or not lesson.get("id"):
                return False
            if not isinstance(lesson.get("title"), str):
                return False
            exercises = lesson.get("exercises")
            if not isinstance(exercises, list) or not exercises:
                return False
            for exercise in exercises:
                if not isinstance(exercise, dict):
                    return False
                if not isinstance(exercise.get("id"), str) or not exercise.get("id"):
                    return False
                if not isinstance(exercise.get("title"), str):
                    return False
                if "statement" not in exercise:
                    return False
                if "starter_code" not in exercise:
                    return False
                if "checks" not in exercise:
                    return False
    return True


def _infer_var_name(exercise: Dict) -> str:
    checks = exercise.get("checks", [])
    for check in checks:
        var_name = check.get("var")
        if isinstance(var_name, str) and var_name:
            return var_name
    return "resultado"


def _apply_defaults(data: Dict) -> Dict:
    for module in data.get("modules", []):
        module.setdefault("description", "")
        lessons = module.get("lessons", [])
        for lesson in lessons:
            if not isinstance(lesson.get("key_points"), list) or not lesson.get("key_points"):
                lesson["key_points"] = [
                    "Lee el enunciado con calma.",
                    "Usa nombres claros para variables.",
                    "Comprueba el resultado al final.",
                ]
            if not isinstance(lesson.get("explanation"), list) or not lesson.get("explanation"):
                lesson["explanation"] = [
                    "Esta leccion practica un concepto concreto.",
                    "Lee el enunciado y sigue los pasos.",
                    "Si te atascas, usa las pistas.",
                    "Prueba y corrige hasta que pase.",
                ]
            exercises = lesson.get("exercises", [])
            for exercise in exercises:
                if "example" not in exercise:
                    exercise["example"] = exercise.get("starter_code", "")
                hints = exercise.get("hints")
                if not isinstance(hints, list) or len(hints) < 2:
                    var_name = _infer_var_name(exercise)
                    exercise["hints"] = [
                        f"Piensa en la variable '{var_name}'.",
                        "Revisa el enunciado y ajusta tu codigo.",
                    ]
                if "solution" not in exercise:
                    exercise["solution"] = "Solucion no disponible."
    return data


def load_catalog(path: Path) -> Optional[Dict]:
    if not path.exists():
        logger.info("Catalogo no encontrado: %s", str(path))
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        logger.warning("Catalogo JSON invalido: %s", str(path))
        return None
    except Exception:
        logger.exception("Error leyendo catalogo: %s", str(path))
        return None

    if not _is_valid_catalog(data):
        logger.warning("Catalogo invalido (estructura inesperada): %s", str(path))
        return None

    data = _apply_defaults(data)
    logger.info("Catalogo cargado OK: %s", str(path))
    return data
