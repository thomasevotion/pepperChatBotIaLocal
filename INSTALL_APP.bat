@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title PepperChat - Installation complete

cd /d "%~dp0"

echo ============================================================
echo   INSTALLATION COMPLETE DE PEPPERCHAT
echo ============================================================
echo.
echo   Ce script va installer :
echo   - Python 2.7.18 32-bit dans C:\Python27
echo   - Python 3.10.11
echo   - Le SDK NAOqi pour Python 2.7
echo   - Les dependances Python 2 et Python 3
echo   - Ollama + modele IA local, modele Whisper (mode 100%% local)
echo.
echo   Lance ce script en tant qu'administrateur.
echo.
pause

set "TEMP_DIR=%~dp0_install_temp"
set "PY2_DIR=C:\Python27"
set "PY2_EXE=%PY2_DIR%\python.exe"
set "PY2_PIP=%PY2_DIR%\Scripts\pip.exe"
set "NAOQI_SRC=%~dp0pynaoqi-python2.7-2.5.7.1-win32-vs2013\lib"
set "NAOQI_DST=%PY2_DIR%\Lib\site-packages"
set "PY3="

if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

call :step_py2
if errorlevel 1 goto :fail

call :step_py3
if errorlevel 1 goto :fail

call :step_naoqi
if errorlevel 1 goto :fail

call :step_deps
if errorlevel 1 goto :fail

call :step_env
if errorlevel 1 goto :fail

call :step_local_ai
if errorlevel 1 goto :fail

call :cleanup

echo.
echo ============================================================
echo   INSTALLATION TERMINEE
echo ============================================================
echo.
echo Verifications :
echo.

if exist "%PY2_EXE%" (
    echo [OK] Python 2.7 :
    "%PY2_EXE%" --version 2>&1
) else (
    echo [ERREUR] Python 2.7 absent
)

if not "%PY3%"=="" (
    echo [OK] Python 3 :
    %PY3% --version 2>&1
) else (
    echo [ERREUR] Python 3 non detecte
)

if exist "%NAOQI_DST%\naoqi.py" (
    echo [OK] SDK NAOqi installe
) else (
    echo [ERREUR] SDK NAOqi absent
)

if exist "%~dp0.env" (
    echo [OK] Fichier .env present
) else (
    echo [ERREUR] Fichier .env absent
)

echo.
echo Prochaine etape :
echo 1. Verifie le fichier .env
echo 2. Verifie l'IP du robot Pepper
echo 3. Lance START_APP.bat
echo.
pause
exit /b 0

:step_py2
echo.
echo [1/6] ====== PYTHON 2.7.18 32-bit ======
echo.

if exist "%PY2_EXE%" (
    call :check_py2_bitness
    if "!PY2_BITS!"=="32" (
        echo Python 2.7 32-bit deja installe dans %PY2_DIR%
        "%PY2_EXE%" --version 2>&1
        goto :ensure_pip2
    ) else (
        echo.
        echo ERREUR : Python 2.7 detecte dans %PY2_DIR% mais il est en !PY2_BITS!-bit.
        echo Le SDK NAOqi win32 exige Python 2.7 32-bit.
        echo.
        echo Desinstalle Python 2.7, supprime %PY2_DIR%, puis relance ce script.
        echo.
        exit /b 1
    )
)

echo Telechargement de Python 2.7.18 32-bit...
call :download_file "https://www.python.org/ftp/python/2.7.18/python-2.7.18.msi" "%TEMP_DIR%\python2.msi"
if errorlevel 1 (
    echo ERREUR : telechargement de Python 2.7.18 impossible.
    exit /b 1
)

if not exist "%TEMP_DIR%\python2.msi" (
    echo ERREUR : fichier MSI Python 2 absent.
    exit /b 1
)

echo Installation de Python 2.7.18 32-bit...
msiexec /i "%TEMP_DIR%\python2.msi" /qn TARGETDIR=%PY2_DIR% ALLUSERS=1 ADDLOCAL=ALL
if errorlevel 1 (
    echo ERREUR : installation silencieuse de Python 2.7 echouee.
    exit /b 1
)

if not exist "%PY2_EXE%" (
    echo ERREUR : Python 2.7 n'a pas ete installe dans %PY2_DIR%.
    exit /b 1
)

call :check_py2_bitness
if not "!PY2_BITS!"=="32" (
    echo ERREUR : Python 2.7 installe mais en !PY2_BITS!-bit au lieu de 32-bit.
    exit /b 1
)

echo Python 2.7 32-bit installe avec succes.
"%PY2_EXE%" --version 2>&1

:ensure_pip2
echo Verification de pip pour Python 2.7...
chcp 1252 >nul
set "PYTHONIOENCODING=cp1252"

"%PY2_EXE%" -m pip --version >nul 2>&1
if not errorlevel 1 (
    chcp 65001 >nul
    echo pip deja present pour Python 2.7
    exit /b 0
)

if exist "%~dp0get-pip.py" (
    echo Utilisation de get-pip.py local...
    "%PY2_EXE%" "%~dp0get-pip.py"
) else (
    echo Telechargement de get-pip.py pour Python 2.7...
    call :download_file "https://bootstrap.pypa.io/pip/2.7/get-pip.py" "%TEMP_DIR%\get-pip-py2.py"
    if errorlevel 1 (
        chcp 65001 >nul
        echo ERREUR : telechargement de get-pip.py impossible.
        exit /b 1
    )
    "%PY2_EXE%" "%TEMP_DIR%\get-pip-py2.py"
)

set "RC=%ERRORLEVEL%"
chcp 65001 >nul

if not "%RC%"=="0" (
    echo ERREUR : installation de pip pour Python 2.7 echouee.
    exit /b 1
)

"%PY2_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : pip pour Python 2.7 reste indisponible.
    exit /b 1
)

echo pip installe pour Python 2.7.
exit /b 0

:step_py3
echo.
echo [2/6] ====== PYTHON 3.10 ======
echo.

call :detect_py3
if not "%PY3%"=="" (
    echo Python 3 deja detecte :
    %PY3% --version 2>&1
    exit /b 0
)

echo Telechargement de Python 3.10.11...
call :download_file "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe" "%TEMP_DIR%\python3.exe"
if errorlevel 1 (
    echo ERREUR : telechargement de Python 3.10.11 impossible.
    exit /b 1
)

if not exist "%TEMP_DIR%\python3.exe" (
    echo ERREUR : installateur Python 3 absent.
    exit /b 1
)

echo Installation de Python 3.10.11...
"%TEMP_DIR%\python3.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if errorlevel 1 (
    echo ERREUR : installation de Python 3 echouee.
    exit /b 1
)

call :detect_py3
if "%PY3%"=="" (
    echo ERREUR : Python 3 n'est pas detecte apres installation.
    echo Redemarre le PC puis relance ce script si besoin.
    exit /b 1
)

echo Python 3 pret :
%PY3% --version 2>&1
exit /b 0

:step_naoqi
echo.
echo [3/6] ====== SDK NAOQI ======
echo.

if not exist "%PY2_EXE%" (
    echo ERREUR : Python 2.7 absent avant copie du SDK.
    exit /b 1
)

if exist "%NAOQI_DST%\naoqi.py" (
    echo SDK NAOqi deja present.
    exit /b 0
)

if not exist "%NAOQI_SRC%" (
    echo ERREUR : dossier SDK NAOqi introuvable :
    echo %NAOQI_SRC%
    exit /b 1
)

echo Copie du SDK NAOqi...
xcopy "%NAOQI_SRC%\*" "%NAOQI_DST%\" /E /I /Y >nul
if errorlevel 1 (
    echo ERREUR : copie du SDK NAOqi echouee.
    exit /b 1
)

if not exist "%NAOQI_DST%\naoqi.py" (
    echo ERREUR : naoqi.py absent apres copie.
    exit /b 1
)

echo SDK NAOqi copie avec succes.
exit /b 0

:step_deps
echo.
echo [4/6] ====== DEPENDANCES ======
echo.

if exist "%~dp0requirements_py2.txt" (
    echo Installation des dependances Python 2...
    chcp 1252 >nul
    set "PYTHONIOENCODING=cp1252"
    "%PY2_EXE%" -m pip install --upgrade "pip<21" "setuptools<45" wheel
    if errorlevel 1 (
        chcp 65001 >nul
        echo ERREUR : mise a jour pip/setuptools Python 2 echouee.
        exit /b 1
    )
    "%PY2_EXE%" -m pip install -r "%~dp0requirements_py2.txt"
    if errorlevel 1 (
        chcp 65001 >nul
        echo ERREUR : installation requirements_py2.txt echouee.
        exit /b 1
    )
    chcp 65001 >nul
) else (
    echo requirements_py2.txt absent, etape Python 2 ignoree.
)

if not "%PY3%"=="" (
    if exist "%~dp0requirements_py3.txt" (
        echo Installation des dependances Python 3...
        %PY3% -m pip install --upgrade pip setuptools wheel
        if errorlevel 1 (
            echo ERREUR : mise a jour pip/setuptools Python 3 echouee.
            exit /b 1
        )
        %PY3% -m pip install -r "%~dp0requirements_py3.txt"
        if errorlevel 1 (
            echo ERREUR : installation requirements_py3.txt echouee.
            exit /b 1
        )
    ) else (
        echo requirements_py3.txt absent, etape Python 3 ignoree.
    )
) else (
    echo Python 3 absent, dependances Python 3 ignorees.
)

echo Dependances installees.
exit /b 0

:step_env
echo.
echo [5/6] ====== FICHIER .ENV ======
echo.

if exist "%~dp0.env" (
    echo Fichier .env deja present.
    exit /b 0
)

set "ROBOT_IP_INPUT="
set "GEMINI_KEY_INPUT="

set /p "ROBOT_IP_INPUT=Entrez l'IP du robot Pepper [192.168.1.76] : "
if "%ROBOT_IP_INPUT%"=="" set "ROBOT_IP_INPUT=192.168.1.76"

(
    echo LOGDIR=logs
    echo OPENAI_PROMPTFILE=openai.prompt
    echo CHATBOT_SERVER_ADDRESS=tcp://localhost:5556
    echo ROBOT_IP=%ROBOT_IP_INPUT%
    echo LLM_BACKEND=ollama
    echo OLLAMA_MODEL=qwen3.5:9b
    echo WHISPER_MODEL=large-v3-turbo
    echo WHISPER_LANGUAGES=fr,en,es
) > "%~dp0.env"

if not exist "%~dp0logs" mkdir "%~dp0logs"

if not exist "%~dp0.env" (
    echo ERREUR : creation du fichier .env echouee.
    exit /b 1
)

echo Fichier .env cree.
exit /b 0

:step_local_ai
echo.
echo [6/6] ====== IA LOCALE (Ollama + Whisper) ======
echo.

set "OLLAMA_MODEL=qwen3.5:9b"
set "WHISPER_MODEL=large-v3-turbo"
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
    if "%%A"=="OLLAMA_MODEL" set "OLLAMA_MODEL=%%B"
    if "%%A"=="WHISPER_MODEL" set "WHISPER_MODEL=%%B"
)

where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
    ) else (
        echo Installation d'Ollama via winget...
        winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
        if errorlevel 1 (
            echo ERREUR : installation d'Ollama echouee. Installe-le depuis https://ollama.com/download
            exit /b 1
        )
        set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
    )
)
echo Ollama present.

curl -s -o nul http://127.0.0.1:11434/api/tags
if errorlevel 1 (
    start "Ollama" /min ollama serve
    timeout /t 5 /nobreak >nul
)

echo Telechargement du modele IA %OLLAMA_MODEL% (plusieurs Go, une seule fois)...
ollama pull %OLLAMA_MODEL%
if errorlevel 1 (
    echo ERREUR : telechargement du modele %OLLAMA_MODEL% echoue.
    exit /b 1
)

if not "%PY3%"=="" (
    echo Telechargement du modele Whisper %WHISPER_MODEL% ^(une seule fois^)...
    %PY3% -c "import os; from faster_whisper.utils import download_model; download_model(os.environ['WHISPER_MODEL'], cache_dir=r'%~dp0whisper_models')"
    if errorlevel 1 (
        echo ERREUR : telechargement du modele Whisper echoue.
        exit /b 1
    )
)

echo IA locale prete : plus aucune connexion Internet necessaire pour le dialogue.
exit /b 0

:cleanup
if exist "%TEMP_DIR%" rd /s /q "%TEMP_DIR%" >nul 2>&1
exit /b 0

:detect_py3
set "PY3="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY3=py -3"
    exit /b 0
)

python3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY3=python3"
    exit /b 0
)

python --version 2>&1 | findstr /C:"Python 3" >nul
if not errorlevel 1 (
    set "PY3=python"
    exit /b 0
)

exit /b 0

:check_py2_bitness
set "PY2_BITS=unknown"
if exist "%TEMP_DIR%\py2bits.txt" del /f /q "%TEMP_DIR%\py2bits.txt" >nul 2>&1

chcp 1252 >nul
set "PYTHONIOENCODING=cp1252"
"%PY2_EXE%" -c "import struct,sys; sys.stdout.write(str(struct.calcsize('P')*8))" > "%TEMP_DIR%\py2bits.txt" 2>nul
chcp 65001 >nul

if exist "%TEMP_DIR%\py2bits.txt" set /p PY2_BITS=<"%TEMP_DIR%\py2bits.txt"
exit /b 0

:download_file
set "DL_URL=%~1"
set "DL_OUT=%~2"

if exist "%DL_OUT%" del /f /q "%DL_OUT%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DL_URL%' -OutFile '%DL_OUT%' -UseBasicParsing } catch { exit 1 }"

exit /b %ERRORLEVEL%

:fail
echo.
echo ============================================================
echo   INSTALLATION ECHOUEE
echo ============================================================
echo.
echo Corrige l'erreur affichee ci-dessus puis relance INSTALL_APP.bat
echo.
pause
exit /b 1
