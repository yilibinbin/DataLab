# DataLab Installer-Based Auto Update Design

## Goal

Add a real installer-based update flow for DataLab on macOS and Windows while preserving the app's offline-friendly behavior. DataLab must not contact the network by default, and it must only download and run installer assets after the user has enabled automatic updates or manually requested an update check.

## Scope

This design covers:

- Manual update checks from the Help menu.
- User-enabled automatic update checks.
- Displaying release notes before installation.
- Downloading platform installers from GitHub Releases.
- Verifying installer integrity with SHA-256 before execution.
- Requiring platform signing/notarization checks as a release gate.
- Launching platform installers with safe arguments constructed by DataLab.
- Showing best-effort update-complete information on the next launch.
- Updating the release build pipeline to publish installer assets and `updates.json`.

This design does not cover:

- Fully silent background installation without user authorization.
- Bypassing Windows UAC, Windows SmartScreen, macOS Gatekeeper, or macOS administrator prompts.
- Storing GitHub tokens or private credentials.
- Delta patching or binary-level incremental updates.
- Rollback after a completed installer overwrite.
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

## Trust Model

The updater has two separate checks:

- **Integrity:** SHA-256 confirms the downloaded bytes match the release metadata. It protects against corrupted downloads, CDN mix-ups, and accidental asset replacement.
- **Authenticity:** SHA-256 inside the same GitHub Release is not a trust root. A compromised release publisher could replace both `updates.json` and the installer with matching hashes. Authenticity must come from platform signing and release controls.

For the first installer-based release, DataLab treats GitHub Release ownership plus platform signing as the trust root:

- Windows installer assets must be Authenticode-signed before upload. Release acceptance verifies the signature publisher and that Windows does not report an unknown publisher in a clean VM.
- macOS `.pkg` assets must be signed with a Developer ID Installer certificate and notarized before upload. Release acceptance verifies Gatekeeper/notarization in a clean macOS environment.
- If signing/notarization is missing for a platform, that platform must not be advertised as auto-installable; DataLab should fall back to the release page.

Future hardening can add a detached signature for `updates.json` using a public key embedded in DataLab. That is not required for the first version, but the spec must not claim SHA-256 alone proves authenticity.

## Architecture

The update system is split into four focused units. The Qt-free payload code owns metadata parsing, platform selection, download, and integrity verification because those operations form one linear data contract. Desktop code owns UI, state, and installer execution.

### 1. Update Check Layer

`shared/update_checker.py` remains the Qt-free GitHub release client.

Responsibilities:

- Fetch latest GitHub Release metadata.
- Compare release version with current DataLab version.
- Preserve existing graceful offline behavior.
- Expose the release tag, release URL, release body, published date, and release asset list.

It must not:

- Import Qt.
- Choose a platform installer.
- Download or execute installers.

### 2. Update Payload Layer

Create `shared/update_payload.py`.

Responsibilities:

- Locate `updates.json` by exact asset name in the GitHub Release asset list.
- Download `updates.json` only from the `browser_download_url` returned by the GitHub Release API.
- Enforce a small manifest size limit, initially 64 KiB.
- Parse and validate `updates.json`.
- Verify the manifest version matches the GitHub release tag after normalizing a leading `v`.
- Select the current platform asset:
  - macOS universal/pkg path: `macos`
  - Windows x64: `windows-x64`
  - Future keys may include `macos-arm64`, `macos-x86_64`, and `windows-arm64`.
- Verify the selected installer asset name exists in the same GitHub Release asset list.
- Download the selected installer only from the matching release asset `browser_download_url`.
- Enforce expected `size_bytes`, a hard maximum installer size, a connection timeout, a stall timeout, and a total timeout.
- Store downloads under a platform user cache directory, not in the repository.
- Compute SHA-256 after download and again immediately before installer launch.
- Delete partial or failed downloads.

It must not:

- Execute installers.
- Choose assets by guessing filenames.
- Use URLs from `updates.json` as installer download sources.
- Accept install arguments from `updates.json`.

### 3. Platform Installer Layer

Create `app_desktop/update_installer.py`.

Responsibilities:

- Accept only a verified local installer path, platform key, expected SHA-256, and expected size.
- Re-check SHA-256 immediately before launch.
- Windows:
  - Accept only `.exe` installers selected for `windows-x64`.
  - Construct argv in code using Inno Setup quiet arguments: `/VERYSILENT`, `/NORESTART`, and any required safe arguments explicitly listed in code.
  - The Inno script should use `CloseApplications=yes` and define a restart behavior that does not rely on overwriting locked files while DataLab is still running.
- macOS:
  - Accept only `.pkg` installers selected for `macos`.
  - Construct argv in code as `/usr/sbin/installer -pkg <verified_path> -target /`.
  - Expect macOS administrator authorization when required by the install target.
- Return a clear result for whether the installer process was launched, not whether installation ultimately succeeded.

It must not:

- Bypass UAC, SmartScreen, Gatekeeper, or macOS administrator prompts.
- Delete or overwrite the running application itself.
- Run an installer whose SHA-256 has not just been verified.
- Accept remote-controlled install arguments.

### 4. Desktop Controller Layer

Create `app_desktop/update_controller.py` and keep UI message construction separate where useful.

Responsibilities:

- Wire Help menu actions.
- Persist automatic update settings, last check time, skipped version, cached release notes, and last seen app version.
- Run manual checks on demand.
- Run automatic checks only when the user enabled them and the throttle window has elapsed.
- Keep automatic offline failures quiet.
- Display update dialogs with release notes.
- Drive the update state machine: idle, checking, update available, downloading, verifying, ready to install, launching installer, failed.
- Enforce in-process re-entrancy protection so manual checks cannot overlap startup checks or downloads.
- Use a cache-directory lock so two DataLab instances cannot download or launch the same update concurrently.
- Launch the installer and then request app exit only after installer launch succeeds.
- Show best-effort update-complete information after the next launch when the app version changes.

## Release Metadata

Each auto-installable GitHub Release must include an asset named exactly `updates.json`.

DataLab fetches `updates.json` as follows:

1. Call the GitHub latest release API.
2. Inspect the release asset list returned by that API.
3. Find an asset whose name is exactly `updates.json`.
4. Download the manifest from that asset's `browser_download_url`.
5. Reject the auto-install path if the manifest asset is missing or cannot be downloaded.

`updates.json` is a data declaration only. It does not provide installer command-line arguments.

Example:

```json
{
  "schema_version": 1,
  "min_client_version": "2.2.0",
  "version": "2.3.0",
  "published_at": "2026-05-26T00:00:00Z",
  "release_url": "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
  "notes": "Added installer-based automatic updates.",
  "assets": {
    "macos": {
      "name": "DataLab-2.3.0-macOS.pkg",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "size_bytes": 125000000
    },
    "windows-x64": {
      "name": "DataLab-2.3.0-Windows-x64.exe",
      "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
      "size_bytes": 140000000
    }
  }
}
```

Validation rules:

- `schema_version` must be `1`; unknown schema versions fall back to the release page with a user-facing message during manual checks and a quiet skip during automatic checks.
- `min_client_version` is optional. If present and the running client version is lower, DataLab falls back to the release page because this client is too old to safely auto-install that release.
- `version` must match the GitHub release tag after normalizing a leading `v`.
- `release_url`, if present, must exactly match the release API `html_url` after URL normalization. It is display metadata, not a download source.
- The selected asset name must exist in the GitHub release assets.
- The selected asset URL must come from that release asset's `browser_download_url`.
- `sha256` must be exactly 64 lowercase or uppercase hexadecimal characters.
- `size_bytes` must be a positive integer and must not exceed the hard maximum installer size.
- Unknown fields are ignored for forward-compatible additive metadata.

## User Flow

### Manual Check

The user selects Help -> `检查更新` / `Check for Updates`.

1. DataLab checks the latest GitHub Release.
2. If no newer version exists, it shows an "already up to date" message.
3. If a newer version exists, DataLab fetches `updates.json` from the matching release asset.
4. If the manifest is valid and contains the current platform installer, DataLab shows an update dialog.
5. If the manifest is missing, invalid, too new for this client, missing the current platform, or missing required signature/notarization release evidence, DataLab shows release notes and offers to open the release page.

### Automatic Check

The user enables Help -> `自动更新` / `Automatic Updates`.

1. DataLab persists this opt-in setting.
2. On later launches, DataLab delays the startup check briefly so the main window can appear.
3. DataLab checks at most once every 24 hours. This interval is a fixed v1 constant, not a user preference.
4. A failed automatic check records `last_checked_at` to avoid repeated startup retries during long offline periods.
5. Offline, GitHub, manifest, or signing-gate failures during automatic checks do not show modal errors.
6. If a valid update is available and the version is not skipped, DataLab shows the same update dialog as the manual flow.

Clock policy:

- If `last_checked_at` is in the future by more than 10 minutes, DataLab treats it as stale and allows one check, then rewrites it.
- If the system clock moves backward, the 24-hour throttle may run later than expected but must not create repeated prompts in a single process.

### Update Dialog

The update dialog shows:

- Current version.
- Latest version.
- Published date from the GitHub Release, with manifest `published_at` used only as fallback display text.
- Release notes, rendered as safe plain text and truncated with a link to the release page if long.
- Installer asset name.
- Installer size.
- A note that OS security prompts may appear and that the app will close after the installer starts.

Buttons:

- `立即更新` / `Update Now`
- `稍后` / `Later`
- `跳过此版本` / `Skip This Version`

`Later` dismisses the dialog for the current check. `Skip This Version` persists the skipped version and suppresses automatic prompts for that version. Manual checks still show skipped versions because the user explicitly requested the check, but the dialog must indicate that the version was previously skipped.

Skipping a newer version replaces any older skipped version. There is no dedicated unskip UI in v1; a manual check can still install a skipped version.

### Download, Verify, Install

After `Update Now`:

1. DataLab acquires the update operation lock.
2. DataLab downloads the selected installer and shows progress.
3. DataLab verifies the final file size and SHA-256.
4. If verification fails, DataLab deletes the installer and cancels the update.
5. If verification succeeds, DataLab tells the user it is preparing to start the installer and close DataLab.
6. Immediately before launch, DataLab re-checks size and SHA-256 to reduce time-of-check/time-of-use risk.
7. DataLab starts the platform installer with code-constructed safe arguments.
8. If installer launch succeeds, DataLab exits.
9. If installer launch fails, DataLab stays open and offers to open the release page.

Installer launch success does not prove install success. If the user cancels Windows UAC, macOS administrator authorization, or a SmartScreen/Gatekeeper prompt after the installer has started, DataLab may already have exited. On next launch, if the version did not change, DataLab treats the update as not installed and may offer the update again after the normal throttle window.

### Update Complete Notice

On startup, DataLab compares the current app version with the last seen version in settings.

If the version changed:

- Show `DataLab 已更新到 X` / `DataLab has been updated to X`.
- Include cached release notes only if they match the current version.
- If cached notes do not match, show a short version-only notice.
- Do not perform a network request solely to populate this notice.

This notice is best-effort. It is not proof that a previous installer process succeeded, and it is not a rollback mechanism.

## Security and Failure Handling

Default behavior:

- Automatic updates are off by default.
- Startup does not contact the network unless automatic updates were enabled.
- Manual checks are allowed to contact GitHub because the user explicitly requested them.

Execution safety:

- DataLab only executes installers declared in a valid `updates.json`.
- DataLab only downloads installers whose asset URL came from the GitHub Release API.
- DataLab only executes installers whose size and SHA-256 match the manifest immediately before launch.
- DataLab never runs arbitrary GitHub release assets chosen by filename guessing.
- DataLab never accepts installer command-line arguments from release metadata.
- DataLab does not store credentials.
- DataLab does not try to bypass OS security prompts.

Failure handling:

- Missing manifest: fall back to release page.
- Invalid manifest: fall back to release page.
- Unsupported schema or too-new `min_client_version`: fall back to release page.
- No current-platform installer: fall back to release page.
- Missing signing/notarization release evidence: fall back to release page.
- Download failure: show error for manual flow; stay quiet for automatic flow unless already in an explicit update dialog.
- Disk-full, free-space, timeout, size mismatch, or SHA-256 mismatch: delete partial file, cancel update, and show error if user initiated install.
- Installer launch failure: keep DataLab open and offer release page.
- Installer runtime failure after DataLab exits: the next launch determines whether the version changed. Rollback is not provided in v1; users can manually install an older GitHub Release if needed.

## Packaging and Release Pipeline

### macOS

- PyInstaller continues to build `DataLab.app`.
- Add a `.pkg` packaging step using `pkgbuild` and, if needed, `productbuild`.
- Install target: `/Applications/DataLab.app`.
- Release asset name: `DataLab-<version>-macOS.pkg`.
- The `.pkg` must be signed with a Developer ID Installer certificate and notarized before being marked auto-installable.
- Release acceptance must verify the package with `spctl`/Gatekeeper behavior in a clean macOS environment.
- Users may still see an administrator authorization prompt when installing to `/Applications`.

### Windows

- PyInstaller continues to build the Windows application directory.
- Add an Inno Setup script to package that directory.
- The Inno script must define safe replacement behavior for a running DataLab instance, using `CloseApplications` and restart settings or an equivalent controlled approach.
- Quiet install arguments are constructed by DataLab code: `/VERYSILENT /NORESTART`.
- Release asset name: `DataLab-<version>-Windows-x64.exe`.
- The installer must be Authenticode-signed before being marked auto-installable.
- Release acceptance must verify the signature and UAC/SmartScreen behavior in a clean Windows VM.

### Release Assets

Each auto-installable release should publish:

- `DataLab-<version>-macOS.pkg`
- `DataLab-<version>-Windows-x64.exe`
- `updates.json`

Release notes must be generic and public-facing. They must not include local paths, local servers, SSH hostnames, temporary directories, or machine-specific build details.

## Settings and Cache

Add update keys under the `Update/` namespace, grouped by role:

- `Update/prefs/auto_update_enabled`
- `Update/prefs/skipped_version`
- `Update/state/last_checked_at`
- `Update/state/last_seen_current_version`
- `Update/cache/release_version`
- `Update/cache/release_notes`
- `Update/cache/release_url`
- `Update/cache/release_published_at`

Stored values are non-sensitive. They are suitable for QSettings plaintext storage.

Downloaded installers and partial files live outside QSettings in the platform user cache:

- macOS: `~/Library/Caches/DataLab/Updates`
- Windows: `%LOCALAPPDATA%\\DataLab\\Updates`

Cache policy:

- Partial downloads use a temporary suffix and are removed on failure.
- Verified installers are deleted after installer launch or on the next startup if older than 7 days.
- The cache directory uses a lock file to prevent concurrent update operations across DataLab instances.
- If the cache directory is unavailable or unwritable, auto-install falls back to the release page.

## Testing Strategy

### Manifest and Payload Tests

- Valid manifest parses successfully.
- `updates.json` is fetched only from a GitHub Release asset named exactly `updates.json`.
- Invalid schema version falls back to release page.
- `min_client_version` higher than the running client falls back to release page.
- Manifest version mismatch is rejected.
- Missing platform asset is rejected.
- SHA-256 with wrong length or non-hex characters is rejected.
- Missing, zero, negative, or oversized `size_bytes` is rejected.
- Selected asset must exist in GitHub release assets.
- Installer download URL must come from the GitHub Release API asset, not from manifest text.
- Platform selection maps macOS to `macos` and Windows x64 to `windows-x64`.
- Future platform keys are ignored by clients that do not use them.

### Download Tests

- Successful fake download produces a file in the platform cache directory.
- Matching size and SHA-256 passes.
- Mismatched size or SHA-256 deletes the file.
- Download failures return clear errors.
- Disk-full and unwritable-cache failures return clear errors.
- Total timeout and stall timeout cancel the download.
- Download code does not write into the project directory.
- SHA-256 is rechecked immediately before installer launch.

### Desktop Controller Tests

- Help menu contains manual check and automatic update toggle.
- Automatic update toggle defaults off.
- Toggle state persists.
- Startup does not call the network when automatic update is off.
- Manual offline failure shows an error.
- Automatic offline failure is quiet and records `last_checked_at`.
- Update dialog includes release notes, installer name, installer size, and OS prompt warning.
- `Skip This Version` suppresses automatic prompts for that version.
- Manual checks show skipped versions with a clear "previously skipped" indication.
- Manual and automatic checks cannot overlap.
- A second DataLab instance cannot start a competing download while the lock is held.
- `Update Now` starts download, verification, re-verification, and installer launch flow.

### Installer Tests

- Windows command is constructed in code and includes Inno quiet arguments.
- Windows backend rejects non-`.exe` installers.
- Windows backend does not accept manifest-provided argv.
- macOS command is constructed in code as `/usr/sbin/installer -pkg <pkg> -target /`.
- macOS backend rejects non-`.pkg` installers.
- macOS backend does not accept manifest-provided argv.
- Installer launch failure does not exit DataLab.
- Installer launch success triggers the configured app-exit callback.
- UAC/admin-prompt cancellation is treated as "install may not have completed"; next launch checks the actual version.

### Release Acceptance Tests

Before publishing a release that claims auto-update support:

- Build macOS `.pkg`.
- Sign and notarize the macOS `.pkg`.
- Verify macOS Gatekeeper/notarization behavior in a clean macOS environment.
- Build Windows Inno `.exe` on the Windows build host.
- Authenticode-sign the Windows `.exe`.
- Verify Windows signature, UAC, and SmartScreen behavior in a clean Windows VM.
- Generate `updates.json` with correct SHA-256 and size values.
- Upload all assets to the same GitHub Release.
- From an older DataLab build, verify:
  - Startup does not check the network when automatic updates are off.
  - Manual update check shows release notes.
  - Current-platform installer downloads.
  - Size and SHA-256 verification pass.
  - Installer launch command is correct.
  - Cancelling OS authorization does not corrupt settings.
  - Offline automatic check does not show an error.

## Acceptance Criteria

- DataLab does not contact the network at startup unless the user enabled automatic updates.
- Manual update checks still work.
- Update prompts show release notes before installation.
- DataLab only downloads and executes manifest-declared, platform-matched installers whose URLs came from the GitHub Release API.
- SHA-256 and size verification are mandatory before installer execution.
- Installer command lines are constructed by code, not by release metadata.
- macOS and Windows each have a defined installer backend and a defined OS authorization boundary.
- Auto-installable releases are signed/notarized as appropriate for the platform.
- Missing metadata, unsupported platforms, signing-gate failures, or schema incompatibility degrade to opening the release page.
- Release packaging can generate signed/notarized `.pkg`, signed Inno `.exe`, and `updates.json`.
- Public release notes and updater dialogs do not expose local/private environment details.
