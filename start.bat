@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=%CD%\.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PYTHON=%CD%\venv\Scripts\python.exe"

"%PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Dependencias nao encontradas no ambiente Python.
    echo Execute: "%PYTHON%" -m pip install -r requirements.txt
    exit /b 1
)

set "APP_URL=http://127.0.0.1:8000/"

echo Iniciando PriceBot em %APP_URL%
echo Pressione Ctrl+C para encerrar.
if /I not "%~1"=="--no-browser" (
    start "" powershell -NoProfile -WindowStyle Hidden -Command "$url = '%APP_URL%'; for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest -UseBasicParsing -Uri ($url + 'health') -TimeoutSec 1 ^| Out-Null; Start-Process $url; exit } catch { Start-Sleep -Milliseconds 500 } }"
)

"%PYTHON%" -m uvicorn src.api:app --host 127.0.0.1 --port 8000
endlocal
