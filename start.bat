@echo off
setlocal
cd /d "%~dp0"
python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
 echo Python 3.11+ is required. Starting official installer through winget.
 winget install --id Python.Python.3.13 --exact --source winget
 if errorlevel 1 goto installfail
 echo Python installed. Close this window and reopen start.bat to refresh PATH.
 pause
 exit /b
)
node -e "process.exit(Number(process.versions.node.split('.')[0])>=24?0:1)" >nul 2>&1
if errorlevel 1 (
 echo Node.js 24+ is required. Starting official installer through winget.
 winget install --id OpenJS.NodeJS.LTS --exact --source winget
 if errorlevel 1 goto installfail
 echo Node.js installed. Close this window and reopen start.bat to refresh PATH.
 pause
 exit /b
)
if not exist .venv\Scripts\python.exe python -m venv .venv
if not exist .venv\Scripts\python.exe goto fail
if not exist .venv\installed.ok (
 .venv\Scripts\python -m pip install -r backend\requirements.txt
 if errorlevel 1 goto fail
 echo installed>.venv\installed.ok
)
if not exist frontend\node_modules\ts-fsrs\package.json (
 call npm --prefix frontend ci
 if errorlevel 1 goto fail
)
if not exist backend\.env copy backend\.env.example backend\.env >nul
if exist initialize_data.py .venv\Scripts\python initialize_data.py
if errorlevel 1 goto fail
start "Open website" /b .venv\Scripts\python open_browser.py
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
exit /b
:installfail
echo Automatic installation failed, or winget is missing.
echo Install App Installer from Microsoft Store, or download runtimes from:
echo https://www.python.org/downloads/ and https://nodejs.org/
pause
exit /b 1
:fail
echo Setup failed. Check the errors above and your Internet connection.
pause
exit /b 1
