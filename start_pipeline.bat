@echo off
echo Lancement du pipeline PepperChat complet
echo =======================================

echo Démarrage STT local...
start "STT Vosk" cmd /k "cd /d %~dp0 && python3 recognize_local.py"

echo Attente 3 secondes...
timeout /t 3

echo Démarrage pipeline Gemma2...
start "Pipeline Gemma2" cmd /k "cd /d %~dp0 && python3 gemma2_pipeline.py"

echo Attente 2 secondes...
timeout /t 2

echo Démarrage TTS Pepper...
start "TTS Pepper" cmd /k "cd /d %~dp0 && C:\Python27\python.exe pepper_tts_handler.py"

echo Attente 2 secondes...
timeout /t 2

echo Démarrage capture audio Pepper...
start "Audio Pepper" cmd /k "cd /d %~dp0 && C:\Python27\python.exe module_speechrecognition.py --pip pepper.local"

echo Pipeline complet lancé!
echo - STT Vosk (Python 3)
echo - Pipeline Gemma2 (Python 3) 
echo - TTS Pepper (Python 2)
echo - Capture audio Pepper (Python 2)
pause
