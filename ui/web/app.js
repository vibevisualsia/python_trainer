let editor = null;
let bridgeApi = null;
let monacoRef = null;
let initDone = false;
let saveStatusTimer = null;
let lintStatusTimer = null;
let latestDiagnostics = [];
let hoverProviderDisposable = null;
let pendingFixPayload = null;
let toolbarBound = false;
let apiCapabilities = {
  available: { ruff: true, pyright: true },
  versions: { ruff: "", pyright: "" },
};

const statusNode = document.getElementById("status");
const runStatusNode = document.getElementById("run-status");
const stdoutNode = document.getElementById("stdout");
const stderrNode = document.getElementById("stderr");
const problemsListNode = document.getElementById("problems-list");
const formatButtonNode = document.getElementById("btn-format");
const fixButtonNode = document.getElementById("btn-fix");
const fixModalNode = document.getElementById("fix-preview-modal");
const fixSummaryNode = document.getElementById("fix-summary");
const fixDiffNode = document.getElementById("fix-diff");
const fixApplyButton = document.getElementById("btn-fix-apply");
const fixCancelButton = document.getElementById("btn-fix-cancel");

function setStatus(text) {
  statusNode.textContent = text;
}

function setTemporaryStatus(text, ms = 1200) {
  setStatus(text);
  if (saveStatusTimer) {
    clearTimeout(saveStatusTimer);
  }
  saveStatusTimer = setTimeout(() => setStatus("Ready"), ms);
}

function showRunMessage(text) {
  runStatusNode.textContent = text || "";
}

window.addEventListener("error", (event) => {
  const msg = event && event.message ? event.message : "Error JavaScript no identificado.";
  showRunMessage(`js error: ${msg}`);
  stderrNode.textContent = `${msg}\n${(event && event.filename) || ""}:${(event && event.lineno) || ""}`;
});

function toCamelCase(value) {
  return String(value || "").replace(/_([a-z])/g, (_match, char) => char.toUpperCase());
}

function resolveApiMethod(methodName) {
  if (!bridgeApi) return null;
  const candidates = [methodName, toCamelCase(methodName)];
  for (const candidate of candidates) {
    if (typeof bridgeApi[candidate] === "function") {
      return bridgeApi[candidate].bind(bridgeApi);
    }
  }
  return null;
}

async function ensureBridge() {
  if (bridgeApi) return bridgeApi;
  bridgeApi = await waitForBridge(15, 120);
  return bridgeApi;
}

function mergeCapabilities(capabilitiesPayload) {
  const fallback = { ruff: true, pyright: true };
  const available = (capabilitiesPayload && capabilitiesPayload.available) || {};
  const versions = (capabilitiesPayload && capabilitiesPayload.versions) || {};
  apiCapabilities = {
    available: {
      ruff: typeof available.ruff === "boolean" ? available.ruff : fallback.ruff,
      pyright: typeof available.pyright === "boolean" ? available.pyright : fallback.pyright,
    },
    versions: {
      ruff: String(versions.ruff || ""),
      pyright: String(versions.pyright || ""),
    },
  };
}

function applyCapabilitiesUI() {
  const hasRuff = apiCapabilities.available.ruff !== false;
  if (formatButtonNode) {
    formatButtonNode.disabled = !hasRuff;
  }
  if (fixButtonNode) {
    fixButtonNode.disabled = !hasRuff;
  }
  if (!hasRuff) {
    showRunMessage("Aviso: ruff no instalado. Format/Fix deshabilitados.");
  }
}

async function loadCapabilities() {
  await ensureBridge();
  if (!bridgeApi) {
    setStatus("Bridge no disponible");
    return;
  }
  const capabilitiesMethod = resolveApiMethod("api_capabilities");
  if (!capabilitiesMethod) {
    applyCapabilitiesUI();
    return;
  }
  try {
    const payload = await capabilitiesMethod();
    mergeCapabilities(payload || {});
  } catch (_error) {
  }
  applyCapabilitiesUI();
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

function severityLabelFromRaw(raw) {
  const value = String(raw || "").toLowerCase();
  if (value === "error") return "ERROR";
  return "WARNING";
}

function normalizeDiagnostics(monaco, diagnostics) {
  return (diagnostics || []).map((item) => ({
    startLineNumber: Math.max(1, Number(item.startLineNumber || 1)),
    startColumn: Math.max(1, Number(item.startColumn || 1)),
    endLineNumber: Math.max(1, Number(item.endLineNumber || item.startLineNumber || 1)),
    endColumn: Math.max(1, Number(item.endColumn || item.startColumn || 2)),
    message: String(item.message || "Issue"),
    code: String(item.code || "").trim(),
    severityLabel: severityLabelFromRaw(item.severity),
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
    const codeLabel = `[${problem.code || "--"}]`;
    li.textContent = `[${problem.severityLabel}] ${codeLabel} ${problem.message} (L${problem.startLineNumber}:C${problem.startColumn})`;
    li.addEventListener("click", () => {
      if (!editor) return;
      editor.revealPositionInCenter({
        lineNumber: problem.startLineNumber,
        column: problem.startColumn,
      });
      editor.setSelection({
        startLineNumber: problem.startLineNumber,
        startColumn: problem.startColumn,
        endLineNumber: problem.endLineNumber,
        endColumn: problem.endColumn,
      });
      editor.focus();
    });
    problemsListNode.appendChild(li);
  });
}

function buildDiffPreview(beforeCode, afterCode, maxLines = 30) {
  if (beforeCode === afterCode) {
    return "No hay cambios en el codigo.";
  }
  const before = (beforeCode || "").split("\n");
  const after = (afterCode || "").split("\n");
  const total = Math.max(before.length, after.length);
  const preview = [];
  let idx = 0;
  while (idx < total && preview.length < maxLines) {
    const left = before[idx];
    const right = after[idx];
    if (left !== right) {
      if (left !== undefined) {
        preview.push(`- ${left}`);
      }
      if (right !== undefined) {
        preview.push(`+ ${right}`);
      }
    }
    idx += 1;
  }
  if (!preview.length) {
    return "No hay cambios en el codigo.";
  }
  if (idx < total) {
    preview.push(`... (preview recortado, primeras ${maxLines} lineas cambiadas)`);
  }
  return preview.join("\n");
}

function closeFixPreview() {
  if (!fixModalNode) return;
  fixModalNode.classList.add("hidden");
  pendingFixPayload = null;
}

function openFixPreview(payload) {
  if (!fixModalNode || !fixSummaryNode || !fixDiffNode) {
    return false;
  }
  pendingFixPayload = payload;
  const summary = payload.summary || {};
  const rules = Array.isArray(summary.rules) ? summary.rules : [];
  const lines = [
    summary.text || "Preview de fix.",
    `Cambios: ${summary.changes || 0}`,
    `Reglas: ${rules.length ? rules.join(", ") : "sin detalle"}`,
  ];
  fixSummaryNode.textContent = lines.join("\n");
  fixDiffNode.textContent = buildDiffPreview(payload.code_before || "", payload.code_new || "");
  fixModalNode.classList.remove("hidden");
  return true;
}

async function applyPendingFix() {
  if (!pendingFixPayload || !editor) {
    closeFixPreview();
    return;
  }
  const previousPosition = editor.getPosition();
  editor.setValue(pendingFixPayload.code_new || getEditorCode());
  if (previousPosition) {
    editor.setPosition(previousPosition);
  }
  closeFixPreview();
  await runLintDiagnostics(monacoRef);
  setTemporaryStatus("Saved", 1000);
}

function applyMarkers(monaco, problems) {
  latestDiagnostics = problems;
  const markers = problems.map((problem) => ({
    startLineNumber: problem.startLineNumber,
    startColumn: problem.startColumn,
    endLineNumber: problem.endLineNumber,
    endColumn: problem.endColumn,
    severity: problem.severity,
    message: problem.code ? `[${problem.code}] ${problem.message}` : problem.message,
    source: problem.source,
    code: problem.code || undefined,
  }));
  monaco.editor.setModelMarkers(editor.getModel(), "pythontrainer", markers);
  renderProblems(problems);
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
  if (!editor) {
    showRunMessage("Editor no disponible.");
    return;
  }
  await ensureBridge();
  if (!bridgeApi) {
    showRunMessage("Bridge no disponible. Reinicia la app.");
    return;
  }
  showRunMessage(`Ejecutando ${methodName}...`);
  if (methodName === "check_code") {
    setStatus("Checking");
  } else {
    setStatus("Running");
  }
  try {
    const runnerMethod = resolveApiMethod(methodName);
    if (!runnerMethod) {
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
  if (!editor) {
    showRunMessage("Editor no disponible.");
    return;
  }
  await ensureBridge();
  if (!bridgeApi) {
    showRunMessage("Bridge no disponible. No se pudo guardar.");
    return;
  }
  setStatus("Running");
  try {
    const saveMethod = resolveApiMethod("save_code");
    if (!saveMethod) {
      throw new Error("Metodo no disponible: save_code");
    }
    const response = await saveMethod(getEditorCode());
    if (response && response.ok) {
      setTemporaryStatus("Saved");
    } else {
      setStatus("Ready");
    }
  } catch (error) {
    setStatus("Ready");
    stderrNode.textContent = String(error);
  }
}

async function runLintDiagnostics(monaco) {
  if (!editor) return;
  await ensureBridge();
  if (!bridgeApi) return;
  setStatus("Linting");
  if (lintStatusTimer) {
    clearTimeout(lintStatusTimer);
  }
  try {
    const lintMethod = resolveApiMethod("lint_code");
    if (!lintMethod) {
      setStatus("Ready");
      return;
    }
    const lint = await lintMethod(getEditorCode());
    if (lint && lint.available) {
      mergeCapabilities({ available: lint.available });
      applyCapabilitiesUI();
    }
    const lintDiagnostics = Array.isArray(lint && lint.diagnostics) ? lint.diagnostics : [];
    let typeDiagnostics = [];
    if (apiCapabilities.available.pyright !== false) {
      const typecheckMethod = resolveApiMethod("typecheck_code");
      if (typecheckMethod) {
        const typecheck = await typecheckMethod(getEditorCode());
        if (typecheck && typecheck.available) {
          mergeCapabilities({ available: typecheck.available });
          applyCapabilitiesUI();
        }
        typeDiagnostics = Array.isArray(typecheck && typecheck.diagnostics) ? typecheck.diagnostics : [];
      }
    }
    const merged = [...lintDiagnostics, ...typeDiagnostics];
    const markers = normalizeDiagnostics(monaco, merged);
    applyMarkers(monaco, markers);
    lintStatusTimer = setTimeout(() => setStatus("Ready"), 250);
  } catch (error) {
    showRunMessage(`lint error: ${String(error)}`);
    setStatus("Ready");
  }
}

async function applyCodeTransform(methodName, stateText) {
  if (!editor) {
    showRunMessage("Editor no disponible.");
    return;
  }
  await ensureBridge();
  if (!bridgeApi) {
    showRunMessage("Bridge no disponible. Reinicia la app.");
    return;
  }
  setStatus(stateText);
  try {
    const method = resolveApiMethod(methodName);
    if (!method) {
      throw new Error(`Metodo no disponible: ${methodName}`);
    }
    const currentCode = getEditorCode();
    const result = await method(currentCode);
    const summaryText = result && result.summary && result.summary.text ? result.summary.text : result.message || "";
    showRunMessage(`${methodName}: ${summaryText}`.trim());
    if (!result || !result.ok) {
      const failText = summaryText || "Operacion fallida.";
      stderrNode.textContent = failText;
      setStatus("Ready");
      return;
    }
    if (methodName === "fix_code") {
      if (result.changed && typeof result.code_new === "string") {
        const opened = openFixPreview({
          code_before: currentCode,
          code_new: result.code_new,
          summary: result.summary || {},
        });
        if (!opened) {
          const accepted = window.confirm(`${summaryText}\n\nQuieres reemplazar el codigo del editor?`);
          if (accepted) {
            editor.setValue(result.code_new);
            await runLintDiagnostics(monacoRef);
          }
        }
      } else {
        setStatus("Ready");
      }
      return;
    }
    if (result.changed && typeof result.code === "string") {
      const previousPosition = editor.getPosition();
      editor.setValue(result.code);
      if (previousPosition) {
        editor.setPosition(previousPosition);
      }
    }
    if (result.diagnostics && Array.isArray(result.diagnostics)) {
      applyMarkers(monacoRef, normalizeDiagnostics(monacoRef, result.diagnostics));
    } else {
      await runLintDiagnostics(monacoRef);
    }
    setTemporaryStatus("Saved", 1000);
  } catch (error) {
    showRunMessage(`error: ${String(error)}`);
    setStatus("Ready");
  }
}

function bindToolbarButtons() {
  if (toolbarBound) return;
  const runBtn = document.getElementById("btn-run");
  const runExamBtn = document.getElementById("btn-run-exam");
  const checkBtn = document.getElementById("btn-check");
  const saveBtn = document.getElementById("btn-save");
  const formatBtn = document.getElementById("btn-format");
  const fixBtn = document.getElementById("btn-fix");
  if (runBtn) runBtn.addEventListener("click", () => run("study"));
  if (runExamBtn) runExamBtn.addEventListener("click", () => run("exam"));
  if (checkBtn) checkBtn.addEventListener("click", () => check());
  if (saveBtn) saveBtn.addEventListener("click", () => saveCode());
  if (formatBtn) formatBtn.addEventListener("click", () => applyCodeTransform("format_code", "Formatting"));
  if (fixBtn) fixBtn.addEventListener("click", () => applyCodeTransform("fix_code", "Fixing"));
  toolbarBound = true;
}

function initEvents(monaco) {
  bindToolbarButtons();
  if (fixApplyButton) {
    fixApplyButton.addEventListener("click", () => {
      applyPendingFix();
    });
  }
  if (fixCancelButton) {
    fixCancelButton.addEventListener("click", () => {
      closeFixPreview();
      setStatus("Ready");
    });
  }
  if (fixModalNode) {
    fixModalNode.addEventListener("click", (event) => {
      if (event.target === fixModalNode) {
        closeFixPreview();
        setStatus("Ready");
      }
    });
  }
  const debouncedDiagnostics = debounce(() => runLintDiagnostics(monaco), 500);
  editor.onDidChangeModelContent(() => {
    debouncedDiagnostics();
  });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    saveCode();
  });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
    run("study");
  });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Enter, () => {
    check();
  });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.Enter, () => {
    run("exam");
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
  await loadCapabilities();

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
  bindToolbarButtons();
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
      minimap: { enabled: true },
      smoothScrolling: true,
      cursorBlinking: "blink",
      bracketPairColorization: { enabled: true },
      autoClosingBrackets: "always",
      autoClosingQuotes: "always",
      formatOnPaste: true,
      acceptSuggestionOnEnter: "on",
      fontSize: 14,
    });
    monaco.editor.setTabFocusMode(false);
    if (hoverProviderDisposable) {
      hoverProviderDisposable.dispose();
    }
    hoverProviderDisposable = monaco.languages.registerHoverProvider("python", {
      provideHover: function (model, position) {
        if (!editor || model !== editor.getModel()) {
          return null;
        }
        const found = latestDiagnostics.find((diag) => {
          if (position.lineNumber < diag.startLineNumber || position.lineNumber > diag.endLineNumber) {
            return false;
          }
          if (position.lineNumber === diag.startLineNumber && position.column < diag.startColumn) {
            return false;
          }
          if (position.lineNumber === diag.endLineNumber && position.column > diag.endColumn) {
            return false;
          }
          return true;
        });
        if (!found) {
          return null;
        }
        const textCode = found.code ? `[${found.code}] ` : "";
        return {
          range: {
            startLineNumber: found.startLineNumber,
            startColumn: found.startColumn,
            endLineNumber: found.endLineNumber,
            endColumn: found.endColumn,
          },
          contents: [{ value: `**${found.severityLabel}** ${textCode}${found.message}` }],
        };
      },
    });

    try {
      initEvents(monacoRef);
    } catch (error) {
      showRunMessage(`js error: ${String(error)}`);
      stderrNode.textContent = String(error);
    }
    initBridgeAndCode(monacoRef);
  });
}

window.addEventListener("pywebviewready", () => {
  if (monacoRef) {
    initBridgeAndCode(monacoRef);
  }
});

startMonaco();
