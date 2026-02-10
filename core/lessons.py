from core.exercises import MODULES


def get_modules() -> list:
    return MODULES


def get_module(module_id: str) -> dict:
    for module in MODULES:
        if module["id"] == module_id:
            return module
    raise ValueError(f"Modulo no encontrado: {module_id}")


def total_modules() -> int:
    return len(MODULES)
