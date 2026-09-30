@echo off
set "PEPPER_SELF=%~f0"
:: --- Auto-reparation des fins de ligne -------------------------------------------------
:: En LF (format Unix : ZIP GitHub, git sans conversion...), cmd.exe ne retrouve pas ses
:: labels ("Le systeme ne trouve pas le nom de fichier de commandes"). Ce bloc n'utilise aucun
:: label : il convertit le script en CRLF si besoin, puis le relance.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:PEPPER_SELF; $t=[IO.File]::ReadAllText($p); if ($t -match '[^\r]\n') { [IO.File]::WriteAllText($p, ($t -replace '\r?\n', ([string][char]13+[char]10))); exit 1 }"
if errorlevel 1 (
    echo [INFO] Script converti au format Windows, relance...
    "%~f0" %*
    exit /b
)
:: ----------------------------------------------------------------------------------------
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

:: Mode et carte : PEPPER_MOBILE (1/0), MAP et NAV_RADIUS du fichier .env
::   MAP vide        -> Pepper cree une nouvelle carte (exploration)
::   MAP=chemin.explo -> Pepper reprend directement cette carte
set "PEPPER_MOBILE=0"
set "MAP="
set "NAV_RADIUS=3"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if "%%A"=="PEPPER_MOBILE" set "PEPPER_MOBILE=%%~B"
        if "%%A"=="MAP" set "MAP=%%~B"
        if "%%A"=="NAV_RADIUS" set "NAV_RADIUS=%%~B"
    )
)
if not "%PEPPER_MOBILE%"=="1" (
    echo [CONFIG] Pepper immobile
    goto :config_done
)
if defined MAP (
    set "NAV_ARGS=--map %MAP% --radius %NAV_RADIUS%"
    echo [CONFIG] Pepper mobile - carte : %MAP%
    echo          Pepper doit etre a l'endroit ou la carte a ete creee.
) else (
    set "NAV_ARGS=--radius %NAV_RADIUS%"
    echo [CONFIG] Pepper mobile - NOUVELLE CARTE : exploration seul dans un rayon de %NAV_RADIUS% m.
    echo          Degagez la zone.
)
:config_done
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

:: ETAPE 6 (mode mobile) : navigation, apres que le dialogue a mis Pepper debout
if "%PEPPER_MOBILE%"=="1" (
    echo [6/6] Navigation autonome...
    timeout /t 15 /nobreak >nul
    start "PepperChat Navigation" cmd /k "title PepperChat Navigation && %PY2% pepper_navigation.py --pip %ROBOT_IP% %NAV_ARGS%"
)

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
if "%PEPPER_MOBILE%"=="1" echo    - Navigation        : fenetre PepperChat Navigation
echo.
echo  Pour tout arreter : STOP_APP.bat
echo ============================================================
echo.
pause
