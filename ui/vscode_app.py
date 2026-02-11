from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    import webview  # type: ignore
except Exception:
    webview = None

from core.exercises import find_exercise, get_modules
from core.progress import get_current_position, get_record, load_progress, save_progress
from core.runner import run_user_code
from core.validator import validate_user_code


def _tool_available(tool_name: str) -> bool:
    return shutil.which(tool_name) is not None


def _tool_version(tool_name: str) -> str:
    if not _tool_available(tool_name):
        return ""
    try:
        completed = subprocess.run(
            [tool_name, "--version"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except Exception:
        return ""
    version_text = (completed.stdout or completed.stderr or "").strip()
    return version_text.splitlines()[0] if version_text else ""


def _available_map() -> Dict[str, bool]:
    return {
        "ruff": _tool_available("ruff"),
        "pyright": _tool_available("pyright"),
    }


def _safe_line(value: Any, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except Exception:
        return default


def _safe_col(value: Any, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except Exception:
        return default


def _parse_ruff_output(stdout: str) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    if not stdout.strip():
        return diagnostics
    try:
        issues = json.loads(stdout)
    except Exception:
        return diagnostics

    if not isinstance(issues, list):
        return diagnostics

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        location = issue.get("location", {}) or {}
        end_location = issue.get("end_location", {}) or {}
        code = str(issue.get("code", "")).strip()
        message = str(issue.get("message", "")).strip()
        if not message:
            continue
        diagnostics.append(
            {
                "source": "ruff",
                "severity": str(issue.get("severity", "warning")).lower(),
                "code": code,
                "message": message,
                "startLineNumber": _safe_line(location.get("row", 1)),
                "startColumn": _safe_col(location.get("column", 1)),
                "endLineNumber": _safe_line(end_location.get("row", location.get("row", 1))),
                "endColumn": _safe_col(end_location.get("column", location.get("column", 2))),
            }
        )
    return diagnostics


def _parse_pyright_output(stdout: str) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    if not stdout.strip():
        return diagnostics
    try:
        payload = json.loads(stdout)
    except Exception:
        return diagnostics

    items = payload.get("generalDiagnostics", [])
    if not isinstance(items, list):
        return diagnostics

    for issue in items:
        if not isinstance(issue, dict):
            continue
        message = str(issue.get("message", "")).strip()
        if not message:
            continue
        rng = issue.get("range", {}) or {}
        start = rng.get("start", {}) or {}
        end = rng.get("end", {}) or {}
        severity = str(issue.get("severity", "warning")).lower()
        if severity not in {"error", "warning", "info", "hint"}:
            severity = "warning"
        diagnostics.append(
            {
                "source": "pyright",
                "severity": severity,
                "code": str(issue.get("rule", "")).strip(),
                "message": message,
                "startLineNumber": _safe_line(start.get("line", 0) + 1),
                "startColumn": _safe_col(start.get("character", 0) + 1),
                "endLineNumber": _safe_line(end.get("line", start.get("line", 0)) + 1),
                "endColumn": _safe_col(end.get("character", start.get("character", 0) + 1) + 1),
            }
        )
    return diagnostics


def _write_temp_code(code: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(code)
        return Path(handle.name)


def _unique_rule_codes(issues: List[Dict[str, Any]]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for issue in issues:
        code = str(issue.get("code", "")).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return ordered


def _changed_lines_count(before_code: str, after_code: str) -> int:
    before_lines = before_code.splitlines()
    after_lines = after_code.splitlines()
    sequence = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    changed = 0
    for tag, i1, i2, j1, j2 in sequence.get_opcodes():
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
    return changed


class VscodeApi:
    def _current_position(self) -> tuple[str, str, str]:
        progress = load_progress()
        return get_current_position(progress)

    def _current_exercise(self) -> Dict[str, Any]:
        module_id, lesson_id, exercise_id = self._current_position()
        try:
            return find_exercise(module_id, lesson_id, exercise_id)
        except Exception:
            first_module = get_modules()[0]
            first_lesson = first_module["lessons"][0]
            first_exercise = first_lesson["exercises"][0]
            return find_exercise(first_module["id"], first_lesson["id"], first_exercise["id"])

    def _study_hint(self, code: str, result: Dict[str, Any]) -> str:
        lowered = code.lower()
        status = str(result.get("status", "")).lower()
        joined_errors = (str(result.get("stderr", "")) + "\n" + str(result.get("message", ""))).lower()

        if status == "timeout":
            if "while true" in lowered or "while 1" in lowered:
                return "Pista: parece que hay un bucle infinito. Revisa while True y agrega una condicion de salida."
            if "sleep(" in lowered:
                return "Pista: sleep puede retrasar la ejecucion. Reduce el tiempo de espera."
            return "Pista: la ejecucion tardo demasiado. Revisa bucles o esperas largas."

        if "zerodivisionerror" in joined_errors or "/0" in lowered or "/ 0" in lowered:
            return "Pista: revisa divisiones entre cero antes de ejecutar el calculo."

        if any(name in lowered for name in ["total =", "suma =", "resultado ="]) and "print(" not in lowered:
            return "Pista: has calculado un valor, pero falta mostrarlo con print()."

        return ""

    def load_initial_code(self) -> str:
        exercise = self._current_exercise()
        module_id = exercise.get("module_id", "")
        lesson_id = exercise.get("lesson_id", "")
        exercise_id = exercise.get("id", "")
        progress = load_progress()
        record = get_record(progress, module_id, lesson_id, exercise_id)
        if record and isinstance(record.get("last_code"), str) and record.get("last_code"):
            return str(record["last_code"])
        return str(exercise.get("starter_code", ""))

    def save_code(self, code: str) -> Dict[str, Any]:
        try:
            exercise = self._current_exercise()
            module_id = exercise.get("module_id", "")
            lesson_id = exercise.get("lesson_id", "")
            exercise_id = exercise.get("id", "")
            progress = load_progress()
            key = f"{module_id}:{lesson_id}:{exercise_id}"
            exercises = progress.setdefault("exercises", {})
            record = exercises.get(
                key,
                {
                    "module_id": module_id,
                    "lesson_id": lesson_id,
                    "exercise_id": exercise_id,
                    "attempts": 0,
                    "completed": False,
                },
            )
            record["last_code"] = code
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            exercises[key] = record
            save_progress(progress)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def run_code(self, code: str, mode: str = "study") -> Dict[str, Any]:
        current_mode = "exam" if str(mode).lower() == "exam" else "study"
        exercise = self._current_exercise()
        run_result = run_user_code(code, setup=exercise.get("setup", {}))

        payload: Dict[str, Any] = {
            "status": run_result.get("status", "error"),
            "stdout": run_result.get("stdout", ""),
            "stderr": run_result.get("stderr", ""),
            "message": run_result.get("message", ""),
            "warnings": run_result.get("warnings", []),
            "hint": "",
        }

        if current_mode == "study":
            payload["hint"] = self._study_hint(code, payload)
        return payload

    def check_code(self, code: str, mode: str = "study") -> Dict[str, Any]:
        current_mode = "exam" if str(mode).lower() == "exam" else "study"
        exercise = self._current_exercise()
        run_result = run_user_code(code, setup=exercise.get("setup", {}))

        payload: Dict[str, Any] = {
            "status": run_result.get("status", "error"),
            "stdout": run_result.get("stdout", ""),
            "stderr": run_result.get("stderr", ""),
            "message": run_result.get("message", ""),
            "warnings": run_result.get("warnings", []),
            "hint": "",
        }

        if payload["status"] == "ok":
            validation = validate_user_code(code, exercise)
            payload["status"] = validation.get("status", "error")
            payload["message"] = validation.get("message", payload["message"])
            payload["stdout"] = validation.get("stdout", payload["stdout"])
            payload["stderr"] = validation.get("stderr", payload["stderr"])
            if validation.get("details"):
                payload["stderr"] = (payload["stderr"] + "\n" + validation["details"]).strip()

        if current_mode == "study":
            payload["hint"] = self._study_hint(code, payload)
        return payload

    def api_capabilities(self) -> Dict[str, Any]:
        available = _available_map()
        versions = {
            "ruff": _tool_version("ruff") if available["ruff"] else "",
            "pyright": _tool_version("pyright") if available["pyright"] else "",
        }
        return {
            "ok": True,
            "available": available,
            "versions": versions,
        }

    def lint_code(self, code: str) -> Dict[str, Any]:
        available = _available_map()
        if not available["ruff"]:
            return {
                "ok": False,
                "diagnostics": [],
                "message": "ruff no instalado",
                "available": available,
            }

        tmp_file = _write_temp_code(code)
        try:
            completed = subprocess.run(
                ["ruff", "check", "--output-format", "json", str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=8.0,
            )
            diagnostics = _parse_ruff_output(completed.stdout or "")
            return {
                "ok": True,
                "diagnostics": diagnostics,
                "message": "",
                "available": available,
            }
        except FileNotFoundError:
            available["ruff"] = False
            return {
                "ok": False,
                "diagnostics": [],
                "message": "ruff no instalado",
                "available": available,
            }
        except subprocess.CalledProcessError as exc:
            return {
                "ok": False,
                "diagnostics": [],
                "message": (exc.stderr or exc.stdout or str(exc)).strip(),
                "available": available,
            }
        except Exception as exc:
            return {
                "ok": False,
                "diagnostics": [],
                "message": str(exc),
                "available": available,
            }
        finally:
            try:
                tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

    def typecheck_code(self, code: str) -> Dict[str, Any]:
        available = _available_map()
        if not available["pyright"]:
            return {
                "ok": False,
                "diagnostics": [],
                "message": "pyright no instalado",
                "available": available,
            }

        tmp_file = _write_temp_code(code)
        try:
            completed = subprocess.run(
                ["pyright", "--outputjson", str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            diagnostics = _parse_pyright_output(completed.stdout or "")
            return {
                "ok": True,
                "diagnostics": diagnostics,
                "message": "",
                "available": available,
            }
        except FileNotFoundError:
            available["pyright"] = False
            return {
                "ok": False,
                "diagnostics": [],
                "message": "pyright no instalado",
                "available": available,
            }
        except subprocess.CalledProcessError as exc:
            return {
                "ok": False,
                "diagnostics": [],
                "message": (exc.stderr or exc.stdout or str(exc)).strip(),
                "available": available,
            }
        except Exception as exc:
            return {
                "ok": False,
                "diagnostics": [],
                "message": str(exc),
                "available": available,
            }
        finally:
            try:
                tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

    def format_code(self, code: str) -> Dict[str, Any]:
        available = _available_map()
        if not available["ruff"]:
            return {
                "ok": False,
                "message": "ruff no instalado",
                "code": code,
                "diagnostics": [],
                "available": available,
            }

        tmp_file = _write_temp_code(code)
        try:
            completed = subprocess.run(
                ["ruff", "format", str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            if completed.returncode != 0:
                return {
                    "ok": False,
                    "message": (completed.stderr or completed.stdout or "No se pudo formatear.").strip(),
                    "code": code,
                    "diagnostics": [],
                    "available": available,
                }
            new_code = tmp_file.read_text(encoding="utf-8")
            changed = new_code != code
            return {
                "ok": True,
                "changed": changed,
                "code": new_code,
                "message": "Codigo formateado." if changed else "No habia cambios de formato.",
                "diagnostics": [],
                "available": available,
            }
        except FileNotFoundError:
            available["ruff"] = False
            return {
                "ok": False,
                "message": "ruff no instalado",
                "code": code,
                "diagnostics": [],
                "available": available,
            }
        except subprocess.CalledProcessError as exc:
            return {
                "ok": False,
                "message": (exc.stderr or exc.stdout or str(exc)).strip(),
                "code": code,
                "diagnostics": [],
                "available": available,
            }
        except Exception as exc:
            return {
                "ok": False,
                "message": str(exc),
                "code": code,
                "diagnostics": [],
                "available": available,
            }
        finally:
            try:
                tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

    def fix_code(self, code: str) -> Dict[str, Any]:
        available = _available_map()
        if not available["ruff"]:
            return {
                "ok": False,
                "changed": False,
                "code_new": code,
                "summary": {
                    "text": "ruff no instalado",
                    "changes": 0,
                    "rules": [],
                },
                "diagnostics": [],
                "message": "ruff no instalado",
                "available": available,
            }

        tmp_file = _write_temp_code(code)
        try:
            before_check = subprocess.run(
                ["ruff", "check", "--output-format", "json", str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            before_diagnostics = _parse_ruff_output(before_check.stdout or "")

            completed = subprocess.run(
                ["ruff", "check", "--fix", "--exit-zero", "--output-format", "json", str(tmp_file)],
                capture_output=True,
                text=True,
                timeout=12.0,
            )
            after_diagnostics = _parse_ruff_output(completed.stdout or "")
            code_new = tmp_file.read_text(encoding="utf-8")
            changed = code_new != code

            rules_before = _unique_rule_codes(before_diagnostics)
            rules_after = set(_unique_rule_codes(after_diagnostics))
            applied_rules = [rule for rule in rules_before if rule not in rules_after]
            changes_count = _changed_lines_count(code, code_new)

            if changed and applied_rules:
                summary_text = f"Se aplicaron {changes_count} cambio(s) en {len(applied_rules)} regla(s)."
            elif changed:
                summary_text = f"Se aplicaron {changes_count} cambio(s) automaticos."
            else:
                summary_text = "No hubo correcciones automaticas aplicables."
            return {
                "ok": True,
                "changed": changed,
                "code_new": code_new,
                "message": summary_text,
                "summary": {
                    "text": summary_text,
                    "changes": changes_count,
                    "rules": applied_rules,
                },
                "diagnostics": after_diagnostics,
                "available": available,
            }
        except FileNotFoundError:
            available["ruff"] = False
            return {
                "ok": False,
                "changed": False,
                "code_new": code,
                "message": "ruff no instalado",
                "summary": {
                    "text": "ruff no instalado",
                    "changes": 0,
                    "rules": [],
                },
                "diagnostics": [],
                "available": available,
            }
        except subprocess.CalledProcessError as exc:
            error_message = (exc.stderr or exc.stdout or str(exc)).strip()
            return {
                "ok": False,
                "changed": False,
                "code_new": code,
                "message": error_message,
                "summary": {
                    "text": error_message,
                    "changes": 0,
                    "rules": [],
                },
                "diagnostics": [],
                "available": available,
            }
        except Exception as exc:
            return {
                "ok": False,
                "changed": False,
                "code_new": code,
                "message": str(exc),
                "summary": {
                    "text": str(exc),
                    "changes": 0,
                    "rules": [],
                },
                "diagnostics": [],
                "available": available,
            }
        finally:
            try:
                tmp_file.unlink(missing_ok=True)
            except Exception:
                pass


def run_app() -> None:
    if webview is None:
        raise RuntimeError("pywebview no esta instalado. Instala con: python -m pip install pywebview")

    web_dir = Path(__file__).resolve().parent / "web"
    index_path = (web_dir / "index.html").resolve()
    api = VscodeApi()
    webview.create_window(
        "Python Trainer - VSCode-like",
        url=index_path.as_uri(),
        js_api=api,
        width=1400,
        height=900,
        min_size=(1000, 700),
    )
    webview.start(debug=False)


if __name__ == "__main__":
    run_app()
