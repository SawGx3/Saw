@echo off
chcp 65001 >nul
title محمّل ملفات ديسكورد
cd /d "%~dp0"

echo ============================================
echo   محمّل ملفات ديسكورد - خلفية شفافة
echo ============================================
echo.

REM التأكد من وجود بايثون
python --version >nul 2>&1
if errorlevel 1 (
    echo [خطأ] بايثون غير مثبّت.
    echo حمّله من: https://www.python.org/downloads/
    echo وتأكد تختار "Add Python to PATH" اثناء التثبيت.
    echo.
    pause
    exit /b 1
)

REM تثبيت المكتبات اول مرة فقط
echo جاري التحقق من المكتبات (اول مرة قد تاخذ دقيقة)...
python -m pip install --quiet --upgrade pip >nul 2>&1
python -m pip install --quiet -r requirements.txt

echo تشغيل البرنامج...
echo.
python discord_downloader.py

if errorlevel 1 (
    echo.
    echo حدث خطأ. اقرا الرسالة بالاعلى.
    pause
)
