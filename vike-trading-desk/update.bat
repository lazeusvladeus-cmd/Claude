@echo off
setlocal
title Vike Trading Desk - update libraries
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto :no_venv

echo  Updating the libraries. yfinance matters most: Yahoo changes things now and then.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade -r requirements.txt
if errorlevel 1 goto :failed
copy /y requirements.txt ".venv\installed-requirements.txt" >nul
echo.
echo  Done. Start the app again with start.bat.
pause
exit /b 0

:no_venv
echo  Nothing to update yet: double-click start.bat first - it sets everything up.
pause
exit /b 1

:failed
echo.
echo  The update failed. Check your internet connection and try again.
pause
exit /b 1
