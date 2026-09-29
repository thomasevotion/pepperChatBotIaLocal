@echo off
chcp 65001 >nul
title PepperChat - Demarrage

cd /d "%~dp0"

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

echo [1/5] Interface Web tablette (port 9091)...
cd "PepperWebLocal"
start "PepperChat Web" cmd /k "title PepperChat Web && %PY2% main.py --ip %ROBOT_IP%"
cd ..
timeout /t 3 /nobreak >nul

:: ETAPE 2 : Serveur STT local (Whisper, aucun envoi en ligne)
echo [2/5] Serveur STT local Whisper (port 8889)...
start "PepperChat STT" cmd /k "title PepperChat STT && %PY3% local_stt_server.py"
timeout /t 3 /nobreak >nul

:: ETAPE 3 : Serveur IA local (Ollama)
echo [3/5] Serveur IA local Ollama (port 5556)...
curl -s -o nul http://127.0.0.1:11434/api/tags
if errorlevel 1 (
    echo        Ollama n'est pas lance, demarrage de "ollama serve"...
    start "PepperChat Ollama" /min cmd /k "title PepperChat Ollama && ollama serve"
    timeout /t 5 /nobreak >nul
)
start "PepperChat IA" cmd /k "title PepperChat IA && %PY3% startDialogueServer_background.py --prompt pepper"
:: Laisser le temps a Whisper et au LLM de se charger en VRAM
timeout /t 10 /nobreak >nul


:: ETAPE 4 : Module reconnaissance vocale
echo [4/5] Module reconnaissance vocale...
start "PepperChat SpeechRecog" cmd /k "title PepperChat SpeechRecog && %PY2% module_speechrecognition.py --pip %ROBOT_IP%"
timeout /t 3 /nobreak >nul

:: ETAPE 5 : Module dialogue principal
echo [5/5] Module dialogue principal...
start "PepperChat Dialogue" cmd /k "title PepperChat Dialogue && echo 2 | %PY2% module_dialogue.py --pip %ROBOT_IP%"

echo.
echo ============================================================
echo  PepperChat demarre !
echo.
echo  Services :
echo    - STT Whisper local : fenetre PepperChat STT
echo    - IA locale Ollama  : fenetre PepperChat IA
echo    - Web Tablette      : fenetre PepperChat Web
echo    - Speech Recognition: fenetre PepperChat SpeechRecog
echo    - Dialogue NaoQI    : fenetre PepperChat Dialogue
echo.
echo  Pour tout arreter : STOP_APP.bat
echo ============================================================
echo.
pause
