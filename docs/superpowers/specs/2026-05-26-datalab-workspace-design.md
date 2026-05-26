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
    └── plots/
        ├── plot-001.png
        └── plot-002.png
```

Short text such as result markdown, log text, CSV rows, and LaTeX source lives in `manifest.json`. Binary plot images live under `attachments/plots/`. This keeps the format self-contained while avoiding base64 blobs for images.

All text is UTF-8. JSON is written with `ensure_ascii=False`. The archive must not contain absolute paths as entry names.

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
    "ui": {},
    "data": {},
    "constants": {},
    "config": {},
    "result_snapshot": {}
  }
}
```

`schema` and `schema_version` control compatibility. `app.version` is diagnostic only and must not by itself block opening a file.

## Data Preservation

Input data is saved in two forms:

- `raw_text`: byte-faithful user/file text decoded as UTF-8 for audit and text-view restoration.
- `canonical_table`: normalized headers and cell strings for table restoration and stable hashing.

Example:

```json
"data": {
  "source_kind": "manual_table",
  "source_path": null,
  "source_path_label": null,
  "active_view": "table",
  "raw_text": "A\tB\n1\t2\n3\t4\n",
  "canonical_table": {
    "headers": ["A", "B"],
    "rows": [["1", "2"], ["3", "4"]]
  },
  "sha256": "sha256:3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7"
}
```

For file-based input, the original file content is embedded in `raw_text`, and the original path is metadata only. On open, DataLab must present it as an embedded snapshot of the original source, not as a live file dependency.

Constants follow the same pattern:

```json
"constants": {
  "enabled": true,
  "source_kind": "manual_table",
  "source_path": null,
  "active_view": "table",
  "raw_text": "ALPHA 7.2973525693(11)[-3]\n",
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
    "power_law": {},
    "levin": {},
    "richardson": {},
    "uncertainty_column": "A"
  },
  "error": {
    "formula": "",
    "method": "taylor",
    "order": 1,
    "mc_samples": 5000,
    "mc_seed": ""
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
    "parameters": [],
    "poly_degree": 3,
    "inverse_power": {"min": 1, "max": 3},
    "pade": {"m": 1, "n": 1},
    "log_axes": ""
  }
}
```

Opening a workspace replaces the whole single-window workspace state. It is not a partial import into the currently active mode.

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

On open, the UI must identify restored output as a saved snapshot. If the user changes inputs or calculation-affecting configuration, the result becomes stale and the UI shows:

- Chinese: `结果为保存的快照，当前输入或配置已更改，请重新计算。`
- English: `This is a saved result snapshot. Inputs or settings have changed; rerun to update.`

CSV, plots, and LaTeX remain visible while stale, but they are labeled as snapshots.

## Hashing

The workspace state hash binds result snapshots to the inputs and settings that produced them. The hash includes:

- canonical and raw input data
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
3. Reopen and validate the temporary ZIP, including `manifest.json`, required fields, and listed plot attachments.
4. Flush data to disk as far as the platform reasonably allows.
5. Atomically replace the target file.
6. On failure, leave the previous target untouched and report the error.

## Loading and Validation

Open protocol:

1. Check that the ZIP can be opened.
2. Read and validate `manifest.json`.
3. Check schema compatibility.
4. Verify required fields and listed attachments.
5. Restore UI state.
6. Restore result snapshot if present.
7. Mark workspace clean.

If `manifest.json` is missing or invalid, refuse to open. If a non-critical plot attachment is missing, open with a clear warning and omit that plot.

## Schema Compatibility

The app opens schema version 1 directly. Future older schemas are migrated through explicit migration functions before the UI restore step. Newer unsupported schemas are rejected with a clear message. Unknown fields in the current schema are preserved when possible, but not trusted for behavior.

`app.version` is informational. It can be shown in diagnostics, but it is not a compatibility gate.

## Module Boundaries

`shared/workspace_schema.py`

- Qt-free schema constants and validation.
- Migration entry point.
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
- Preserve raw input text and canonical table.
- Preserve constants raw text and table.
- Preserve result snapshot fields.
- Save plot attachments and verify hashes.
- Atomic save leaves the old file untouched on simulated write failure.
- Workspace hash changes when data/config changes and stays stable for display-only changes.

Desktop/static tests:

- File menu exposes workspace actions with bilingual labels.
- Existing LaTeX open/save actions remain scoped to `.tex`.
- Save/Open are guarded when a worker is running.
- Restore marks result snapshots as snapshot-only.
- Editing restored inputs marks the result stale.

Focused integration tests:

- Populate a desktop window offscreen, save `.datalab`, open it in a fresh window, and verify mode, data, key config, result text, log, LaTeX source, CSV rows, and plot presence.

## Open Implementation Notes

- Do not serialize `_last_result_payloads` directly.
- Do not reload original data paths on open.
- Do not automatically recompute on open.
- Do not save compiled PDF previews.
- Prefer a user-visible snapshot/stale indicator over silent degraded behavior.
