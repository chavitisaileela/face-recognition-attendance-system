@echo off
title FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM - Local
color 0B
cls
echo.
echo  ============================================================
echo   FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM
echo  ============================================================
echo.
echo  Starting LOCAL server (accessible only on this computer)...
echo  Open browser at:  http://localhost:8000
echo.

cd /d F:\AI-Attendance-System
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
