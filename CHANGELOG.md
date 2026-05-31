# Changelog

All notable changes to DataLab are documented in this file.
DataLab follows [Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

## [2.5.0] — 2026-05-31

### Changed
- Refined fitting workflows around explicit model selection and shared
  fitting input normalization.

### Fixed
- Preserved custom fitting constants during parameter normalization.
- Rejected ambiguous or missing CLI batch fit models instead of changing
  fitting behavior silently.
- Normalized fitting constants, parameter names, and uncertainty inputs
  consistently across desktop, web, and CLI paths.
- Preserved weighted-fitting uncertainty semantics and rejected invalid
  non-finite uncertainties.
- Made checked-in workspace examples byte-stable across Python and zlib
  versions.
- Restored custom parameter constraints before loading workspace parameter
  rows, including legacy workspace formats.
- Hardened implicit fitting derivative and sequence length guards.

### Removed
- Removed the AIC/BIC model-selection workflow from desktop, web, CLI,
  and public fitting exports. Use explicit fitting models instead.

## [2.4.0] — 2026-05-29

### Added
- Added desktop parallel compute preferences for execution mode, worker
  count, reserved CPU cores, nested parallelism policy, and backend
  rollback gates.
- Added a shared parallel backend for serial, thread, process, and
  killable subprocess execution.

### Changed
- Routed sampling and self-consistent fitting subprocess execution
  through the shared backend while preserving rollback behavior.

### Fixed
- Cleaned up active fitting subprocesses during shutdown and made
  multiprocessing child shutdown handling safer.

## [2.3.2] — 2026-05-29

### Added
- Added rendered formula previews for custom formulas, error
  propagation, custom fitting, and self-consistent fitting editors.
- Added shared custom and self-consistent fitting parameter and
  constants editors with automatic parameter detection.

### Changed
- Unified constants and parameter editing across fitting workflows so
  table and text drafts, constraints, and workspace state use shared
  components.

### Fixed
- Preserved custom and self-consistent fitting parameter and constants
  drafts in workspace files, including disabled editors and inactive
  text-view drafts.
- Passed custom fitting constants through manual and worker execution
  paths.

## [2.3.1] — 2026-05-28

### Changed
- Refined the self-consistent / implicit fitting workflow with a
  formula-first editor, independent parameter and constants tables, and
  clearer generic defaults.
- Moved self-consistent fitting execution through a subprocess boundary
  so long implicit fits can be cancelled or timed out more reliably.

### Fixed
- Preserved high-precision implicit parameter values through workspace
  restore and worker serialization.
- Preserved draft implicit constants rows in workspace files, including
  duplicate or incomplete rows that should remain editable.
- Marked workspaces dirty when persisted implicit fitting controls are
  changed.

## [2.3.0] — 2026-05-28

### Added
- Added a general self-consistent / implicit fitting model for user
  defined variables, implicit equations, and output expressions.
- Added a quantum-defect implicit-model preset built on the general
  self-consistent fitting mechanism.
- Preserved self-consistent fitting setup and results in `.datalab`
  workspace files and fitting reports.

### Changed
- Improved update dialogs with localized platform-specific release
  messages and visible download progress including transfer speed.

### Fixed
- Preserved the native macOS application icon path so packaged Dock
  icons keep the expected rounded app appearance.
- Kept generic implicit-model parameter inference independent from the
  quantum-defect preset constants.

## [2.2.1] — 2026-05-28

### Added
- Registered `.datalab` workspace files with the desktop app on macOS
  and Windows installers.
- Added startup and file-open handling so opening a `.datalab`
  workspace from the operating system restores the saved workspace
  directly.

### Fixed
- Preserved unsaved-work prompts and busy-worker guards when opening a
  workspace from the operating system.
- Hardened repeated or unsupported file-open events so failed opens do
  not block later valid workspace opens.

## [2.2.0] — 2026-05-26

### Added
- Added a user-authorized installer-based update flow with release-note
  prompts, offline-friendly automatic checks, installer integrity
  verification, and platform installer packaging hooks.

## [2.1.0] — 2026-05-26

### Added
- Desktop app now supports self-contained `.datalab` workspace files
  for saving and reopening a calculation session.
- Workspace files preserve embedded input data, constants, current
  configuration, LaTeX source, CSV/result text, and saved plot
  snapshots without depending on the original input file paths.
- File menu now includes New, Open, Save, and Save As workspace
  actions with dirty-state window titles and prompts for unsaved work.

### Changed
- Restored workspace results are clearly treated as saved snapshots:
  users can inspect and export saved artifacts, and recomputation
  restores full live result interactivity.

### Security
- `.datalab` files are validated as hostile ZIP input, including
  schema checks, path traversal rejection, duplicate-entry detection,
  attachment limits, and plot/source hash validation.

## [2.0.2] — 2026-05-02

### Added
- Desktop Help menu now links to the public project homepage and checks
  GitHub Releases for newer DataLab versions.
- About dialog now uses a native rich-text presentation with the DataLab
  icon, repository link, license link, and desktop documentation link.

### Fixed
- PyInstaller-frozen desktop builds no longer reopen extra GUI windows
  when automatic fitting starts multiprocessing worker processes.
- Frozen desktop packages now bundle `pyproject.toml` and the app icon
  image so version display, update checks, and About branding work in
  packaged apps.
- Update checker now prefers bundled version metadata over stale
  installed package metadata, so released apps do not falsely report
  themselves outdated.

## [2.0.0] — 2026-04-26

First public release. Desktop is shipped as one-click installable
macOS / Windows bundles with Python, PySide6, and the full scientific
stack embedded — no external runtime needed.

### Added
- **Sequence extrapolation** — Richardson, Wynn-ε, Levin u-transform,
  custom power-law formulas
- **Curve fitting** — automatic model selection by AIC/BIC + optional
  MCMC posterior refinement
- **Error propagation** — `1.23(4)[-2]` compact uncertainty syntax +
  SymPy-based symbolic partial derivatives
- **Weighted statistics** — weighted mean, standard error, RMS
  dispersion
- **LaTeX export + inline PDF preview** — Tectonic engine by default
  (auto-downloaded to `~/.datalab/bin/`, no TeX Live install needed);
  pdflatex / xelatex still selectable
- **Bilingual UI** — 中文 / English toggleable from the menu
- **5 bundled example files** under `examples/` covering all four
  modes
- **Two frontends, one core** — PySide6 desktop + Flask web app share
  the same `extrapolation_methods/`, `fitting/`, `datalab_latex/`,
  `shared/` packages

### Fixed
- siunitx v2 / v3 (incl. Tectonic-bundled v3.0.49) full
  compatibility — `digit-group-size` guard date = 2024-01-01
- Pathological fit parameters no longer produce 21-digit integers
  like `4(1543551156637860)[\text{-18}]` in LaTeX output
- LaTeX tab — line-number gutter + engine selector moved to the
  semantically correct location (was previously inside the compute
  panel)
- Data table — equal column widths + add/remove row & column
  buttons (previously could only add)
- Windows GBK / CP936 encoded `.tex` files now load correctly
- MCMC pre-flight + health checks prevent NaN walkers from
  contaminating the chain
- `DataLab.spec` paths are portable — any clone can build, not just
  the original author's machine

### Tests
- `pytest -q` → **769 passed, 11 skipped**
- Coverage spans high-precision Mathematica reference values, all four
  modes end-to-end, and every LaTeX output path

[Unreleased]: https://github.com/yilibinbin/DataLab/compare/v2.5.0...HEAD
[2.5.0]: https://github.com/yilibinbin/DataLab/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/yilibinbin/DataLab/compare/v2.3.2...v2.4.0
[2.3.2]: https://github.com/yilibinbin/DataLab/compare/v2.3.1...v2.3.2
[2.3.1]: https://github.com/yilibinbin/DataLab/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/yilibinbin/DataLab/compare/v2.2.1...v2.3.0
[2.2.1]: https://github.com/yilibinbin/DataLab/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/yilibinbin/DataLab/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/yilibinbin/DataLab/compare/v2.0.2...v2.1.0
[2.0.2]: https://github.com/yilibinbin/DataLab/compare/v2.0.0...v2.0.2
[2.0.0]: https://github.com/yilibinbin/DataLab/releases/tag/v2.0.0
