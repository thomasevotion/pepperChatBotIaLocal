@echo off
chcp 65001 >nul
title PepperChat — Arrêt

:: ============================================================
:: STOP_APP.bat — Arrête proprement l'application PepperChat
::
:: Ce script :
::   1. Ferme les fenêtres NaoQI (Speech Recognition + Dialogue)
::   2. Arrête les conteneurs Docker
:: ============================================================

:: Se placer dans le dossier du script (= racine du projet)
cd /d "%~dp0"

echo [STOP] Arret de PepperChat en cours...
echo.

:: ── ÉTAPE 1 : Fermer les fenêtres NaoQI ─────────────────────
echo [1/2] Fermeture des modules NaoQI (Python 2.7)...

:: Tuer la fenetre "Speech Recognition" (lancee par START_APP.bat)
taskkill /FI "WINDOWTITLE eq Speech Recognition" /F /T >nul 2>&1

:: Tuer la fenetre "Dialogue NaoQI" (lancee par START_APP.bat)
taskkill /FI "WINDOWTITLE eq Dialogue NaoQI" /F /T >nul 2>&1

:: Securite : tuer tous les processus python.exe restants (Python 2.7)
:: (uniquement si les fenetres ne s'etaient pas encore fermees)
taskkill /F /IM python.exe >nul 2>&1

echo [1/2] Modules NaoQI arretes.

:: ── ÉTAPE 2 : Arrêter les conteneurs Docker ─────────────────
echo.
echo [2/2] Arret des conteneurs Docker...
docker compose down
IF ERRORLEVEL 1 (
    echo AVERTISSEMENT : Erreur lors de l'arret Docker.
    echo Verifiez l'etat avec : docker compose ps
) ELSE (
    echo [2/2] Conteneurs Docker arretes.
)

:: ── Résumé ──────────────────────────────────────────────────
echo.
echo ============================================================
echo  PepperChat est completement arrete.
echo ============================================================
echo.
pause
