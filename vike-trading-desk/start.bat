@echo off
setlocal
title Vike Trading Desk
cd /d "%~dp0"

echo.
echo  ==============================================
echo     Vike Trading Desk
echo  ==============================================
echo.

rem ---- 1. Find Python 3.11 or newer - 3.13 preferred
set "PY="
for %%V in (3.13 3.12 3.14 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto :no_python

rem ---- 2. First start: create a private Python environment in the .venv folder
if exist ".venv\Scripts\python.exe" goto :have_venv
echo  First start: creating a private Python environment. This takes about a minute...
%PY% -m venv .venv
if errorlevel 1 goto :venv_failed
:have_venv

rem ---- 3. Install the libraries - only when requirements.txt has changed
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>&1
if not errorlevel 1 goto :libs_ok
echo  Installing the libraries the app needs. The first time this takes a few minutes...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :install_failed
copy /y requirements.txt ".venv\installed-requirements.txt" >nul
:libs_ok

rem ---- 4. Skip Streamlit's one-time "enter your email" question
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo  Starting... your browser will open http://localhost:8501
echo  Keep this black window open while you use the app.
echo  To stop the app, close this window.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
echo.
echo  The app has stopped.
pause
exit /b 0

:no_python
echo  Python was not found on this computer.
echo.
echo  1. Open https://www.python.org/downloads/windows/
echo  2. Under "Python 3.13.16" (or the newest 3.13), click "Windows installer (64-bit)"
echo  3. Run it, tick "Add python.exe to PATH" at the bottom, then click "Install Now"
echo  4. Double-click start.bat again
echo.
pause
exit /b 1

:venv_failed
echo  Could not create the private Python environment.
echo  Delete the .venv folder next to this file, then double-click start.bat again.
pause
exit /b 1

:install_failed
echo.
echo  Installing the libraries failed. Check your internet connection and run start.bat again.
echo  If it keeps failing: delete the .venv folder next to this file and try once more.
pause
exit /b 1
