from typing import Dict, Optional

from core.exercises import find_exercise, get_modules, next_position, reload_catalog
from core.progress import (
    allowed_modules,
    get_current_position,
    is_exercise_completed,
    load_progress,
    record_attempt,
    set_current_position,
    validate_current_pointer,
)
from core.validator import validate_user_code


def _pause() -> None:
    input("\nPulsa Enter para continuar...")


def _read_multiline_code(prefill: str) -> str:
    print("\nEscribe tu codigo. Termina con una linea que contenga solo: FIN")
    print("Plantilla sugerida:\n")
    print(prefill)
    lines = []
    while True:
        line = input()
        if line.strip() == "FIN":
            break
        lines.append(line)
    return "\n".join(lines).rstrip()


def _first_pending(modules: list, progress: Dict) -> Optional[Dict]:
    allowed = allowed_modules(modules, progress)
    for module in modules:
        if not allowed.get(module["id"], False):
            break
        for lesson in module["lessons"]:
            for exercise in lesson["exercises"]:
                if not is_exercise_completed(progress, module["id"], lesson["id"], exercise["id"]):
                    item = dict(exercise)
                    item["module_id"] = module["id"]
                    item["lesson_id"] = lesson["id"]
                    return item
    return None


def _current_or_pending(modules: list, progress: Dict) -> Optional[Dict]:
    mod_id, les_id, ex_id = get_current_position(progress)
    allowed = allowed_modules(modules, progress)
    if not allowed.get(mod_id, False):
        return _first_pending(modules, progress)
    try:
        exercise = find_exercise(mod_id, les_id, ex_id)
        if is_exercise_completed(progress, mod_id, les_id, ex_id):
            return _first_pending(modules, progress)
        return exercise
    except Exception:
        return _first_pending(modules, progress)


def _run_exercise(modules: list, exercise: Dict, exam_mode: bool) -> None:
    module = next(m for m in modules if m["id"] == exercise["module_id"])
    lesson = next(l for l in module["lessons"] if l["id"] == exercise["lesson_id"])

    print("\n----------------------------------------")
    print(f"Modulo: {module['title']}  | Leccion: {lesson['title']}")
    print(f"Ejercicio: {exercise['title']}")
    print("----------------------------------------\n")
    if not exam_mode:
        print("Explicacion:")
        for line in lesson.get("explanation", []):
            print("-", line)
        print("\nEjemplo mini:\n" + exercise["example"])
    print("\nEnunciado:\n" + exercise["statement"])

    # Pistas
    if not exam_mode:
        show_hint1 = input("\nQuieres ver la pista 1? (s/n): ").strip().lower() == "s"
        if show_hint1:
            print("Pista 1:", exercise["hints"][0])
        show_hint2 = input("Quieres ver la pista 2? (s/n): ").strip().lower() == "s"
        if show_hint2:
            print("Pista 2:", exercise["hints"][1])
            solution_allowed = True
        else:
            solution_allowed = False
    else:
        solution_allowed = False

    code = _read_multiline_code(exercise["starter_code"])
    if not code:
        print("No escribiste codigo.")
        _pause()
        return

    result = validate_user_code(code, exercise)
    status = result.get("status", "error")
    message = result.get("message", "")
    output = result.get("stdout", "")
    print("\nRESULTADO")
    if status == "ok":
        print("CORRECTO")
    elif status == "fail":
        print("INCORRECTO")
    else:
        print("ERROR")

    if not exam_mode:
        print(message)

    if output:
        print("\nSalida del programa:")
        print(output)

    record_attempt(
        exercise["module_id"],
        exercise["lesson_id"],
        exercise["id"],
        code,
        status == "ok",
        "" if status == "ok" else message,
        mode="examen" if exam_mode else "estudio",
    )

    if status != "ok":
        if not solution_allowed:
            solution_allowed = input("\nMostrar solucion? (s/n, tras fallo): ").strip().lower() == "s"
        if solution_allowed:
            print("\nSOLUCION PROPUESTA:\n")
            print(exercise["solution"])
        print("\nSigue intentando hasta que sea correcto.")
    else:
        print("\nBien hecho. Continua con el siguiente ejercicio.")
        nxt = next_position(modules, exercise["module_id"], exercise["lesson_id"], exercise["id"])
        if nxt:
            set_current_position(load_progress(), *nxt, mode="examen" if exam_mode else "estudio")
    _pause()


def run_app(exam_mode: bool = False) -> None:
    modules = get_modules()

    while True:
        progress = validate_current_pointer(modules, load_progress())
        current = _current_or_pending(modules, progress)

        print("\nPythonTrainer - Modo CLI")
        print("1) Empezar / continuar")
        print("2) Ver progreso")
        print("3) Salir")
        print("4) Recargar catalogo")
        choice = input("\nElige una opcion: ").strip()

        if choice == "1":
            if current is None:
                print("\nTodo completado. Modulos listos.")
                _pause()
                continue
            _run_exercise(modules, current, exam_mode)
        elif choice == "2":
            print("\nPROGRESO")
            for module in modules:
                mod_ok = allowed_modules(modules, progress).get(module["id"], False)
                status_mod = "Desbloqueado" if mod_ok else "Bloqueado"
                print(f"- {module['title']} [{status_mod}]")
                for lesson in module["lessons"]:
                    for exercise in lesson["exercises"]:
                        done = is_exercise_completed(progress, module["id"], lesson["id"], exercise["id"])
                        mark = "OK" if done else "Pendiente"
                        print(f"  * {lesson['title']} - {exercise['title']}: {mark}")
            _pause()
        elif choice == "3":
            return
        elif choice == "4":
            ok = reload_catalog()
            if ok:
                print("\nCatalogo recargado.")
            else:
                print("\nNo se pudo cargar catalogo, usando contenido por defecto.")
            _pause()
        else:
            print("Opcion no valida.")
            _pause()
