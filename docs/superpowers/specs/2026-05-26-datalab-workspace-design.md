# DataLab Single-Workspace File Design

## Intent

Add a self-contained DataLab workspace file so users can save the current desktop calculation state, reopen it later, and continue working without relying on external data-file paths. The first version is a single-window workspace snapshot, not a multi-cell notebook history.

## Scope

The workspace file uses the `.datalab` extension and is implemented as a ZIP container. It restores inputs, configuration, and the latest saved result snapshot without automatically recomputing. It stores LaTeX source and compile settings, but not compiled PDF snapshots.

Out of scope for the first version:

- Multi-cell notebook history.
- Automatic recomputation on open.
- Saving Python pickle, Qt objects, worker/job objects, or raw mpmath objects.
- Storing compiled PDFs.
- Web UI or CLI workspace support.

## User Workflow

The desktop app adds a `File` menu with:

- `New Workspace`
- `Open Workspace...`
- `Save Workspace`
- `Save Workspace As...`

`Open Recent` can be added later if needed. Existing LaTeX-tab open/save actions remain scoped to `.tex` files and must not be presented as workspace actions.

`Save Workspace` writes the current window state to the existing workspace path. If no path is bound, it behaves like `Save Workspace As...`. `Save Workspace As...` prompts for a `.datalab` file.

`Open Workspace...` replaces the current DataLab window workspace. If the current state has unsaved changes, the app prompts to save, discard, or cancel.

The window title shows workspace identity and dirty state:

- `DataLab - Untitled`
- `DataLab - analysis.datalab`
- `DataLab - analysis.datalab *`

## Runtime Guards

Save and open are not allowed while a calculation, fit, auto-fit, or batch-fit worker is running. The first version should disable the actions or show a clear message asking the user to wait or stop the running job. This avoids saving a mixed state such as new configuration with old results.

## Archive Layout

The ZIP container has a small stable layout:

```text
analysis.datalab
├── manifest.json
└── attachments/
    ├── sources/
    │   ├── input.bin
    │   └── constants.bin
    └── plots/
        ├── plot-001.png
        └── plot-002.png
```

Short text such as decoded input text, result markdown, log text, CSV rows, and LaTeX source lives in `manifest.json`. Original source bytes and binary plot images live under `attachments/sources/` and `attachments/plots/`. This keeps the format self-contained while avoiding base64 blobs for binary data.

All manifest text is UTF-8. JSON is written with `ensure_ascii=False`. Archive entry names are normalized POSIX-style relative paths. The writer must only create `manifest.json` and files under `attachments/sources/` or `attachments/plots/`.

The reader treats the ZIP as hostile input and validates before restore:

- exactly one `manifest.json`
- no duplicate archive names after normalization
- no absolute paths, drive-prefixed paths, empty parts, `.` parts, or `..` parts
- no entries outside the allowed layout
- no symlink entries or external-attribute tricks that would write non-regular files
- maximum manifest size: 2 MiB
- maximum plot attachment count: 64
- maximum source attachment count: 2
- maximum individual plot attachment size: 20 MiB uncompressed
- maximum individual source attachment size: 128 MiB uncompressed
- maximum total uncompressed workspace size: 256 MiB
- plot attachments must be PNG files in v1 and must match the listed hash

## Manifest Shape

```json
{
  "schema": "datalab.workspace.v1",
  "schema_version": 1,
  "app": {
    "name": "DataLab",
    "version": "2.0.2"
  },
  "created_at": "2026-05-26T00:00:00Z",
  "updated_at": "2026-05-26T00:00:00Z",
  "workspace": {
    "title": "Untitled",
    "current_mode": "fitting",
    "language": "auto",
    "ui": {
      "main_tab": "results",
      "result_subtab": "plots",
      "selected_plot_index": 0,
      "plot_zoom": 1.0,
      "latex_editor": {
        "line_wrap": true,
        "cursor_line": 1,
        "cursor_column": 1
      }
    },
    "data": {
      "source_kind": "manual_table"
    },
    "constants": {
      "enabled": false
    },
    "config": {
      "common": {
        "mpmath_precision": 16
      }
    },
    "result_snapshot": {
      "present": false
    }
  }
}
```

`schema` and `schema_version` control compatibility. `app.version` is diagnostic only and must not by itself block opening a file.

`workspace.ui` stores only user-visible state needed to reopen the workspace in a familiar position: current mode/main tab, result subtab, selected plot index, plot zoom, and LaTeX editor cursor/wrap state. It does not store rendered PDF pages, PDF caches, window geometry, splitter positions, recent-file lists, or platform window state; those remain in existing app preferences such as `QSettings`.

## Data Preservation

Input data is saved in two forms:

- `decoded_text`: the text DataLab actually parsed and displayed after applying its loader decoding rules.
- `canonical_table`: normalized headers and cell strings for table restoration, stable hashing, and recomputation.

For file inputs, the original bytes are also embedded as an attachment when available. This preserves the source payload without depending on the original filesystem path. The manifest records the detected encoding, newline style, and original-byte hash so the UI can explain what was restored. Existing loader behavior such as UTF-8 BOM, GBK, and Latin-1 fallback is represented by metadata instead of pretending every source is UTF-8.

Example:

```json
"data": {
  "source_kind": "manual_table",
  "source_path": null,
  "source_path_label": null,
  "active_view": "table",
  "decoded_text": "A\tB\n1\t2\n3\t4\n",
  "encoding": "utf-8",
  "newline": "lf",
  "original_bytes_sha256": "sha256:3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7",
  "raw_bytes_path": "attachments/sources/input.bin",
  "canonical_table": {
    "headers": ["A", "B"],
    "rows": [["1", "2"], ["3", "4"]]
  },
  "sha256": "sha256:3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7"
}
```

For file-based input, the original file content is embedded at `raw_bytes_path` and the original path is metadata only. On open, DataLab must present it as an embedded snapshot of the original source, not as a live file dependency. For manual input, `raw_bytes_path` is normally null and `decoded_text` is the authoritative text-view content.

The two representations have explicit precedence:

- `canonical_table` is the authority for table restore, workspace hashing, and recomputation.
- `decoded_text` is the authority for audit display and text-view restore.
- the workspace hash covers both values plus encoding metadata and byte hash.
- if `decoded_text` and `canonical_table` disagree on load, v1 opens in degraded state, uses `canonical_table` for computation, uses `decoded_text` for the text view, and requires the warning flow described in Loading and Validation.

Constants follow the same pattern:

```json
"constants": {
  "enabled": true,
  "source_kind": "manual_table",
  "source_path": null,
  "active_view": "table",
  "decoded_text": "ALPHA 7.2973525693(11)[-3]\n",
  "encoding": "utf-8",
  "newline": "lf",
  "original_bytes_sha256": "sha256:9e0d19e62b63d157ee43b90d167e3a84f1e4fb7601dc4e9f35a7a9d53d5f3a20",
  "raw_bytes_path": null,
  "canonical_table": {
    "rows": [["ALPHA", "7.2973525693(11)[-3]"]]
  },
  "sha256": "sha256:9e0d19e62b63d157ee43b90d167e3a84f1e4fb7601dc4e9f35a7a9d53d5f3a20"
}
```

If constants are disabled, `enabled` is false and the remaining content may be empty.

## Configuration

Configuration is grouped by concern:

```json
"config": {
  "common": {
    "mpmath_precision": 16,
    "uncertainty_digits": 1,
    "generate_latex": false,
    "generate_plots": false,
    "verbose": false,
    "display_scientific": false,
    "display_digits": 10
  },
  "latex": {
    "output_path": "",
    "input_digits": 20,
    "use_dcolumn": false,
    "group_size": 3,
    "use_caption": false,
    "caption": "",
    "engine": "tectonic"
  },
  "extrapolation": {
    "method": "richardson",
    "custom_formula": "",
    "power_law": {
      "x_values": "",
      "custom_p": "",
      "seed_guesses": ""
    },
    "levin": {
      "variant": "u",
      "order": 2,
      "weight": "",
      "beta": "1"
    },
    "richardson": {
      "p": ""
    },
    "uncertainty_column": "A"
  },
  "error": {
    "formula": "",
    "method": "taylor",
    "order": 1,
    "mc_samples": 5000,
    "mc_seed": "",
    "mcmc_steps": 2000,
    "mcmc_burn_in": 500,
    "mcmc_seed": ""
  },
  "statistics": {
    "value_column": "A",
    "sigma_column": "",
    "mode": "mean",
    "sample": false,
    "weighted_variance": false
  },
  "fitting": {
    "model": "custom",
    "expression": "A*x**(-p) + C",
    "target_column": "B",
    "weighted": false,
    "mcmc_refine": false,
    "variables": [{"name": "x", "column": "A"}],
    "constraints_enabled": false,
    "parameters": [
      {"name": "A", "initial": "", "min": "", "max": ""},
      {"name": "p", "initial": "", "min": "", "max": ""},
      {"name": "C", "initial": "", "min": "", "max": ""}
    ],
    "poly_degree": 3,
    "inverse_power": {"min": 1, "max": 3},
    "pade": {"m": 1, "n": 1},
    "log_axes": {
      "x": false,
      "y": false
    }
  }
}
```

Opening a workspace replaces the whole single-window workspace state. It is not a partial import into the currently active mode.

The first implementation should capture concrete widget values rather than internal defaults. Empty strings mean the same thing as the current UI field being empty. Numeric fields should be serialized after normal UI validation; invalid in-progress edits should block save with a user-facing message instead of writing ambiguous data.

## Result Snapshot

Saved results are snapshots. They are useful for reopening and inspecting previous output, but they do not reconstruct internal typed result payloads. Full interactive payload-dependent behavior returns after the user reruns the calculation.

```json
"result_snapshot": {
  "present": true,
  "kind": "fit_single",
  "result_of_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "snapshot_only": true,
  "stale": false,
  "markdown": "## Fitting Results\n\nBest-fit parameters are shown below.",
  "log": "Fitting completed.",
  "csv": {
    "headers": ["batch", "section", "name", "value"],
    "rows": []
  },
  "latex_source": "\\\\begin{table}\\n\\\\centering\\n\\\\end{table}\\n",
  "plots": [
    {
      "path": "attachments/plots/plot-001.png",
      "role": "primary",
      "order": 0,
      "title": "Fit residuals",
      "format": "png",
      "sha256": "sha256:28f3d8f9f3e61d9f8f8b8d94b6f3f0d8f19f9c0f5f5e5f5f5e5f5f5e5f5f5e5f"
    }
  ]
}
```

If no calculation has run:

```json
"result_snapshot": {
  "present": false
}
```

On open, the UI must identify restored output as a saved snapshot. Result text, log text, CSV rows, plot images, and LaTeX source remain visible. Export actions that use saved snapshot artifacts are allowed. Controls that require typed in-memory payloads from `_last_result_payloads` are disabled or show a rerun-required message until the user recomputes. Recalculation replaces the snapshot with normal live result payload behavior.

Plot ownership is deterministic. The canonical source is the current result state at save time. If the result state references plot file paths, the saver reads every referenced path and embeds its bytes into `attachments/plots/` in role/order/index order. Missing plot files make save fail with a clear error unless the user explicitly chooses a degraded save path; degraded saves must mark the snapshot as degraded in the manifest.

If the user changes inputs or calculation-affecting configuration, the result becomes stale and the UI shows:

- Chinese: `结果为保存的快照，当前输入或配置已更改，请重新计算。`
- English: `This is a saved result snapshot. Inputs or settings have changed; rerun to update.`

CSV, plots, and LaTeX remain visible while stale, but they are labeled as snapshots.

## Hashing

The workspace state hash binds result snapshots to the inputs and settings that produced them. The hash includes:

- canonical and decoded input data
- source encoding/newline metadata and original-byte hashes
- constants state and content
- current mode
- current mode configuration
- common computation options that affect numerical output

The hash excludes display-only options such as font size and result decimal formatting. LaTeX/display options affect the saved output snapshot, but should not mark numerical results stale unless they change computation inputs.

## Dirty Tracking

The first version should prefer conservative dirty tracking. It is acceptable to mark dirty too often; it is not acceptable to miss important edits.

Dirty state is cleared after open or successful save. It is set by:

- input table/text changes
- constants table/text changes
- mode changes
- calculation option changes
- formula/model/statistics changes
- LaTeX source edits
- successful calculation completion

Close and open prompts use the dirty state to protect unsaved work.

## Atomic Save

Saving must not risk destroying the previous good workspace file.

Save protocol:

1. Build a plain Python workspace snapshot from the UI.
2. Write a complete ZIP to a temporary file in the destination directory.
3. Reopen and validate the temporary ZIP, including `manifest.json`, hostile-input limits, required fields, and listed plot attachments.
4. Flush data to disk as far as the platform reasonably allows.
5. Atomically replace the target file.
6. On failure, leave the previous target untouched and report the error.

The writer never copies arbitrary files into the archive. Only current UI state, embedded original source bytes, and result plot bytes are written.

## Loading and Validation

Open protocol:

1. Check that the ZIP can be opened.
2. Read and validate `manifest.json`.
3. Check schema compatibility.
4. Verify hostile-input limits, required fields, attachment hashes, and listed attachments.
5. Restore UI state.
6. Restore result snapshot if present.
7. Mark workspace clean.

If `manifest.json` is missing, duplicated, oversized, or invalid, refuse to open. If a non-critical plot attachment is missing or invalid and the rest of the workspace is usable, open with a clear warning and omit that plot. Any degraded open must mark the workspace degraded and dirty or read-only. Overwriting the same file after a degraded open requires an explicit warning; the preferred repair flow is `Save Workspace As...` to a new clean copy.

## Schema Compatibility

The app opens schema version 1 directly. For v1, `schema` must equal `datalab.workspace.v1` and `schema_version` must equal `1`. Newer unsupported schemas are rejected with a clear message. A future migration hook may be added when v2 exists, but v1 does not require a generic migration framework or unknown-field passthrough.

`app.version` is informational. It can be shown in diagnostics, but it is not a compatibility gate.

## Module Boundaries

`shared/workspace_schema.py`

- Qt-free schema constants and validation.
- Future migration hook.
- Hash helpers for canonical state.

`shared/workspace_io.py`

- Qt-free `.datalab` read/write.
- ZIP creation, validation, plot attachment handling, atomic save.
- No pickle.

`app_desktop/workspace_controller.py`

- Qt-facing controller.
- File menu actions.
- UI state capture and restore.
- Dirty tracking, stale-result banner, window title, user-facing dialogs.
- Converts Qt widgets into plain Python dict/list/string values before calling `shared`.

## Test Strategy

Qt-free tests:

- Write/read a minimal `.datalab` file.
- Reject missing or malformed manifest.
- Reject unsupported future schema.
- Preserve decoded input text and canonical table.
- Preserve constants decoded text and table.
- Preserve source encoding/newline metadata and original-byte hashes.
- Reject archive path traversal, duplicate names, duplicate manifests, oversized manifests, excessive attachments, oversized attachments, non-PNG plot attachments, symlink entries, and excessive total uncompressed size.
- Preserve result snapshot fields.
- Save plot attachments and verify hashes.
- Save plot role/order/index metadata and fail or explicitly degrade when a referenced current plot file is missing.
- Atomic save leaves the old file untouched on simulated write failure.
- Workspace hash changes when data/config changes and stays stable for display-only changes.
- Detect `decoded_text`/`canonical_table` disagreement and enter degraded restore behavior.

Desktop/static tests:

- File menu exposes workspace actions with bilingual labels.
- Existing LaTeX open/save actions remain scoped to `.tex`.
- Save/Open are guarded when a worker is running.
- Restore marks result snapshots as snapshot-only.
- Editing restored inputs marks the result stale.
- Snapshot-only controls that need typed payloads are disabled or show rerun-required.
- Degraded opens warn before overwriting the same workspace path.

Focused integration tests:

- Populate a desktop window offscreen, save `.datalab`, open it in a fresh window, and verify mode, data, key config, result text, log, LaTeX source, CSV rows, and plot presence.

## Open Implementation Notes

- Do not serialize `_last_result_payloads` directly.
- Do not reload original data paths on open.
- Do not automatically recompute on open.
- Do not save compiled PDF previews.
- Prefer a user-visible snapshot/stale indicator over silent degraded behavior.
