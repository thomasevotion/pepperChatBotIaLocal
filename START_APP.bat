@echo off
chcp 65001 >nul
title PepperChat - Demarrage

cd /d "%~dp0"

set "PY2=C:\Python27\python.exe"
set "PY3=py -3"

set "ROBOT_IP=192.168.1.76"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if "%%A"=="ROBOT_IP" set "ROBOT_IP=%%B"
    )
)
echo [CONFIG] IP robot : %ROBOT_IP%
echo.

echo [1/5] Serveur STT Google (port 8889)...
start "PepperChat STT" %PY3% "%~dp0google_stt_server.py"
timeout /t 3 /nobreak >nul

echo [2/5] Serveur IA Gemini (port 5556)...
start "PepperChat Gemini" %PY3% "%~dp0startDialogueServer_background.py" --prompt pepper
timeout /t 3 /nobreak >nul

echo [3/5] Interface Web tablette (port 9091)...
start "PepperChat Web" /D "%~dp0PepperWebLocal" %PY2% "%~dp0PepperWebLocal\main.py" --ip %ROBOT_IP%
timeout /t 3 /nobreak >nul

echo [4/5] Module reconnaissance vocale...
start "PepperChat SpeechRecog" %PY2% "%~dp0module_speechrecognition.py" --pip %ROBOT_IP%
timeout /t 3 /nobreak >nul

echo [5/5] Module dialogue principal...
start "PepperChat Dialogue" %PY2% "%~dp0module_dialogue.py" --pip %ROBOT_IP%

echo.
echo ============================================================
echo  PepperChat demarre !
echo.
echo  Pour tout arreter : STOP_APP.bat
echo ============================================================
echo.
pause
