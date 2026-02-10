import ast
import getpass
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

try:
    import resource  # type: ignore[attr-defined]
except Exception:
    resource = None

BLOCKED_MODULES = {
    "os",
    "sys",
    "shutil",
    "subprocess",
    "pathlib",
    "socket",
    "requests",
    "ctypes",
}
DEFAULT_MAX_MEMORY_MB = 128
DEFAULT_MAX_CPU_S = 2


def _is_safe_identifier(name: str) -> bool:
    return name.isidentifier()


def _sandbox_dir() -> Path:
    sandbox = Path(__file__).resolve().parent.parent / "sandbox" / getpass.getuser()
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox


def _detect_blocked_import(code: str) -> Optional[str]:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name in BLOCKED_MODULES:
                    return root_name
        if isinstance(node, ast.ImportFrom):
            module_name = (node.module or "").split(".")[0]
            if module_name in BLOCKED_MODULES:
                return module_name
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                root_name = node.args[0].value.split(".")[0]
                if root_name in BLOCKED_MODULES:
                    return root_name
    return None


def _build_script(code: str, setup: Optional[Dict[str, Any]]) -> str:
    lines = []
    for key, value in (setup or {}).items():
        if _is_safe_identifier(key):
            lines.append(f"{key} = {repr(value)}")
    lines.append(code)
    return "\n".join(lines)


def _build_preexec_limiter(max_memory_mb: int, max_cpu_s: int) -> Optional[Callable[[], None]]:
    if os.name == "nt" or resource is None:
        return None

    memory_bytes = max(16, int(max_memory_mb)) * 1024 * 1024
    cpu_seconds = max(1, int(max_cpu_s))

    def _limit_resources() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        except Exception:
            pass

        for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
            limit = getattr(resource, limit_name, None)
            if limit is None:
                continue
            try:
                resource.setrlimit(limit, (memory_bytes, memory_bytes))
                break
            except Exception:
                continue

    return _limit_resources


def run_user_code(
    code: str,
    setup: Optional[Dict[str, Any]] = None,
    timeout_s: float = 2.5,
    max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
    max_cpu_s: int = DEFAULT_MAX_CPU_S,
) -> Dict[str, Any]:
    start = time.perf_counter()
    warnings: list[str] = []

    blocked_module = _detect_blocked_import(code)
    if blocked_module:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "blocked",
            "stdout": "",
            "stderr": "",
            "message": f"Import bloqueado por seguridad: '{blocked_module}'.",
            "duration_ms": duration_ms,
            "warnings": warnings,
        }

    script = _build_script(code, setup)
    run_kwargs: Dict[str, Any] = {
        "cwd": str(_sandbox_dir()),
        "capture_output": True,
        "text": True,
        "timeout": timeout_s,
    }
    preexec_limiter = _build_preexec_limiter(max_memory_mb=max_memory_mb, max_cpu_s=max_cpu_s)
    if preexec_limiter is not None:
        run_kwargs["preexec_fn"] = preexec_limiter
    else:
        warnings.append("Limites de CPU/memoria no disponibles en este sistema operativo.")

    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            **run_kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "timeout",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "message": "Tiempo excedido.",
            "duration_ms": duration_ms,
            "warnings": warnings,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "message": f"No se pudo ejecutar el codigo: {exc}",
            "duration_ms": duration_ms,
            "warnings": warnings,
        }

    duration_ms = int((time.perf_counter() - start) * 1000)
    stdout_text = completed.stdout or ""
    stderr_text = completed.stderr or ""
    if completed.returncode < 0:
        return {
            "status": "timeout",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "message": "Ejecucion detenida por limite de recursos.",
            "duration_ms": duration_ms,
            "warnings": warnings,
        }

    if completed.returncode == 0:
        return {
            "status": "ok",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "message": "Ejecucion completada.",
            "duration_ms": duration_ms,
            "warnings": warnings,
        }

    error_message = stderr_text.strip().splitlines()[-1] if stderr_text.strip() else "Error en ejecucion."
    return {
        "status": "error",
        "stdout": stdout_text,
        "stderr": stderr_text,
        "message": error_message,
        "duration_ms": duration_ms,
        "warnings": warnings,
    }
