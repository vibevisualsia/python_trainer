import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core import runner  # noqa: E402


def test_python_cmd_uses_system_python_when_frozen(monkeypatch):
    frozen_executable = r"C:\app\PythonTrainer-GUI.exe"
    monkeypatch.setattr(runner.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runner.sys, "executable", frozen_executable, raising=False)
    monkeypatch.setattr(
        runner.shutil,
        "which",
        lambda name: r"C:\Python314\python.exe" if name == "python" else None,
    )
    selected = runner._python_cmd()
    assert selected == r"C:\Python314\python.exe"
    assert selected != frozen_executable
