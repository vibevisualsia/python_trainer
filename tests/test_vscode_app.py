import json

from ui.vscode_app import VscodeApi, _parse_pyright_output, _parse_ruff_output


def test_parse_ruff_output_json():
    sample = json.dumps(
        [
            {
                "code": "F821",
                "message": "Undefined name `x`",
                "location": {"row": 2, "column": 5},
                "end_location": {"row": 2, "column": 6},
            }
        ]
    )
    diagnostics = _parse_ruff_output(sample)
    assert len(diagnostics) == 1
    assert diagnostics[0]["source"] == "ruff"
    assert diagnostics[0]["startLineNumber"] == 2
    assert diagnostics[0]["code"] == "F821"
    assert diagnostics[0]["message"] == "Undefined name `x`"


def test_parse_pyright_output_json():
    sample = json.dumps(
        {
            "generalDiagnostics": [
                {
                    "severity": "error",
                    "message": "Cannot find name 'foo'",
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 3},
                    },
                }
            ]
        }
    )
    diagnostics = _parse_pyright_output(sample)
    assert len(diagnostics) == 1
    assert diagnostics[0]["source"] == "pyright"
    assert diagnostics[0]["severity"] == "error"
    assert diagnostics[0]["startLineNumber"] == 1


def test_run_code_keeps_exam_without_hint(monkeypatch):
    api = VscodeApi()
    monkeypatch.setattr(api, "_current_exercise", lambda: {"setup": {}, "checks": []})

    def fake_runner(code, setup=None):
        return {
            "status": "timeout",
            "stdout": "",
            "stderr": "",
            "message": "Tiempo excedido.",
            "warnings": [],
        }

    monkeypatch.setattr("ui.vscode_app.run_user_code", fake_runner)
    result = api.run_code("while True:\n    pass\n", mode="exam")
    assert result["status"] == "timeout"
    assert result["hint"] == ""


def test_run_code_does_not_validate_but_check_code_does(monkeypatch):
    api = VscodeApi()
    monkeypatch.setattr(api, "_current_exercise", lambda: {"setup": {}, "checks": []})

    monkeypatch.setattr(
        "ui.vscode_app.run_user_code",
        lambda code, setup=None: {
            "status": "ok",
            "stdout": "123\n",
            "stderr": "",
            "message": "Ejecucion completada.",
            "warnings": [],
        },
    )

    validate_calls = {"count": 0}

    def fake_validate(code, exercise):
        validate_calls["count"] += 1
        return {"status": "fail", "message": "No coincide", "stdout": "", "stderr": "", "details": ""}

    monkeypatch.setattr("ui.vscode_app.validate_user_code", fake_validate)

    run_result = api.run_code("print(123)", mode="study")
    assert run_result["status"] == "ok"
    assert validate_calls["count"] == 0

    check_result = api.check_code("print(123)", mode="study")
    assert check_result["status"] == "fail"
    assert validate_calls["count"] == 1


def test_fix_code_returns_expected_shape_when_ruff_missing(monkeypatch):
    api = VscodeApi()
    monkeypatch.setattr(
        "ui.vscode_app._available_map",
        lambda: {"ruff": False, "pyright": False, "pyright_langserver": False},
    )
    result = api.fix_code("print(1)\n")
    assert result["ok"] is False
    assert result["changed"] is False
    assert result["code_new"] == "print(1)\n"
    assert "ruff" in result["message"].lower()
    assert result["available"]["ruff"] is False
    assert "summary" in result
    assert isinstance(result["summary"], dict)


def test_api_capabilities_shape_when_tools_missing(monkeypatch):
    api = VscodeApi()
    monkeypatch.setattr("ui.vscode_app._tool_available", lambda _name: False)
    capabilities = api.api_capabilities()
    assert capabilities["ok"] is True
    assert set(capabilities["available"].keys()) == {"ruff", "pyright", "pyright_langserver"}
    assert capabilities["available"]["ruff"] is False
    assert capabilities["available"]["pyright"] is False
    assert capabilities["available"]["pyright_langserver"] is False
    assert set(capabilities["versions"].keys()) == {"ruff", "pyright", "pyright_langserver"}


def test_format_code_returns_error_when_ruff_missing(monkeypatch):
    api = VscodeApi()
    monkeypatch.setattr(
        "ui.vscode_app._available_map",
        lambda: {"ruff": False, "pyright": False, "pyright_langserver": False},
    )
    result = api.format_code("print(1)\n")
    assert result["ok"] is False
    assert "ruff" in result["message"].lower()
    assert result["available"]["ruff"] is False


def test_syntax_check_reports_python_error():
    api = VscodeApi()
    result = api.syntax_check("if True print('x')\n")
    assert result["ok"] is False
    assert result["diagnostics"]
    diag = result["diagnostics"][0]
    assert diag["code"] == "SYNTAX"
    assert diag["severity"] == "error"
    assert diag["startLineNumber"] >= 1
