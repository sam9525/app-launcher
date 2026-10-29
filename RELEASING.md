# Releasing

Checklist for releasing App Launcher. `X.Y.Z` stands for the new version. `version.py` is the only place a version number is typed; everything below is text.

Prerequisites installed by hand:
- Inno Setup (`iscc`), which turns `dist\AppLauncher.exe` into `AppLauncher-Setup.exe`. Without it, `installer\build.bat` stops at `iscc` with "not recognized" and exit 1 after `dist\AppLauncher.exe` is built; that is expected.
- Optionally the `gh` CLI. The GitHub release can also be created on the website.

Run each command on its own line; do not chain them with `&&` (a parse error in Windows PowerShell 5.1).

1. **Start clean.** Be on `develop` with a clean tree, and make sure all four checks are at zero:
   ```
   py -m black --check .
   py -m ruff check .
   py -m mypy .
   py -m pytest -q
   ```
2. **README.** Re-read `README.md` against the app and fix anything stale; it has gone stale before.
3. **Changelog.** Add a `## vX.Y.Z` section to `CHANGELOG.md` from `git log master..develop`. List user-facing changes only (Added / Fixed / Changed); leave out test and lint commits. Then commit steps 2 and 3:
   ```
   git commit -am "docs: update README and changelog for vX.Y.Z"
   ```
4. **Version.** Set `VERSION = "X.Y.Z"` in `version.py` on `develop` and commit only that file:
   ```
   git commit version.py -m "chore: bump version to X.Y.Z"
   ```
5. **Merge to master.** Sync first so you don't merge onto a stale `master`.
   ```
   git checkout master
   git pull --ff-only
   git log --oneline develop..master
   git merge --no-ff develop -m "Merge develop into master for vX.Y.Z"
   ```
   Stop if `git pull --ff-only` fails (for example offline). `git log --oneline develop..master` must print nothing; if it lists commits, `master` has changes `develop` lacks, so stop and resolve that before merging. `--no-ff` leaves a merge commit as a marker for each release.
6. **Tag.** Annotated tag on the merge commit:
   ```
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   ```
7. **Back to develop.** Never leave the tree on `master`.
   ```
   git checkout develop
   npx gitnexus analyze
   ```
8. **Build.** Close the running App Launcher first (it locks `dist\AppLauncher.exe`) and open a fresh terminal. A terminal started by an older App Launcher inherits its temporary Tcl/Tk paths and the exe is built without Tcl/Tk; `installer\build.bat` clears those variables, but a fresh terminal is still the safe habit.
   ```
   installer\build.bat
   ```
   Check that the built exe opens Settings. If Explorer shows a stale icon, that is the Windows icon cache, not the build.
9. **Manual, by you.**
   - `git push origin master` and `git push origin vX.Y.Z`. Never push `develop`; origin holds only `master` and the release tags.
   - Create the GitHub release on the tag, paste the changelog section, and attach `installer\Output\AppLauncher-Setup.exe`.
10. **Check.** After publishing, an older install shows "Update available".
