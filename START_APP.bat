@echo off
chcp 65001 >nul
title PepperChat - Demarrage

cd /d "%~dp0"
set "PROJECT_DIR=%cd%"

:: Detecter Python 3
set "PY3="
where py >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%V in ('py -3 --version 2^>nul') do set "PY3=py -3"
)
if "%PY3%"=="" (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%V in ('python --version 2^>^&1') do (
            echo %%V | findstr /C:"3." >nul && set "PY3=python"
        )
    )
)
if "%PY3%"=="" (
    echo ERREUR : Python 3 introuvable.
    pause
    exit /b 1
)
echo [CONFIG] Python 3 : %PY3%

:: Detecter Python 2.7
set "PY2=C:\Python27\python.exe"
if not exist "%PY2%" (
    echo ERREUR : Python 2.7 introuvable dans C:\Python27\
    pause
    exit /b 1
)
echo [CONFIG] Python 2 : %PY2%

:: Lire IP robot depuis .env
set "ROBOT_IP=192.168.1.76"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if "%%A"=="ROBOT_IP" set "ROBOT_IP=%%B"
    )
)
echo [CONFIG] IP robot : %ROBOT_IP%
echo.

:: ETAPE 1 : Serveur STT Google
echo [1/5] Serveur STT Google (port 8889)...
start "PepperChat STT" cmd /k "title PepperChat STT && cd /d "%PROJECT_DIR%" && %PY3% google_stt_server.py"
timeout /t 3 /nobreak >nul

:: ETAPE 2 : Serveur IA Gemini
echo [2/5] Serveur IA Gemini (port 5556)...
start "PepperChat Gemini" cmd /k "title PepperChat Gemini && cd /d "%PROJECT_DIR%" && %PY3% startDialogueServer_background.py --prompt pepper"
timeout /t 3 /nobreak >nul

:: ETAPE 3 : Interface Web tablette (on cd dans PepperWebLocal pour les chemins relatifs)
echo [3/5] Interface Web tablette (port 9091)...
start "PepperChat Web" cmd /k "title PepperChat Web && cd /d "%PROJECT_DIR%\PepperWebLocal" && %PY2% main.py --ip %ROBOT_IP%"
timeout /t 3 /nobreak >nul

:: ETAPE 4 : Module reconnaissance vocale
echo [4/5] Module reconnaissance vocale...
start "PepperChat SpeechRecog" cmd /k "title PepperChat SpeechRecog && cd /d "%PROJECT_DIR%" && %PY2% module_speechrecognition.py --pip %ROBOT_IP%"
timeout /t 3 /nobreak >nul

:: ETAPE 5 : Module dialogue (echo Pepper pour repondre au raw_input Participant ID)
echo [5/5] Module dialogue principal...
start "PepperChat Dialogue" cmd /c "title PepperChat Dialogue && cd /d "%PROJECT_DIR%" && echo Pepper| %PY2% module_dialogue.py --pip %ROBOT_IP%"

echo.
echo ============================================================
echo  PepperChat demarre !
echo.
echo  Services :
echo    - STT Google        : fenetre PepperChat STT
echo    - Serveur Gemini    : fenetre PepperChat Gemini
echo    - Web Tablette      : fenetre PepperChat Web
echo    - Speech Recognition: fenetre PepperChat SpeechRecog
echo    - Dialogue NaoQI    : fenetre PepperChat Dialogue
echo.
echo  Pour tout arreter : STOP_APP.bat
echo ============================================================
echo.
pause
