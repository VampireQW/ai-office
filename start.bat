@echo off
echo Starting AI办公室...
echo.

cd /d "%~dp0"
echo Current dir: %cd%
echo.

echo Checking Python...
python --version
echo.

echo Checking dependencies...
python -c "import fastapi, uvicorn, aiohttp, dotenv; print('All OK')"
echo.

echo Cleaning port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTEN"') do (
    echo Killing PID %%a ...
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo.

echo Starting server...
cd /d "%~dp0backend"
set PYTHONPATH=%cd%
set "AIKY_URL=http://localhost:8000"
echo Browser will open automatically: %AIKY_URL%
echo.

set AIKY_AUTO_OPEN_BROWSER=1
set "AIKY_AUTO_OPEN_URL=%AIKY_URL%"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .

echo.
echo Server stopped.
pause
