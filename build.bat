@echo off
REM One-click local build. Python is needed ONLY on the machine that builds - the resulting EXE needs nothing.
setlocal
cd /d "%~dp0"
python -m venv .venv || goto :err
call .venv\Scripts\activate || goto :err
python -m pip install -r requirements-build.txt || goto :err
python icon.py || goto :err
pyinstaller --noconfirm --clean --noconsole --onefile --name FPSBoosterPro --icon assets\icon.ico --version-file version.txt --add-data "assets;assets" --exclude-module tkinter app.py || goto :err
echo Testing the built EXE...
dist\FPSBoosterPro.exe --selftest "%~dp0selftest"
if errorlevel 1 (type selftest\result.txt & goto :err)
type selftest\result.txt
echo.
echo SUCCESS: dist\FPSBoosterPro.exe is built and passed its self-test.
exit /b 0
:err
echo.
echo BUILD FAILED - see the messages above.
exit /b 1
