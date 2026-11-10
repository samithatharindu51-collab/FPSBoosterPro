# FPS BOOSTER PRO — standalone Windows app
The finished product is a single `FPSBoosterPro.exe` (Windows 10/11 x64). Users need NO Python, NO installer, NO console: double-click and it runs.
PySide6, psutil and the icon are bundled inside. Basic optimization works fully offline. PresentMon (optional, for FPS capture) is a separate free download.

## Get the EXE (pick one)
**A. GitHub Actions (no tools on your PC):** create a free GitHub repo, upload ALL files of this folder (including the `.github` folder; use GitHub Desktop or `git push` if drag-and-drop skips it),
open the **Actions** tab -> *Build FPSBoosterPro.exe* -> **Run workflow**. After ~5-8 minutes download artifact **FPSBoosterPro-windows-x64**. It only appears if the EXE passed its self-test.
Artifact **diagnostics** has a screenshot of every page rendered by the built EXE. Push a tag like `v2.0.0` to also get a GitHub Release with the EXE.
**B. On any Windows PC:** double-click `build.bat` (needs Python only on that PC). It builds `dist\FPSBoosterPro.exe`, then tests it.

## What the automated test does
Runs `test_all.py`, builds a one-file EXE with PyInstaller, then launches the *built EXE* with Python removed from PATH using `--selftest`: it starts the real UI, visits all 10 pages, saves screenshots, checks the bundled icon and live hardware data, and exits 0 only on success.

## Administrator rights
The EXE starts without elevation. It asks (with a Yes/No prompt, then Windows UAC) only when you use something that needs it: the HKLM scheduler tweak or PresentMon capture. Settings has a "Restart as administrator" button.

## Notes
* First launch takes a few seconds (one-file EXEs unpack to a temp folder). Unsigned EXEs may show Windows SmartScreen "Unknown publisher": click More info -> Run anyway. Removing that requires a paid code-signing certificate.
* Errors are caught and logged to `%APPDATA%\FPSBoosterPro\crash.log`; startup failures show a message box.
* FPS: put `PresentMon.exe` (https://github.com/GameTechDev/PresentMon/releases) next to the EXE or use FPS Monitor -> Locate. FPS is never estimated.
* Tests locally: `python test_all.py`.
