let editor = null;
let bridgeApi = null;
let monacoRef = null;
let initDone = false;
let saveStatusTimer = null;

const statusNode = document.getElementById("status");
const runStatusNode = document.getElementById("run-status");
const stdoutNode = document.getElementById("stdout");
const stderrNode = document.getElementById("stderr");
const problemsListNode = document.getElementById("problems-list");

function setStatus(text) {
  statusNode.textContent = text;
}

function showRunMessage(text) {
  runStatusNode.textContent = text || "";
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => fn(...args), delay);
  };
}

function markerSeverity(monaco, severity) {
  const value = String(severity || "").toLowerCase();
  if (value === "error") return monaco.MarkerSeverity.Error;
  if (value === "info") return monaco.MarkerSeverity.Info;
  if (value === "hint") return monaco.MarkerSeverity.Hint;
  return monaco.MarkerSeverity.Warning;
}

function normalizeDiagnostics(monaco, diagnostics) {
  return (diagnostics || []).map((item) => ({
    startLineNumber: Math.max(1, Number(item.startLineNumber || 1)),
    startColumn: Math.max(1, Number(item.startColumn || 1)),
    endLineNumber: Math.max(1, Number(item.endLineNumber || item.startLineNumber || 1)),
    endColumn: Math.max(1, Number(item.endColumn || item.startColumn || 2)),
    message: String(item.message || "Issue"),
    source: String(item.source || "tool"),
    severity: markerSeverity(monaco, item.severity),
  }));
}

function renderProblems(problems) {
  problemsListNode.innerHTML = "";
  if (!problems.length) {
    const li = document.createElement("li");
    li.textContent = "No problems";
    problemsListNode.appendChild(li);
    return;
  }

  problems.forEach((problem) => {
    const li = document.createElement("li");
    li.textContent = `${problem.source} L${problem.startLineNumber}: ${problem.message}`;
    li.addEventListener("click", () => {
      if (!editor) return;
      editor.setPosition({
        lineNumber: problem.startLineNumber,
        column: problem.startColumn,
      });
      editor.focus();
      editor.revealLineInCenter(problem.startLineNumber);
    });
    problemsListNode.appendChild(li);
  });
}

function getEditorCode() {
  if (!editor) return "";
  return editor.getValue();
}

function updateOutput(result) {
  showRunMessage(`${result.status || "unknown"}: ${result.message || ""}`.trim());
  stdoutNode.textContent = result.stdout || "";
  stderrNode.textContent = result.stderr || "";
  if (result.hint) {
    runStatusNode.textContent += `\n${result.hint}`;
  }
  if (result.warnings && result.warnings.length) {
    runStatusNode.textContent += `\nWarnings:\n- ${result.warnings.join("\n- ")}`;
  }
}

async function executeAction(methodName, mode) {
  if (!bridgeApi || !editor) {
    showRunMessage("Bridge no disponible. Reinicia la app.");
    return;
  }
  setStatus(`${methodName} (${mode})...`);
  try {
    const runnerMethod = bridgeApi[methodName];
    if (typeof runnerMethod !== "function") {
      throw new Error(`Metodo no disponible: ${methodName}`);
    }
    const result = await runnerMethod(getEditorCode(), mode);
    updateOutput(result || {});
  } catch (error) {
    showRunMessage(`error: ${String(error)}`);
    stderrNode.textContent = String(error);
  }
  setStatus("Ready");
}

async function run(mode) {
  await executeAction("run_code", mode);
}

async function check() {
  await executeAction("check_code", "study");
}

async function saveCode() {
  if (!bridgeApi || !editor) {
    showRunMessage("Bridge no disponible. No se pudo guardar.");
    return;
  }
  setStatus("Saving...");
  try {
    const response = await bridgeApi.save_code(getEditorCode());
    if (response && response.ok) {
      setStatus("Saved");
      if (saveStatusTimer) {
        clearTimeout(saveStatusTimer);
      }
      saveStatusTimer = setTimeout(() => setStatus("Ready"), 1200);
    } else {
      setStatus("Save failed");
    }
  } catch (error) {
    setStatus("Save failed");
    stderrNode.textContent = String(error);
  }
}

async function runLintDiagnostics(monaco) {
  if (!bridgeApi || !editor) return;
  try {
    const lint = await bridgeApi.lint_code(getEditorCode());
    const markers = normalizeDiagnostics(monaco, lint.diagnostics || []);
    monaco.editor.setModelMarkers(editor.getModel(), "pythontrainer", markers);
    renderProblems(markers);
  } catch (error) {
    showRunMessage(`lint error: ${String(error)}`);
  }
}

function initEvents(monaco) {
  document.getElementById("btn-run").addEventListener("click", () => run("study"));
  document.getElementById("btn-run-exam").addEventListener("click", () => run("exam"));
  document.getElementById("btn-check").addEventListener("click", () => check());
  document.getElementById("btn-save").addEventListener("click", () => saveCode());
  const debouncedDiagnostics = debounce(() => runLintDiagnostics(monaco), 500);
  editor.onDidChangeModelContent(() => {
    setStatus("Unsaved changes");
    debouncedDiagnostics();
  });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    saveCode();
  });
}

async function waitForBridge(maxRetries = 40, delayMs = 100) {
  for (let i = 0; i < maxRetries; i += 1) {
    if (window.pywebview && window.pywebview.api) {
      return window.pywebview.api;
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return null;
}

async function initBridgeAndCode(monaco) {
  if (initDone) return;
  initDone = true;

  bridgeApi = await waitForBridge();
  if (!bridgeApi) {
    setStatus("Bridge no disponible");
    showRunMessage("No se detecto pywebview.api. Reintenta abrir la app.");
    editor.setValue('print("hola")\n');
    return;
  }

  let initialCode = "";
  try {
    initialCode = await bridgeApi.load_initial_code();
  } catch (error) {
    stderrNode.textContent = String(error);
  }

  editor.setValue(initialCode || 'print("hola")\n');
  await runLintDiagnostics(monaco);
  setStatus("Ready");
}

function startMonaco() {
  window.MonacoEnvironment = {
    getWorkerUrl: function () {
      const code = `
        self.MonacoEnvironment = { baseUrl: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/' };
        importScripts('https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/base/worker/workerMain.js');
      `;
      return `data:text/javascript;charset=utf-8,${encodeURIComponent(code)}`;
    },
  };

  require.config({
    paths: {
      vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs",
    },
  });

  require(["vs/editor/editor.main"], function () {
    monacoRef = monaco;
    editor = monaco.editor.create(document.getElementById("editor"), {
      value: "",
      language: "python",
      theme: "vs-dark",
      automaticLayout: true,
      tabSize: 4,
      insertSpaces: true,
      detectIndentation: false,
      quickSuggestions: true,
      suggestOnTriggerCharacters: true,
      wordBasedSuggestions: "currentDocument",
      tabCompletion: "on",
      minimap: { enabled: false },
      fontSize: 14,
    });

    initEvents(monacoRef);
    initBridgeAndCode(monacoRef);
  });
}

window.addEventListener("pywebviewready", () => {
  if (monacoRef) {
    initBridgeAndCode(monacoRef);
  }
});

startMonaco();
