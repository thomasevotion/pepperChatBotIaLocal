@echo off
echo Arret de tous les processus Python...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python2.exe >nul 2>&1
taskkill /F /IM python3.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
echo Termine.
pause
