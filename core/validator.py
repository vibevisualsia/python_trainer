"""Exercise validation helpers for safe execution and learner feedback."""

import ast
import io
import math
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, List, Tuple


class ValidationError(Exception):
    """Raised when user code violates safety constraints or syntax rules."""

    pass


def _check_code_is_safe(code: str) -> ast.AST:
    """Parse code and reject unsafe syntax, imports, and blocked builtins."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValidationError(f"Error de sintaxis: {exc.msg} (linea {exc.lineno}, columna {exc.offset}).") from exc

    banned_calls = {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "globals",
        "locals",
        "vars",
        "dir",
        "help",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
    }

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValidationError("No se permiten imports en este ejercicio.")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ValidationError("No se permite usar global/nonlocal.")
        if isinstance(node, ast.Name) and "__" in node.id:
            raise ValidationError("No se permiten nombres con '__' (dunder).")
        if isinstance(node, ast.Attribute) and "__" in node.attr:
            raise ValidationError("No se permiten atributos con '__' (dunder).")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in banned_calls:
                raise ValidationError(f"No se permite llamar a '{node.func.id}'.")


def _safe_builtins() -> dict:
    """Return the limited builtins dictionary exposed to learner exec()."""
    return {
        "abs": abs,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "print": print,
        "range": range,
        "round": round,
        "sum": sum,
        "enumerate": enumerate,
        "str": str,
        "bool": bool,
    }


def _as_list(value: Any, warnings: List[str]) -> Any:
    """Convert iterables to list for comparisons while preserving text types."""
    if isinstance(value, (str, bytes, bytearray)):
        return value
    if isinstance(value, map):
        warnings.append("He convertido tu resultado (map) a lista para comprobarlo.")
        return list(value)
    if hasattr(value, "__iter__") and not isinstance(value, list):
        try:
            return list(value)
        except Exception:
            return value
    return value


def _list_close(got: Any, expected: List[float]) -> Tuple[bool, str, List[str], Dict[str, Any]]:
    """Compare numeric iterables against expected floats using tolerance 1e-6."""
    warnings: List[str] = []
    got = _as_list(got, warnings)
    if isinstance(got, (str, bytes, bytearray)):
        return False, "result no es una lista (es texto).", warnings, {"expected_len": len(expected)}
    try:
        items = list(got)
    except Exception:
        return False, "result debe ser una lista, tupla o iterable.", warnings, {"expected_len": len(expected)}
    if len(items) != len(expected):
        return (
            False,
            f"Tu lista tiene longitud incorrecta (esperado {len(expected)}, obtenido {len(items)}).",
            warnings,
            {"expected_len": len(expected), "got_len": len(items)},
        )
    for a, b in zip(items, expected):
        if not math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-6):
            return (
                False,
                "Los valores no coinciden con tolerancia 1e-6.",
                warnings,
                {"expected_len": len(expected)},
            )
    return True, "Correcto.", warnings, {"expected_len": len(expected)}


def _lint_whitespace(code: str) -> Tuple[bool, str, int, int]:
    """Check indentation tabs and trailing spaces, returning issue position."""
    lines = code.splitlines()
    for idx, line in enumerate(lines, start=1):
        # detect tabs in indentation
        leading = line[: len(line) - len(line.lstrip("\t "))]
        if "\t" in leading:
            col = leading.index("\t") + 1
            return False, f"Usa espacios en lugar de tabs en la linea {idx}.", idx, col
        if line.rstrip() != line:
            return False, f"Quita espacios al final de la linea {idx}.", idx, len(line)
    return True, "", 0, 0


def _run_checks(checks: List[Dict], local_vars: Dict[str, Any], captured_out: str) -> Tuple[bool, str, List[str]]:
    """Run checks using the legacy signature and default exercise metadata."""
    # fallback exercise-wide accepted vars handled in validate_user_code via "exercise" object
    return _run_checks_with_exercise(checks, local_vars, captured_out, {})


def _select_var(var: str, local_vars: Dict[str, Any], exercise: Dict) -> Tuple[str, bool, List[str]]:
    """Return (var_name, found, notes). Allows alternative names in exercise['accepted_vars']."""
    notes: List[str] = []
    if var in local_vars:
        return var, True, notes
    alts = exercise.get("accepted_vars", [])
    for alt in alts:
        if alt in local_vars:
            return alt, True, notes
    if alts:
        notes.append(f"Variables aceptadas: {', '.join(alts + [var])}.")
    return var, False, notes


def _run_checks_with_exercise(checks: List[Dict], local_vars: Dict[str, Any], captured_out: str, exercise: Dict) -> Tuple[bool, str, List[str]]:
    """Run supported check types and produce actionable, learner-friendly feedback."""
    notes: List[str] = []
    output_checks = [c for c in checks if c.get("type") == "output_contains"]
    output_has_expected = False
    for c in output_checks:
        expected_text = str(c.get("expected", ""))
        if expected_text and expected_text in captured_out:
            output_has_expected = True

    for check in checks:
        ctype = check.get("type")
        base_message = check.get("message", "Revisa tu solucion.")
        if ctype == "equals":
            var = check["var"]
            var, found, extra = _select_var(var, local_vars, exercise)
            notes.extend(extra)
            if not found:
                if output_has_expected:
                    return (
                        False,
                        f"El calculo parece correcto, pero el ejercicio exige guardar el resultado en una variable llamada '{var}'.",
                        notes,
                    )
                return False, f"No has creado la variable '{var}'.", notes
            expected = check["expected"]
            if local_vars[var] != expected:
                return False, f"{base_message} (se esperaba {expected!r}).", notes
        elif ctype == "list_close":
            var = check["var"]
            var, found, extra = _select_var(var, local_vars, exercise)
            notes.extend(extra)
            if not found:
                if output_has_expected:
                    return (
                        False,
                        f"El calculo parece correcto, pero el ejercicio exige guardar el resultado en una variable llamada '{var}'.",
                        notes,
                    )
                return False, f"No has creado la variable '{var}'.", notes
            expected = check["expected"]
            if isinstance(local_vars[var], map):
                notes.append("Nota: te falta convertir map a list (usa list(map(...))).")
            ok, msg, warnings, meta = _list_close(local_vars[var], expected)
            notes.extend(warnings)
            if not ok:
                summary = check.get("expected_summary")
                if summary:
                    return False, f"{msg} Se esperaba: {summary}", notes
                expected_len = meta.get("expected_len", len(expected))
                return False, f"{msg} Se esperaba una lista de {expected_len} numeros.", notes
        elif ctype == "output_contains":
            expected = str(check["expected"])
            if expected not in captured_out:
                return False, f"{base_message} (la salida debe contener '{expected}').", notes
        else:
            return False, "Tipo de validacion no soportado.", notes
    return True, "Correcto.", notes


def validate_user_code(code: str, exercise: dict) -> Dict[str, str]:
    """Validate learner code safely and return status, message, output and details."""
    ok_ws, ws_msg, ws_line, ws_col = _lint_whitespace(code)
    if not ok_ws:
        return {
            "status": "fail",
            "message": ws_msg,
            "stdout": "",
            "details": "",
            "lineno": ws_line,
            "offset": ws_col,
        }

    try:
        _check_code_is_safe(code)
    except ValidationError as exc:
        base = {"status": "error", "message": str(exc), "stdout": "", "details": ""}
        if isinstance(exc.__cause__, SyntaxError):
            se = exc.__cause__
            base["lineno"] = se.lineno or 1
            base["offset"] = se.offset or 0
        return base

    globals_dict: Dict[str, Any] = {"__builtins__": _safe_builtins()}
    locals_dict: Dict[str, Any] = {}
    for key, value in exercise.get("setup", {}).items():
        locals_dict[key] = value

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code, globals_dict, locals_dict)
    except Exception as exc:
        tb = traceback.format_exc()
        msg = f"{type(exc).__name__}: {exc}"
        return {
            "status": "error",
            "message": msg,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
            "details": tb,
        }

    output_text = stdout_capture.getvalue()
    stderr_text = stderr_capture.getvalue()
    checks = exercise.get("checks", [])
    if not checks:
        return {
            "status": "error",
            "message": "No hay validaciones definidas.",
            "stdout": output_text,
            "stderr": stderr_text,
            "details": "",
        }

    ok, message, notes = _run_checks_with_exercise(checks, locals_dict, output_text, exercise)
    if ok and "custom_check" in exercise and callable(exercise["custom_check"]):
        try:
            custom_ok, custom_msg = exercise["custom_check"](locals_dict, output_text)
            if not custom_ok:
                return {
                    "status": "fail",
                    "message": custom_msg,
                    "stdout": output_text,
                    "stderr": stderr_text,
                    "details": "",
                }
            if custom_msg:
                message = custom_msg
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error en validador del ejercicio: {exc}",
                "stdout": output_text,
                "stderr": stderr_text,
                "details": traceback.format_exc(),
            }
    if ok:
        if notes:
            message = (message + " " + " ".join(notes)).strip()
        return {"status": "ok", "message": message, "stdout": output_text, "stderr": stderr_text, "details": ""}

    if notes:
        message = (message + " " + " ".join(notes)).strip()
    return {"status": "fail", "message": message, "stdout": output_text, "stderr": stderr_text, "details": ""}
