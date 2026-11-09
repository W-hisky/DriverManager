@echo off
:: Controllo privilegi di Amministratore ed elevazione automatica UAC
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WindowStyle Hidden"
    exit /b
)

cd /d "C:\DriverManager"
start "" "C:\DriverManager\.venv\Scripts\pythonw.exe" "C:\DriverManager\src\gui.py"
exit
