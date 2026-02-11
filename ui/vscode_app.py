from __future__ import annotations

import ast
import difflib
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import webview  # type: ignore
except Exception:
    webview = None

from core.exercises import find_exercise, get_modules
from core.progress import get_current_position, get_record, load_progress, save_progress
from core.runner import run_user_code
from core.validator import validate_user_code


def _run_command(command: List[str], timeout: float = 3.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_ruff_command(args: List[str], timeout: float) -> subprocess.CompletedProcess[str]:
    last_error: Optional[Exception] = None
    commands = [
        [sys.executable, "-m", "ruff", *args],
        ["ruff", *args],
    ]
    for command in commands:
        try:
            return _run_command(command, timeout=timeout)
        except FileNotFoundError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise FileNotFoundError("ruff no instalado")


def _run_pyright_command(args: List[str], timeout: float) -> subprocess.CompletedProcess[str]:
    last_error: Optional[Exception] = None
    commands = [
        [sys.executable, "-m", "pyright", *args],
        ["pyright", *args],
    ]
    for command in commands:
        try:
            return _run_command(command, timeout=timeout)
        except FileNotFoundError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise FileNotFoundError("pyright no instalado")


def _pyright_langserver_command() -> Optional[List[str]]:
    commands = [
        [sys.executable, "-m", "pyright.langserver", "--stdio"],
        ["pyright-langserver", "--stdio"],
    ]
    for command in commands:
        try:
            completed = _run_command([*command[:3], "--help"] if command[0] == sys.executable else [command[0], "--help"], timeout=2.0)
            if completed.returncode in {0, 1, 2}:
                return command
        except Exception:
            continue
    return None


def _tool_available(tool_name: str) -> bool:
    if tool_name == "ruff":
        try:
            completed = _run_ruff_command(["--version"], timeout=2.0)
            return completed.returncode == 0
        except Exception:
            return False
    if tool_name == "pyright":
        try:
            completed = _run_pyright_command(["--version"], timeout=2.0)
            return completed.returncode == 0
        except Exception:
            return False
    if tool_name == "pyright-langserver":
        return _pyright_langserver_command() is not None
    return shutil.which(tool_name) is not None


def _tool_version(tool_name: str) -> str:
    try:
        if tool_name == "ruff":
            completed = _run_ruff_command(["--version"], timeout=2.0)
        elif tool_name == "pyright":
            completed = _run_pyright_command(["--version"], timeout=2.0)
        elif tool_name == "pyright-langserver":
            command = _pyright_langserver_command()
            if not command:
                return ""
            completed = _run_command([command[0], "--version"] if len(command) == 2 else [sys.executable, "-m", "pyright", "--version"], timeout=2.0)
        else:
            if not _tool_available(tool_name):
                return ""
            completed = _run_command([tool_name, "--version"], timeout=2.0)
    except Exception:
        return ""
    version_text = (completed.stdout or completed.stderr or "").strip()
    return version_text.splitlines()[0] if version_text else ""


def _available_map() -> Dict[str, bool]:
    return {
        "ruff": _tool_available("ruff"),
        "pyright": _tool_available("pyright"),
        "pyright_langserver": _tool_available("pyright-langserver"),
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


def _lsp_markdown_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("value", "")).strip()
    if isinstance(value, list):
        return "\n".join(_lsp_markdown_to_text(item) for item in value if item)
    return str(value or "")


def _map_lsp_completion_item(item: Dict[str, Any]) -> Dict[str, Any]:
    label = str(item.get("label", "")).strip()
    if not label:
        return {}
    documentation = _lsp_markdown_to_text(item.get("documentation"))
    insert_text = str(item.get("insertText", "")).strip() or label
    return {
        "label": label,
        "kind": int(item.get("kind", 1) or 1),
        "detail": str(item.get("detail", "")).strip(),
        "documentation": documentation,
        "insertText": insert_text,
    }


class _PyrightLspClient:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending: Dict[int, queue.Queue[Dict[str, Any]]] = {}
        self._next_id = 1
        self._document_opened = False
        self._document_version = 0
        self._document_uri = (Path(__file__).resolve().parent.parent / "lsp_buffer.py").as_uri()

    def _ensure_started(self) -> bool:
        if self._process and self._process.poll() is None:
            return True

        command = _pyright_langserver_command()
        if not command:
            return False
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception:
            self._process = None
            return False

        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        try:
            self._request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": Path(__file__).resolve().parent.parent.as_uri(),
                    "capabilities": {},
                },
                timeout=5.0,
            )
            self._notify("initialized", {})
            return True
        except Exception:
            self.shutdown()
            return False

    def _reader_loop(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        stream = process.stdout
        while True:
            headers: Dict[str, str] = {}
            while True:
                line = stream.readline()
                if not line:
                    self._flush_pending_with_error("Pyright LSP finalizado.")
                    return
                if line in {b"\r\n", b"\n"}:
                    break
                header_line = line.decode("utf-8", errors="replace").strip()
                if ":" in header_line:
                    key, value = header_line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            content_length = int(headers.get("content-length", "0") or "0")
            if content_length <= 0:
                continue
            body = stream.read(content_length)
            if not body:
                self._flush_pending_with_error("Sin respuesta de Pyright LSP.")
                return
            try:
                payload = json.loads(body.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if isinstance(payload, dict) and "id" in payload:
                request_id = int(payload["id"])
                with self._lock:
                    waiter = self._pending.pop(request_id, None)
                if waiter:
                    waiter.put(payload)

    def _send(self, payload: Dict[str, Any]) -> None:
        process = self._process
        if not process or not process.stdin:
            raise RuntimeError("Pyright LSP no disponible.")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        process.stdin.write(header + body)
        process.stdin.flush()

    def _request(self, method: str, params: Dict[str, Any], timeout: float = 4.0) -> Dict[str, Any]:
        if not self._ensure_started():
            raise RuntimeError("No se pudo iniciar pyright-langserver.")
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            response = waiter.get(timeout=timeout)
        except Exception as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise RuntimeError(f"Timeout LSP en {method}") from exc
        if "error" in response:
            error_payload = response.get("error", {})
            raise RuntimeError(str(error_payload.get("message", "Error de pyright-langserver.")))
        return response

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        if not self._ensure_started():
            raise RuntimeError("No se pudo iniciar pyright-langserver.")
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _sync_document(self, code: str) -> None:
        self._document_version += 1
        if not self._document_opened:
            self._notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": self._document_uri,
                        "languageId": "python",
                        "version": self._document_version,
                        "text": code,
                    }
                },
            )
            self._document_opened = True
            return
        self._notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": self._document_uri, "version": self._document_version},
                "contentChanges": [{"text": code}],
            },
        )

    def complete(self, code: str, line: int, column: int) -> Dict[str, Any]:
        self._sync_document(code)
        response = self._request(
            "textDocument/completion",
            {
                "textDocument": {"uri": self._document_uri},
                "position": {"line": max(0, line - 1), "character": max(0, column - 1)},
            },
        )
        result = response.get("result", [])
        items = result.get("items", []) if isinstance(result, dict) else result
        parsed_items: List[Dict[str, Any]] = []
        if isinstance(items, list):
            for item in items[:100]:
                if isinstance(item, dict):
                    mapped = _map_lsp_completion_item(item)
                    if mapped:
                        parsed_items.append(mapped)
        return {"ok": True, "items": parsed_items}

    def hover(self, code: str, line: int, column: int) -> Dict[str, Any]:
        self._sync_document(code)
        response = self._request(
            "textDocument/hover",
            {
                "textDocument": {"uri": self._document_uri},
                "position": {"line": max(0, line - 1), "character": max(0, column - 1)},
            },
        )
        result = response.get("result") or {}
        contents = _lsp_markdown_to_text(result.get("contents", ""))
        if not contents:
            return {"ok": True, "contents": ""}
        return {"ok": True, "contents": contents}

    def _flush_pending_with_error(self, message: str) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for waiter in pending:
            waiter.put({"error": {"message": message}})

    def shutdown(self) -> None:
        process = self._process
        if not process:
            return
        try:
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass
        self._process = None
        self._document_opened = False


class VscodeApi:
    def __init__(self) -> None:
        self._lsp_client = _PyrightLspClient()

    def _current_position(self) -> tuple[str, str, str]:
        progress = load_progress()
        return get_current_position(progress)

    def close(self) -> None:
        self._lsp_client.shutdown()

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
            "pyright_langserver": _tool_version("pyright-langserver") if available["pyright_langserver"] else "",
        }
        return {
            "ok": True,
            "available": available,
            "versions": versions,
        }

    def syntax_check(self, code: str) -> Dict[str, Any]:
        try:
            ast.parse(code)
            return {"ok": True, "diagnostics": [], "message": "", "available": _available_map()}
        except SyntaxError as exc:
            line = max(1, int(exc.lineno or 1))
            col = max(1, int(exc.offset or 1))
            end_col = max(col + 1, col + 1)
            diagnostics = [
                {
                    "source": "python",
                    "severity": "error",
                    "code": "SYNTAX",
                    "message": str(exc.msg or "Syntax error"),
                    "startLineNumber": line,
                    "startColumn": col,
                    "endLineNumber": line,
                    "endColumn": end_col,
                }
            ]
            return {
                "ok": False,
                "diagnostics": diagnostics,
                "message": str(exc.msg or "Syntax error"),
                "available": _available_map(),
            }
        except Exception as exc:
            return {"ok": False, "diagnostics": [], "message": str(exc), "available": _available_map()}

    def lsp_complete(self, code: str, line: int, column: int) -> Dict[str, Any]:
        try:
            result = self._lsp_client.complete(code, line, column)
            result["available"] = _available_map()
            return result
        except Exception as exc:
            return {"ok": False, "items": [], "message": str(exc), "available": _available_map()}

    def lsp_hover(self, code: str, line: int, column: int) -> Dict[str, Any]:
        try:
            result = self._lsp_client.hover(code, line, column)
            result["available"] = _available_map()
            return result
        except Exception as exc:
            return {"ok": False, "contents": "", "message": str(exc), "available": _available_map()}

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
            completed = _run_ruff_command(["check", "--output-format", "json", str(tmp_file)], timeout=8.0)
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
            completed = _run_pyright_command(["--outputjson", str(tmp_file)], timeout=10.0)
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
            completed = _run_ruff_command(["format", str(tmp_file)], timeout=10.0)
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
            before_check = _run_ruff_command(["check", "--output-format", "json", str(tmp_file)], timeout=10.0)
            before_diagnostics = _parse_ruff_output(before_check.stdout or "")

            completed = _run_ruff_command(
                ["check", "--fix", "--exit-zero", "--output-format", "json", str(tmp_file)],
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
    try:
        webview.start(debug=False)
    finally:
        api.close()


if __name__ == "__main__":
    run_app()
