@echo off
chcp 65001 >nul
title PepperChat - Arret

cd /d "%~dp0"

echo [STOP] Arret de PepperChat...
echo.

echo [1/2] Fermeture des fenetres PepperChat...
taskkill /FI "WINDOWTITLE eq PepperChat STT*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Gemini*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Web*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat SpeechRecog*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq PepperChat Dialogue*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Speech Recognition" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Dialogue NaoQI" /F /T >nul 2>&1
echo [1/2] Fenetres fermees.

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
