# DataLab Root LaTeX Compile and Splitter Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three release-blocking regressions: root-solving LaTeX must compile with `dcolumn` and obey digit grouping, LaTeX/PDF compilation must not freeze the GUI, and the left configuration pane must not be clipped by the main splitter.

**Architecture:** Keep the fixes narrowly scoped and reusable. Root-solving LaTeX continues to use the existing shared numeric formatter and `build_sisetup_block()` rather than inventing a new formatter; GUI compilation moves the blocking external compiler wait into a Qt worker while completion stays on the main thread; splitter behavior is enforced as a layout invariant whenever content width can change.

**Tech Stack:** Python 3, PySide6/Qt, pytest/pytest-qt, ruff, mpmath, existing `datalab_latex` helpers, external LaTeX engines (`xelatex`, `pdflatex`, `tectonic`).

---

## File Structure

- Modify: `app_desktop/root_latex_writer.py`
  - Responsibility: build root-solving LaTeX documents using shared DataLab numeric formatting and valid table preambles.
- Modify: `app_desktop/window_latex_pdf_mixin.py`
  - Responsibility: run LaTeX engine subprocesses in a cancellable Qt background worker and handle UI completion safely.
- Modify: `app_desktop/panels.py`
  - Responsibility: compute and enforce the main splitter left-pane minimum width.
- Modify: `app_desktop/window_i18n_mixin.py`
  - Responsibility: refresh layout constraints after language changes alter visible labels.
- Modify: `tests/test_root_latex_writer.py`
  - Responsibility: root LaTeX regression coverage for `dcolumn` preamble and `latex_group_size`.
- Create: `tests/test_latex_compile_worker.py`
  - Responsibility: Qt-free/static behavior tests for compile fallback detection and proof that the compile entrypoint starts a worker instead of calling `subprocess.run`.
- Create: `tests/test_desktop_latex_compile_ui.py`
  - Responsibility: pytest-qt smoke test that the compile button starts a worker and returns without doing synchronous compiler work.

## Non-Goals

- Do not change root-solving math, root uncertainty propagation, or output rows.
- Do not change the global LaTeX engine selection UI.
- Do not introduce a new precision/backend option.
- Do not add a single-instance lock or any packaging/release change in this bugfix plan.
- Do not stage `.superpowers/` or unrelated dirty files.

---

### Task 1: Root LaTeX dcolumn Regression Tests

**Files:**
- Modify: `tests/test_root_latex_writer.py`

- [x] **Step 1: Add failing tests for dcolumn preamble and group size**

Append these tests to `tests/test_root_latex_writer.py`:

```python
def test_root_latex_dcolumn_preamble_declares_column_type() -> None:
    rows = [{"input_row_index": "0", "root_index": "0", "name": "x", "value": "2", "backend": "mpmath"}]

    latex = build_root_latex_document(rows=rows, include_dcolumn=True, language="en")

    assert r"\usepackage{dcolumn}" in latex
    assert r"\newcolumntype{d}[1]{D{.}{.}{#1}}" in latex


def test_root_latex_dcolumn_respects_group_size_option() -> None:
    rows = [
        {
            "input_row_index": "0",
            "root_index": "0",
            "name": "x",
            "value": "1234567.890123",
            "uncertainty": "0.00000123",
            "backend": "mpmath",
            "mode": "scalar",
        }
    ]

    group_two = build_root_latex_document(rows=rows, include_dcolumn=True, group_size=2, language="en")
    group_three = build_root_latex_document(rows=rows, include_dcolumn=True, group_size=3, language="en")

    assert "1.23\\,45\\,67\\,89" in group_two
    assert "1.234\\,567\\,890" in group_three
    assert group_two != group_three
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_root_latex_writer.py
```

Expected before implementation:

```text
FAILED tests/test_root_latex_writer.py::test_root_latex_dcolumn_preamble_declares_column_type
FAILED tests/test_root_latex_writer.py::test_root_latex_dcolumn_respects_group_size_option
```

- [x] **Step 3: Do not commit yet**

Keep the RED tests in the worktree so Task 2 can make them pass.

---

### Task 2: Root LaTeX Writer Fix

**Files:**
- Modify: `app_desktop/root_latex_writer.py`
- Test: `tests/test_root_latex_writer.py`

- [x] **Step 1: Add valid dcolumn preamble lines**

In `build_root_latex_document()`, update the preamble list so the dcolumn branch mirrors fitting/common LaTeX writers:

```python
lines = [
    "\\documentclass{article}",
    "\\usepackage[UTF8]{ctex}" if language == "zh" else "",
    "\\usepackage{booktabs}",
    "\\usepackage{dcolumn}" if include_dcolumn else "",
    "\\newcolumntype{d}[1]{D{.}{.}{#1}}" if include_dcolumn else "",
    "\\usepackage{siunitx}",
    build_sisetup_block(group_size=group_size, include_dcolumn=include_dcolumn).rstrip(),
    "\\begin{document}",
]
```

- [x] **Step 2: Thread `group_size` into the root table**

In the `_root_table(...)` call inside `build_root_latex_document()`, pass the normalized group size:

```python
lines.extend(
    _root_table(
        rows,
        digits=max(1, int(digits)),
        uncertainty_digits=max(1, int(uncertainty_digits)),
        group_size=max(0, int(group_size)),
        language=language,
        include_dcolumn=include_dcolumn,
    )
)
```

Update `_root_table()` signature:

```python
def _root_table(
    rows: Sequence[Mapping[str, object]],
    *,
    digits: int,
    uncertainty_digits: int,
    group_size: int,
    language: str,
    include_dcolumn: bool,
) -> list[str]:
```

When `_root_table()` calls `_number_with_uncertainty(...)`, pass `group_size=group_size` for both `include_dcolumn=False` value-spec calculation and visible row rendering.

- [x] **Step 3: Pass group size to shared formatter**

Update `_number_with_uncertainty()` signature:

```python
def _number_with_uncertainty(
    value: object,
    uncertainty: object,
    *,
    digits: int,
    uncertainty_digits: int,
    group_size: int,
    include_dcolumn: bool,
) -> str:
```

Inside the `format_value_for_latex_file(...)` call, add:

```python
latex_group_size=group_size,
```

- [x] **Step 4: Run root LaTeX tests and verify GREEN**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_root_latex_writer.py
```

Expected:

```text
7 passed
```

- [x] **Step 5: Compile a real dcolumn root document**

Run:

```bash
tmpdir=$(mktemp -d /tmp/datalab-root-latex-smoke-XXXXXX)
PYTHONPATH=. TMPDIR_FOR_LATEX="$tmpdir" python - <<'PY'
import os
from pathlib import Path
from app_desktop.root_latex_writer import write_root_latex

out = Path(os.environ["TMPDIR_FOR_LATEX"]) / "root_dcolumn.tex"
write_root_latex(
    output_path=str(out),
    rows=[{
        "input_row_index": "0",
        "root_index": "0",
        "name": "x",
        "value": "1234567.890123",
        "uncertainty": "0.00000123",
        "backend": "mpmath",
        "mode": "scalar",
    }],
    caption="Root dcolumn smoke",
    digits=16,
    uncertainty_digits=2,
    group_size=2,
    include_dcolumn=True,
    language="en",
)
print(out)
PY
/opt/homebrew/bin/xelatex -interaction=nonstopmode -halt-on-error -output-directory="$tmpdir" "$tmpdir/root_dcolumn.tex"
ls -l "$tmpdir/root_dcolumn.pdf"
sed -n '1,24p' "$tmpdir/root_dcolumn.tex"
```

Expected:

```text
root_dcolumn.pdf exists
\usepackage{dcolumn}
\newcolumntype{d}[1]{D{.}{.}{#1}}
1.23\,45\,67...
```

---

### Task 3: Async LaTeX Compile Worker

**Files:**
- Modify: `app_desktop/window_latex_pdf_mixin.py`
- Modify: `app_desktop/window_extrapolation_mixin.py`
- Modify: `app_desktop/window.py`
- Create: `tests/test_latex_compile_worker.py`
- Create: `tests/test_desktop_latex_compile_ui.py`

- [x] **Step 1: Add compile worker data types with PDF path in the outcome**

Near `_TectonicInstallWorker`, add `from dataclasses import dataclass`, then add:

```python
@dataclass(frozen=True)
class _LatexEngineRun:
    engine: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _LatexCompileOutcome:
    runs: tuple[_LatexEngineRun, ...] = ()
    pdf_path: Path | None = None
    error: str | None = None
    timed_out: bool = False
    cancelled: bool = False
    used_fallback: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.runs) and self.runs[-1].returncode == 0 and not self.error


def _looks_like_plain_tex_output(output: str) -> bool:
    lower = output.lower()
    return "format=pdftex" in lower or "\\documentclass" in lower and "undefined control sequence" in lower
```

- [x] **Step 2: Add `_LatexCompileWorker` with guaranteed process cleanup**

Add `_LatexCompileWorker(QThread)` in `app_desktop/window_latex_pdf_mixin.py`. Its constructor must take `pdf_path: Path`, store it as `self._pdf_path`, and every emitted `_LatexCompileOutcome` must include `pdf_path=self._pdf_path`. The worker must kill the subprocess on timeout and in generic exception cleanup:

```python
class _LatexCompileWorker(QThread):
    completed = Signal(object)

    def __init__(self, *, target: Path, pdf_dir: Path, engine_name: str, engine_path: Path, pdf_path: Path, fallback_name: str | None = None, fallback_path: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self._target = target
        self._pdf_dir = pdf_dir
        self._engine_name = engine_name
        self._engine_path = engine_path
        self._pdf_path = pdf_path
        self._fallback_name = fallback_name
        self._fallback_path = fallback_path
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            proc.terminate()
```

Inside `run()`, emit outcomes like:

```python
self.completed.emit(_LatexCompileOutcome(runs=tuple(runs), pdf_path=self._pdf_path, cancelled=self._cancel_requested))
```

and in exception branches:

```python
except FileNotFoundError as exc:
    self.completed.emit(_LatexCompileOutcome(runs=tuple(runs), pdf_path=self._pdf_path, error=str(exc)))
except subprocess.TimeoutExpired:
    self.completed.emit(_LatexCompileOutcome(runs=tuple(runs), pdf_path=self._pdf_path, timed_out=True))
except Exception as exc:
    import traceback

    self.completed.emit(_LatexCompileOutcome(runs=tuple(runs), pdf_path=self._pdf_path, error=f"{exc}\n{traceback.format_exc()}"))
```

In `_run_engine()`, use `subprocess.Popen(...).communicate(timeout=timeout)` and kill the process before re-raising `TimeoutExpired`:

```python
except subprocess.TimeoutExpired:
    if proc.poll() is None:
        proc.kill()
    raise
finally:
    self._process = None
```

- [x] **Step 3: Start the worker from the GUI without lambda UI callbacks**

In `compile_latex_to_pdf()`, replace the synchronous `subprocess.run()` path with a non-modal `QProgressDialog` and `_LatexCompileWorker`. Pass `pdf_path=pdf_path` into the worker and connect the signal directly to the bound QWidget method:

```python
worker = _LatexCompileWorker(
    target=target,
    pdf_dir=pdf_dir,
    engine_name=engine,
    engine_path=engine_path,
    pdf_path=pdf_path,
    fallback_name=fallback if fallback_path is not None else None,
    fallback_path=fallback_path,
    parent=self,
)
self._latex_compile_worker = worker
self._latex_compile_progress = progress
self.latex_compile_button.setEnabled(False)
progress.canceled.connect(worker.request_cancel)
worker.completed.connect(self._on_latex_compile_completed)
worker.finished.connect(worker.deleteLater)
progress.show()
worker.start()
```

Do not use `worker.completed.connect(lambda outcome: ...)` because a Python lambda has no QObject receiver context and can execute GUI code from the worker thread.

- [x] **Step 4: Add completion handler that reads `pdf_path` from outcome**

Add:

```python
def _on_latex_compile_completed(self, outcome: _LatexCompileOutcome) -> None:
    progress = getattr(self, "_latex_compile_progress", None)
    if progress is not None:
        progress.close()
        progress.deleteLater()
    self._latex_compile_progress = None
    self._latex_compile_worker = None
    self.latex_compile_button.setEnabled(True)

    for run in outcome.runs:
        self._append_log(f"{run.engine} 输出 (returncode={run.returncode}):\n{run.stdout}\n{run.stderr}")

    if outcome.cancelled:
        self._append_log(self._tr("LaTeX 编译已取消。", "LaTeX compilation canceled."))
        return
    if outcome.timed_out:
        QMessageBox.critical(self, self._tr("编译失败", "Compilation Failed"), self._tr("LaTeX 编译超时。", "LaTeX compilation timed out."))
        return
    if outcome.error:
        self._append_log(outcome.error)
        QMessageBox.critical(self, self._tr("编译失败", "Compilation Failed"), outcome.error)
        return
    if outcome.succeeded:
        pdf_path = outcome.pdf_path
        if pdf_path is None:
            QMessageBox.critical(self, self._tr("编译失败", "Compilation Failed"), self._tr("缺少 PDF 输出路径。", "Missing PDF output path."))
            return
        self.last_pdf_path = pdf_path
        if self._render_pdf_preview(pdf_path, force_reload=True):
            QMessageBox.information(self, self._tr("编译完成", "Compilation Complete"), self._tr("PDF 已生成并加载到预览标签页。", "PDF generated and loaded in preview tab."))
        else:
            QMessageBox.information(self, self._tr("编译完成", "Compilation Complete"), self._tr(f"PDF 已生成于 {pdf_path}.", f"PDF generated at {pdf_path}."))
        return
    QMessageBox.critical(self, self._tr("编译失败", "Compilation Failed"), self._tr("LaTeX 编译失败，请查看日志并检查 pdflatex/xelatex 格式是否可用。", "LaTeX compilation failed; check logs and ensure pdflatex/xelatex formats are available."))
```

- [x] **Step 5: Include LaTeX compile worker in window lifecycle**

In `app_desktop/window_extrapolation_mixin.py::_has_running_worker()`, add:

```python
or (getattr(self, "_latex_compile_worker", None) and self._latex_compile_worker.isRunning())
```

In `_stop_current_worker()`, add:

```python
latex_worker = getattr(self, "_latex_compile_worker", None)
if latex_worker is not None and latex_worker.isRunning():
    latex_worker.request_cancel()
    stopped = True
```

In `app_desktop/window.py::closeEvent()`, include `latex_worker.wait(100)` in the graceful wait loop. In the force-terminate section, kill the child process before terminating the QThread:

```python
latex_worker = getattr(self, "_latex_compile_worker", None)
if latex_worker is not None and latex_worker.isRunning():
    latex_worker.request_kill()
    latex_worker.wait(500)
    if latex_worker.isRunning():
        latex_worker.terminate()
        latex_worker.wait()
```

- [x] **Step 6: Add worker behavior tests**

Create `tests/test_latex_compile_worker.py` with:

```python
def test_latex_compile_worker_runs_fallback_after_plain_tex_failure(monkeypatch) -> None:
    processes = [
        _FakeProcess(returncode=1, stdout="format=pdftex"),
        _FakeProcess(returncode=0, stdout="ok"),
    ]
    monkeypatch.setattr("app_desktop.window_latex_pdf_mixin.subprocess.Popen", lambda *args, **kwargs: processes.pop(0))
    worker = _LatexCompileWorker(target=Path("report.tex"), pdf_dir=Path("."), engine_name="pdflatex", engine_path=Path("/bin/pdflatex"), pdf_path=Path("report.pdf"), fallback_name="xelatex", fallback_path=Path("/bin/sh"))
    outcomes = []
    worker.completed.connect(outcomes.append)

    worker.run()

    assert outcomes[0].succeeded is True
    assert outcomes[0].used_fallback == "xelatex"
    assert [run.engine for run in outcomes[0].runs] == ["pdflatex", "xelatex"]
    assert outcomes[0].pdf_path == Path("report.pdf")
```

Also add a timeout test with a fake process whose `communicate()` raises `subprocess.TimeoutExpired`; assert `process.killed is True`, `process.waited is True`, and `outcomes[0].timed_out is True`. Add a generic communicate-error test and assert the same `killed`/`waited` cleanup before checking the emitted error text.

- [x] **Step 7: Add desktop compile entry and lifecycle smoke**

Create `tests/test_desktop_latex_compile_ui.py` with a dummy worker that has `start()`, `isRunning()`, `request_cancel()`, and `deleteLater()` methods. Add tests that assert:

```python
window.compile_latex_to_pdf()
assert worker.started is True
assert worker.kwargs["pdf_path"] == tmp_path / "report.pdf"
assert window._latex_compile_worker is worker
assert window.latex_compile_button.isEnabled() is False

assert window._has_running_worker() is True
window._stop_current_worker()
assert worker.cancelled is True
```

Each test must set `worker.started = False`, clear `window._latex_compile_worker`, and close `window._latex_compile_progress` in a `finally` block so pytest-qt teardown does not block on the running-task close confirmation.

- [x] **Step 8: Run focused compile tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_desktop_latex_compile_ui.py tests/test_latex_compile_worker.py
```

Expected:

```text
6 passed
```

---

### Task 4: Splitter Minimum-Width Invariant

**Files:**
- Modify: `app_desktop/panels.py`
- Modify: `app_desktop/window_i18n_mixin.py`
- Test: `tests/test_desktop_root_solving_ui.py`
- Test: `tools/scan_desktop_gui_schema.py`

- [x] **Step 1: Reject restored splitter states that violate the current left minimum**

In `app_desktop/panels.py`, update the `restoreState(...)` acceptance condition:

```python
if (
    restored_ok
    and len(sizes_after) == splitter.count()
    and all(s >= 0 for s in sizes_after)
    and sum(sizes_after) > 0
    and sizes_after[0] >= getattr(self, "_main_splitter_left_min_width", 0)
):
    pass
else:
    splitter.setSizes(pre_restore_sizes)
    settings.save_bytes(KEY_MAIN_SPLITTER_STATE, None)
```

- [x] **Step 2: Clamp current splitter size whenever the minimum is refreshed**

In `_refresh_main_splitter_left_min_width()`, after `left_scroll.setMinimumWidth(left_min_width)`, add:

```python
splitter = getattr(self, "_main_splitter", None)
if splitter is None or splitter.count() < 2:
    return
sizes = splitter.sizes()
if not sizes or sizes[0] >= left_min_width:
    return
total = max(sum(sizes), left_min_width + 1)
right_width = max(1, total - left_min_width)
splitter.setSizes([left_min_width, right_width])
```

- [x] **Step 3: Refresh layout after language changes**

In `app_desktop/window_i18n_mixin.py::_apply_language()`, after root help/text refresh, add:

```python
if hasattr(self, "_refresh_main_splitter_left_min_width"):
    self._refresh_main_splitter_left_min_width()
```

- [x] **Step 4: Run splitter-focused GUI tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q \
  tests/test_desktop_root_solving_ui.py::test_main_splitter_clamps_left_panel_to_config_minimum \
  tests/test_desktop_root_solving_ui.py::test_main_splitter_minimum_prevents_left_horizontal_scrollbar \
  tests/test_desktop_root_solving_ui.py::test_main_splitter_left_minimum_refreshes_after_mode_visibility
```

Expected:

```text
3 passed
```

- [x] **Step 5: Run the GUI schema scan**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/scan_desktop_gui_schema.py
```

Expected JSON contains:

```json
{
  "checks": {
    "left_panel_no_horizontal_scrollbar": true
  },
  "issues": []
}
```

---

### Task 5: Final Quality Gates

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`
- No broad staging.

- [x] **Step 1: Run focused regression suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q \
  tests/test_root_latex_writer.py \
  tests/test_latex_compile_worker.py \
  tests/test_desktop_latex_compile_ui.py \
  tests/test_desktop_root_solving_ui.py \
  tests/test_desktop_gui_schema_scan.py \
  tests/test_latex_tables_common_unit.py \
  tests/test_fitting_latex_writer.py
```

Expected:

```text
68 passed
```

- [x] **Step 2: Run focused static checks**

Run:

```bash
PYTHONPATH=. ruff check \
  app_desktop/root_latex_writer.py \
  app_desktop/window_latex_pdf_mixin.py \
  app_desktop/panels.py \
  app_desktop/window_i18n_mixin.py \
  tests/test_root_latex_writer.py \
  tests/test_latex_compile_worker.py \
  tests/test_desktop_latex_compile_ui.py \
  tests/test_desktop_root_solving_ui.py \
  tests/test_desktop_gui_schema_scan.py
```

Expected:

```text
All checks passed!
```

- [x] **Step 3: Run compile checks**

Run:

```bash
python3 -m compileall -q \
  app_desktop/root_latex_writer.py \
  app_desktop/window_latex_pdf_mixin.py \
  app_desktop/panels.py \
  app_desktop/window_i18n_mixin.py \
  tests/test_root_latex_writer.py \
  tests/test_latex_compile_worker.py \
  tests/test_desktop_latex_compile_ui.py
```

Expected: no output and exit code `0`.

- [x] **Step 4: Run diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected:

```text
git diff --check exits 0
status shows only this plan's allowlisted source/test/planning files plus any pre-existing untracked .superpowers/
```

- [x] **Step 5: Commit only allowlisted files after review approval**

Stage only these files:

```bash
git add \
  app_desktop/root_latex_writer.py \
  app_desktop/window_latex_pdf_mixin.py \
  app_desktop/panels.py \
  app_desktop/window_i18n_mixin.py \
  app_desktop/window_extrapolation_mixin.py \
  app_desktop/window.py \
  tests/test_root_latex_writer.py \
  tests/test_latex_compile_worker.py \
  tests/test_desktop_latex_compile_ui.py \
  docs/superpowers/plans/2026-06-05-datalab-root-latex-compile-splitter-fix-plan.md
git diff --cached --name-only
git commit -m "fix: repair root latex compile and splitter layout"
```

Expected staged names must not include `.superpowers/`, ignored local planning files (`task_plan.md`, `findings.md`, `progress.md`), or unrelated files.

---

## Self-Review

- Spec coverage:
  - Root-solving LaTeX `dcolumn` compile failure: covered by Tasks 1-2 and real `xelatex` smoke.
  - Digit spacing/group-size failure: covered by Tasks 1-2 with `group_size=2` vs `3`.
  - Tectonic/LaTeX GUI freeze: covered by Task 3 moving external compiler wait to `_LatexCompileWorker`.
  - Splitter left-panel clipping: covered by Task 4 restoring/clamping and language refresh.
  - Code quality: covered by Task 5 focused tests, GUI scan, ruff, compileall, diff hygiene, strict allowlist staging.
- Placeholder scan:
  - No `TBD`, `TODO`, or "implement later" instructions.
  - Each code-changing step names exact files and concrete code blocks.
- Type consistency:
  - `_LatexCompileOutcome`, `_LatexEngineRun`, `_LatexCompileWorker`, and `_looks_like_plain_tex_output` are introduced before use.
  - `group_size` is threaded consistently from `build_root_latex_document()` to `_root_table()` to `_number_with_uncertainty()`.
  - Splitter refresh function name matches existing `ExtrapolationWindow._refresh_main_splitter_left_min_width()` forwarding method.

## External Review Status

- Gemini adversarial review round 1: REJECT. Accepted high finding: direct lambda connection from worker signal to GUI completion risks running GUI mutations off the main thread. Accepted low finding: generic exception cleanup should kill any active compiler subprocess.
- Claude adversarial review round 1: REJECT. Accepted high finding: `_LatexCompileWorker` must participate in `_has_running_worker()`, `_stop_current_worker()`, and `closeEvent()` shutdown handling. Accepted medium finding: worker fallback/timeout/cancel behavior needs behavioral tests, not only source-text assertions. Accepted low finding: source-text assertion is brittle and should be replaced by behavior tests.
- Gemini adversarial review round 2: CONTESTED. Accepted high finding: force-terminating the LaTeX QThread can leak the external compiler process. Accepted low thread-affinity recommendation was rejected for current project context because the direct bound QWidget method is the Qt main-thread receiver, but the plan keeps the lambda ban.
- Claude adversarial review round 2: REJECT. Accepted high finding: fallback engine resolution must not call the side-effecting `_ensure_latex_engine()` before the primary compile actually fails. Accepted medium finding: generic non-timeout `communicate()` exceptions must kill the process before clearing `self._process`. Accepted low finding: force-terminate path should request-kill the child process first.
- Gemini adversarial review round 3: PASS with one accepted low finding on a microscopic cancel-before-process-assignment race. Fixed by killing the just-started process immediately after assignment when `_cancel_requested` is already true, with a regression test.
- Claude adversarial review round 3: PASS with low-only notes; no blocking findings remained.
- Gemini final narrow re-review: REJECT on plan text/code cleanup. Accepted finding: Task 3 Step 5 must explicitly say `request_kill()` before QThread termination. Accepted low finding: after `proc.kill()` on timeout/generic communicate errors, call `proc.wait()` to reap the child process.
- Gemini final narrow re-review: REJECT on plan/add-list consistency and redundant cleanup helper. Accepted finding: Task 5 `git add` must include `app_desktop/window.py` and `app_desktop/window_extrapolation_mixin.py`. Accepted low finding: remove now-dead `_kill_running_process()` calls/helper because cleanup lives in `_run_engine()`.
- Claude final re-review: PASS. Gemini direct diff review after redundant-cleanup removal found one plan command syntax issue: the final `git add` path had a trailing backslash. Fixed.
- Current revision addresses all accepted findings: fallback uses `_resolve_latex_engine_no_prompt()`, `_run_engine()` kills and waits for timeout/generic/cancel-race cases, closeEvent calls `request_kill()` before any QThread termination, the allowlist includes all modified source/test/plan files, and tests cover these behaviors.
