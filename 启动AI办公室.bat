@echo off
echo.
echo  ========================================
echo     AI办公室 Multi-Agent System v2.0
echo  ========================================
echo.

cd /d "%~dp0"

:: [1/3] Check Python
echo  [1/3] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Please install Python 3.8+
    goto :end
)
echo  [OK] Python ready
echo.

:: [2/3] Check dependencies
echo  [2/3] Checking dependencies...
python -c "import fastapi, uvicorn, aiohttp, dotenv" 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] Missing dependencies, installing...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo  [ERROR] Install failed. Please run manually: pip install -r requirements.txt
        goto :end
    )
)
echo  [OK] Dependencies ready
echo.

:: [3/3] Check .env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo  [INFO] Please edit .env to set your LLM API Key
        notepad ".env"
        pause
    )
)

echo  [3/3] Starting server...
echo.

:: Kill process on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTEN"') do (
    echo  [INFO] Killing existing process on port 8000 (PID=%%a)...
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

set "AIKY_URL=http://localhost:8000"
echo  Browser will open automatically: %AIKY_URL%
echo  Press Ctrl+C to stop
echo.

cd /d "%~dp0backend"
set PYTHONPATH=%cd%
set AIKY_AUTO_OPEN_BROWSER=1
set "AIKY_AUTO_OPEN_URL=%AIKY_URL%"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .

:end
echo.
pause
