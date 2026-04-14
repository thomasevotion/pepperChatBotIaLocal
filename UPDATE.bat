@echo off
title Mise a jour du projet (Git Pull)
echo === Mise a jour depuis le depot distant ===
echo.

:: Se placer automatiquement dans le dossier où se trouve le fichier .bat
cd /d "%~dp0"

:: Executer le git pull
git pull

echo.
echo ===========================================
echo Mise a jour terminee.
pause