@echo off
chcp 65001 >nul
title PepperChat — Démarrage

:: ============================================================
:: START_APP.bat — Lance l'application PepperChat complète
::
:: Ce script :
::   1. Démarre les services Python 3 via Docker Compose
::   2. Attend 10 secondes que les services soient prêts
::   3. Lance le module de reconnaissance vocale (Python 2.7)
::   4. Lance le module de dialogue principal (Python 2.7)
::
:: Prérequis :
::   - Docker Desktop ouvert et démarré
::   - Python 2.7 installé dans C:\Python27\
::   - SDK NaoQI copié dans C:\Python27\Lib\site-packages\
::   - Fichier .env configuré avec ROBOT_IP=<ip_du_robot>
:: ============================================================

:: Se placer dans le dossier du script (= racine du projet)
cd /d "%~dp0"

:: ── Lire l'IP du robot depuis le fichier .env ──────────────
SET ROBOT_IP=192.168.1.76
FOR /F "usebackq tokens=1,* delims==" %%A IN (".env") DO (
    IF "%%A"=="ROBOT_IP" SET ROBOT_IP=%%B
)
:: Supprimer les espaces eventuels autour de la valeur
SET ROBOT_IP=%ROBOT_IP: =%
echo [CONFIG] IP robot : %ROBOT_IP%

:: ── ÉTAPE 1 : Démarrer les services Docker (Python 3) ──────
echo.
echo [1/3] Demarrage des services Docker (IA + STT + Interface Web)...
docker compose up -d --build
IF ERRORLEVEL 1 (
    echo ERREUR : Impossible de demarrer Docker Compose.
    echo Verifiez que Docker Desktop est bien ouvert et en cours d'execution.
    pause
    exit /b 1
)
echo [1/3] Services Docker demarres avec succes.

:: ── ÉTAPE 2 : Attendre que les services soient opérationnels
echo.
echo [2/3] Attente de 10 secondes pour l'initialisation des services...
timeout /t 10 /nobreak >nul

:: ── ÉTAPE 3 : Module reconnaissance vocale (Python 2.7) ────
echo.
echo [3/3] Lancement du module de reconnaissance vocale...
start "Speech Recognition" C:\Python27\python.exe module_speechrecognition.py --pip %ROBOT_IP%

:: Petite pause entre les deux modules NaoQI
timeout /t 3 /nobreak >nul

:: ── ÉTAPE 4 : Module dialogue principal (Python 2.7) ───────
echo.
echo [3/3] Lancement du module de dialogue principal...
start "Dialogue NaoQI" cmd /c "echo 2 | C:\Python27\python.exe module_dialogue.py --pip %ROBOT_IP%"

:: ── Résumé ──────────────────────────────────────────────────
echo.
echo ============================================================
echo  PepperChat est maintenant en cours d'execution !
echo.
echo  Services actifs :
echo    - Docker (IA + STT + Web) : docker compose logs -f
echo    - Speech Recognition      : fenetre "Speech Recognition"
echo    - Dialogue NaoQI          : fenetre "Dialogue NaoQI"
echo.
echo  Pour tout arreter : double-cliquer sur STOP_APP.bat
echo ============================================================
echo.
pause
