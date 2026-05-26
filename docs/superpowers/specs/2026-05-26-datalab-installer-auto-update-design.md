# DataLab Installer-Based Auto Update Design

## Goal

Add a real installer-based update flow for DataLab on macOS and Windows while preserving the app's offline-friendly behavior. DataLab must not contact the network by default, and it must only download and run installer assets after the user has enabled automatic updates or manually requested an update check.

## Scope

This design covers:

- Manual update checks from the Help menu.
- User-enabled automatic update checks.
- Displaying release notes before installation.
- Downloading platform installers from GitHub Releases.
- Verifying installers with SHA-256 before execution.
- Launching platform installers with quiet installation arguments where supported.
- Showing update-complete information on the next launch.
- Updating the release build pipeline to publish installer assets and `updates.json`.

This design does not cover:

- Fully silent background installation without user authorization.
- Bypassing Windows UAC or macOS administrator prompts.
- Storing GitHub tokens or private credentials.
- Delta patching or binary-level incremental updates.
- Auto-updating Linux builds.

## User Decisions

- Automatic update means actual download and installation, not only opening the release page.
- The first version covers both macOS and Windows.
- Release assets should be platform installers, not zip archives used for self-overwrite.
- Windows installer: Inno Setup `.exe`.
- macOS installer: `pkgbuild` / `productbuild` `.pkg`.
- Installation should be as quiet as the platform allows, but only after user authorization.
- Update metadata uses `updates.json` plus SHA-256.
- UI uses the existing Help menu plus a compact update dialog.

## Current State

DataLab already has a Qt-free update checker in `shared/update_checker.py`. It reads GitHub latest-release metadata, compares versions, and converts network failures into an `unavailable` status. The desktop app currently exposes `项目主页` / `Project Homepage` and `检查更新` / `Check for Updates` in the Help menu. The existing update dialog can tell the user whether a newer version exists, but it does not parse machine-readable installer metadata, download installers, verify them, or run platform installers.

The existing `SettingsStore` centralizes QSettings access and enforces a plaintext key namespace allowlist. Update preferences should use a new `Update/` namespace and must store only non-sensitive values.

## Architecture

The update system is split into five focused units.

### 1. Update Check Layer

`shared/update_checker.py` remains the Qt-free GitHub release client.

Responsibilities:

- Fetch latest GitHub Release metadata.
- Compare release version with current DataLab version.
- Preserve existing graceful offline behavior.
- Expose release asset metadata needed by higher layers.

It must not:

- Import Qt.
- Choose a platform installer.
- Download or execute installers.

### 2. Update Manifest Layer

Create `shared/update_manifest.py`.

Responsibilities:

- Parse `updates.json`.
- Validate `schema_version`, `version`, `published_at`, `release_url`, `notes`, and `assets`.
- Verify the manifest version matches the GitHub release tag version.
- Select the current platform asset:
  - macOS: `macos`
  - Windows x64: `windows-x64`
- Validate asset name, SHA-256, download URL, and install arguments.

If the manifest is missing, malformed, incompatible with the release tag, or missing the current platform, DataLab must not automatically install. It should fall back to showing release notes and offering to open the GitHub release page.

### 3. Download and Verification Layer

Create `shared/update_download.py`.

Responsibilities:

- Download only the installer asset selected by the manifest layer.
- Store downloads in a safe user cache or temporary update directory, not in the repository.
- Report progress to the desktop controller.
- Compute SHA-256 for the downloaded installer.
- Delete the installer if SHA-256 verification fails.

It must not:

- Execute the installer.
- Choose assets by guessing filenames.
- Trust HTTPS alone for automatic installation.

### 4. Platform Installer Layer

Create `app_desktop/update_installer.py`.

Responsibilities:

- Accept only a verified local installer path and validated install arguments.
- Windows:
  - Accept only `.exe` installers selected for `windows-x64`.
  - Run Inno Setup with quiet arguments such as `/VERYSILENT` and `/NORESTART`.
- macOS:
  - Accept only `.pkg` installers selected for `macos`.
  - Run `/usr/sbin/installer -pkg <path> -target /`.
- Return a clear success/failure result for starting the installer.

It must not:

- Bypass UAC or macOS administrator prompts.
- Delete or overwrite the running application itself.
- Run an installer whose SHA-256 has not been verified.

### 5. Desktop Controller Layer

Create `app_desktop/update_controller.py` and keep UI message construction separate where useful.

Responsibilities:

- Wire Help menu actions.
- Persist automatic update settings, last check time, skipped version, cached release notes, and last seen app version.
- Run manual checks on demand.
- Run automatic checks only when the user enabled them and the throttle window has elapsed.
- Keep automatic offline failures quiet.
- Display update dialogs with release notes.
- Drive download, verification, installer launch, and app exit.
- Show update-complete information after the next launch when the app version changes.

## Release Metadata

Each auto-installable GitHub Release must include `updates.json`.

Example:

```json
{
  "schema_version": 1,
  "version": "2.2.0",
  "published_at": "2026-05-26T00:00:00Z",
  "release_url": "https://github.com/yilibinbin/DataLab/releases/tag/v2.2.0",
  "notes": "Added installer-based automatic updates.",
  "assets": {
    "macos": {
      "name": "DataLab-2.2.0-macOS.pkg",
      "sha256": "64 hex chars",
      "install_args": ["-pkg", "{path}", "-target", "/"]
    },
    "windows-x64": {
      "name": "DataLab-2.2.0-Windows-x64.exe",
      "sha256": "64 hex chars",
      "install_args": ["/VERYSILENT", "/NORESTART"]
    }
  }
}
```

Validation rules:

- `schema_version` must be `1`.
- `version` must match the GitHub release tag after normalizing a leading `v`.
- `release_url` must point to the same GitHub release.
- The selected asset name must exist in the GitHub release assets.
- The selected asset URL must come from that release asset, not from arbitrary manifest text.
- `sha256` must be exactly 64 lowercase or uppercase hexadecimal characters.
- Install arguments must come from the manifest but are validated against the platform backend. `{path}` is replaced only by the verified local installer path.

## User Flow

### Manual Check

The user selects Help -> `检查更新` / `Check for Updates`.

1. DataLab checks the latest GitHub Release.
2. If no newer version exists, it shows an "already up to date" message.
3. If a newer version exists, DataLab fetches `updates.json`.
4. If the manifest is valid and contains the current platform installer, DataLab shows an update dialog.
5. If the manifest is missing or invalid, DataLab shows release notes and offers to open the release page.

### Automatic Check

The user enables Help -> `自动更新` / `Automatic Updates`.

1. DataLab persists this opt-in setting.
2. On later launches, DataLab delays the startup check briefly so the main window can appear.
3. DataLab checks at most once per throttle window, initially 24 hours.
4. Offline or GitHub failures during automatic checks do not show modal errors.
5. If a valid update is available and the version is not skipped, DataLab shows the same update dialog as the manual flow.

### Update Dialog

The update dialog shows:

- Current version.
- Latest version.
- Published date.
- Release notes.
- Installer asset name.

Buttons:

- `立即更新` / `Update Now`
- `稍后` / `Later`
- `跳过此版本` / `Skip This Version`

`Later` dismisses the dialog for the current check. `Skip This Version` persists the skipped version and suppresses automatic prompts for that version. Manual checks may still show the skipped version because the user explicitly requested the check.

### Download, Verify, Install

After `Update Now`:

1. DataLab downloads the selected installer and shows progress.
2. DataLab computes SHA-256.
3. If verification fails, DataLab deletes the installer and cancels the update.
4. If verification succeeds, DataLab tells the user it is preparing to install and restart.
5. DataLab starts the platform installer with quiet arguments.
6. If installer launch succeeds, DataLab exits.
7. If installer launch fails, DataLab stays open and offers to open the release page.

### Update Complete Notice

On startup, DataLab compares the current app version with the last seen version in settings.

If the version changed:

- Show `DataLab 已更新到 X` / `DataLab has been updated to X`.
- Include cached release notes if they match the current version.
- Do not perform a network request solely to populate this notice.

## Security and Failure Handling

Default behavior:

- Automatic updates are off by default.
- Startup does not contact the network unless automatic updates were enabled.
- Manual checks are allowed to contact GitHub because the user explicitly requested them.

Execution safety:

- DataLab only executes installers declared in a valid `updates.json`.
- DataLab only executes installers whose SHA-256 matches the manifest.
- DataLab never runs arbitrary GitHub release assets chosen by filename guessing.
- DataLab does not store credentials.
- DataLab does not try to bypass OS security prompts.

Failure handling:

- Missing manifest: fall back to release page.
- Invalid manifest: fall back to release page.
- No current-platform installer: fall back to release page.
- Download failure: show error for manual flow; stay quiet for automatic flow unless already in an explicit update dialog.
- SHA-256 mismatch: delete file, cancel update, show error if user initiated install.
- Installer launch failure: keep DataLab open and offer release page.
- Installer runtime failure after DataLab exits: old version remains usable because DataLab did not self-delete.

## Packaging and Release Pipeline

### macOS

- PyInstaller continues to build `DataLab.app`.
- Add a `.pkg` packaging step using `pkgbuild` and, if needed, `productbuild`.
- Install target: `/Applications/DataLab.app`.
- Release asset name: `DataLab-<version>-macOS.pkg`.
- Future signing/notarization can be added without changing the updater contract.

### Windows

- PyInstaller continues to build the Windows application directory.
- Add an Inno Setup script to package that directory.
- Quiet install arguments: `/VERYSILENT /NORESTART`.
- Release asset name: `DataLab-<version>-Windows-x64.exe`.

### Release Assets

Each auto-installable release should publish:

- `DataLab-<version>-macOS.pkg`
- `DataLab-<version>-Windows-x64.exe`
- `updates.json`

Release notes must be generic and public-facing. They must not include local paths, local servers, SSH hostnames, temporary directories, or machine-specific build details.

## Settings

Add update keys under the `Update/` namespace:

- `Update/auto_update_enabled`
- `Update/last_checked_at`
- `Update/skipped_version`
- `Update/last_seen_current_version`
- `Update/cached_release_version`
- `Update/cached_release_notes`
- `Update/cached_release_url`
- `Update/cached_release_published_at`

Stored values are non-sensitive. They are suitable for QSettings plaintext storage.

## Testing Strategy

### Manifest Tests

- Valid manifest parses successfully.
- Invalid schema version is rejected.
- Manifest version mismatch is rejected.
- Missing platform asset is rejected.
- SHA-256 with wrong length or non-hex characters is rejected.
- Selected asset must exist in GitHub release assets.
- Platform selection maps macOS to `macos` and Windows x64 to `windows-x64`.

### Download Tests

- Successful fake download produces a file.
- Matching SHA-256 passes.
- Mismatched SHA-256 deletes the file.
- Download failures return clear errors.
- Download code does not write into the project directory.

### Desktop Controller Tests

- Help menu contains manual check and automatic update toggle.
- Automatic update toggle defaults off.
- Toggle state persists.
- Manual offline failure shows an error.
- Automatic offline failure is quiet.
- Update dialog includes release notes.
- `Skip This Version` suppresses automatic prompts for that version.
- `Update Now` starts download, verification, and installer launch flow.

### Installer Tests

- Windows command includes Inno quiet arguments.
- Windows backend rejects non-`.exe` installers.
- macOS command uses `/usr/sbin/installer -pkg <pkg> -target /`.
- macOS backend rejects non-`.pkg` installers.
- Installer launch failure does not exit DataLab.
- Installer launch success triggers the configured app-exit callback.

### Release Acceptance Tests

Before publishing a release that claims auto-update support:

- Build macOS `.pkg`.
- Build Windows Inno `.exe` on the Windows build host.
- Generate `updates.json` with correct SHA-256 values.
- Upload all assets to the same GitHub Release.
- From an older DataLab build, verify:
  - Startup does not check the network when automatic updates are off.
  - Manual update check shows release notes.
  - Current-platform installer downloads.
  - SHA-256 verification passes.
  - Installer launch command is correct.
  - Offline automatic check does not show an error.

## Acceptance Criteria

- DataLab does not contact the network at startup unless the user enabled automatic updates.
- Manual update checks still work.
- Update prompts show release notes before installation.
- DataLab only downloads and executes manifest-declared, platform-matched installers.
- SHA-256 verification is mandatory before installer execution.
- macOS and Windows each have a defined installer backend.
- Missing metadata or unsupported platforms degrade to opening the release page.
- Release packaging can generate `.pkg`, Inno `.exe`, and `updates.json`.
- Public release notes and updater dialogs do not expose local/private environment details.
