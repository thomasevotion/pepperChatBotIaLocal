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
title PepperChat - Arret

cd /d "%~dp0"

echo [STOP] Arret de PepperChat...
echo.

set "ROBOT_IP=192.168.1.76"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if "%%A"=="ROBOT_IP" set "ROBOT_IP=%%B"
    )
)

:: Les deplacements continuent sur le robot meme si la fenetre Navigation est fermee :
:: on les arrete explicitement d'abord.
if exist "C:\Python27\python.exe" (
    echo [0/2] Arret des deplacements de Pepper...
    "C:\Python27\python.exe" pepper_navigation.py --pip %ROBOT_IP% --stop >nul 2>&1
)

echo [1/2] Fermeture des fenetres PepperChat...
taskkill /FI "WINDOWTITLE eq PepperChat Navigation*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat STT*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Gemini*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat IA*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Ollama*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Web*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat SpeechRecog*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Dialogue*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Speech Recognition" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Dialogue NaoQI" /F /T >nul 2>&1
echo [1/2] Fenetres fermees.

:: Liberer la VRAM : le modele Ollama est charge avec keep_alive infini
set "OLLAMA_MODEL=qwen3.5:9b"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if "%%A"=="OLLAMA_MODEL" set "OLLAMA_MODEL=%%B"
    )
)
ollama stop %OLLAMA_MODEL% >nul 2>&1

echo.
echo [2/2] Nettoyage processus Python...
taskkill /F /IM python.exe >nul 2>&1
echo [2/2] Termine.

echo.
echo ============================================================
echo  PepperChat arrete.
echo ============================================================
echo.
pause
