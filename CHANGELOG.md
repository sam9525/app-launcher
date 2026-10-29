# Changelog

## v0.2.2

### Added

- Apps that need admin rights open through a UAC prompt. They are not placed in a zone and launch at most once per run. Cancelling shows "admin approval declined".
- An update check at startup (after about 90 s) and then daily. A newer GitHub release shows a tray notification and an "Update available (vX.Y.Z)" tray item that opens the release page.
- The Settings window shows the app version in its top bar.

### Fixed

- Apps, terminals and Explorer windows opened by App Launcher no longer inherit the exe's temporary Tcl/Tk paths, which broke Tk programs run from them after App Launcher exited.

### Changed

- The installer takes its version from `version.py` (it was hard-coded as 1.0.0).

Earlier versions: https://github.com/sam9525/app-launcher/releases
