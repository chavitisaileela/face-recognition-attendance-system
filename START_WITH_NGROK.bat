@echo off
title FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM
color 0A
cls
echo.
echo  ============================================================
echo   FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM
echo  ============================================================
echo.
echo  Starting system with NGROK online tunnel...
echo  (The app will be accessible from any device on the internet)
echo.

cd /d F:\AI-Attendance-System

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found! Please install Python 3.9+
    pause
    exit /b
)

REM Check if pyngrok is installed, install if not
python -c "import pyngrok" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] Installing pyngrok...
    pip install pyngrok
)

echo.
echo  ============================================================
echo   Starting server... (this may take 5-10 seconds)
echo  ============================================================
echo.

python ngrok_run.py

pause
