# Releasing

Checklist for releasing App Launcher. `X.Y.Z` stands for the new version. `version.py` is the only place a version number is typed; everything below is text.

1. **Start clean.** Be on `develop` with a clean tree, and make sure all four checks are at zero:
   `py -m black .`, `py -m ruff check .`, `py -m mypy .`, `py -m pytest -q`.
2. **README.** Re-read `README.md` against the app and fix anything stale. It went stale before v0.2.1.
3. **Changelog.** Add a `## vX.Y.Z` section to `CHANGELOG.md` from `git log master..develop`. List user-facing changes only (Added / Fixed / Changed); leave out test and lint commits.
4. **Version.** Set `VERSION = "X.Y.Z"` in `version.py` on `develop` and commit it:
   `git commit -am "chore: bump version to X.Y.Z"`.
5. **Merge to master.** Sync first so you don't merge onto a stale `master`. If the pull fails (offline) or `master` has commits `develop` lacks, stop and sort that out first.
   ```
   git checkout master && git pull --ff-only
   git merge --no-ff develop -m "Merge develop into master for vX.Y.Z"
   ```
   `--no-ff` leaves a merge commit as a marker for each release.
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

   Prerequisites installed by hand: Inno Setup (`iscc`, turns `dist\AppLauncher.exe` into `AppLauncher-Setup.exe`) and, optionally, the `gh` CLI (the release can also be created on the GitHub website).
10. **Check.** After publishing, an older install shows "Update available".
