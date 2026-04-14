@echo off
chcp 65001 >nul
title PepperChat — Installation complète
setlocal enabledelayedexpansion

:: ============================================================
:: INSTALL_APP.bat — Installation complète de PepperChat
::                   à partir de zéro sur un PC Windows vierge.
::
:: Ce script :
::   1. Télécharge et installe Python 2.7.18 (silencieux)
::   2. Télécharge et installe Python 3.10.x  (silencieux)
::   3. Copie le SDK NAOqi dans Python 2.7
::   4. Installe les dépendances pip pour Python 2 et 3
::   5. Crée le fichier .env si absent
::
:: IMPORTANT : Exécuter en tant qu'Administrateur !
:: ============================================================

cd /d "%~dp0"

echo ============================================================
echo   INSTALLATION COMPLETE DE PEPPERCHAT
echo ============================================================
echo.
echo  Ce script va installer :
echo    - Python 2.7.18  (C:\Python27)
echo    - Python 3.10    (via python.org)
echo    - SDK NAOqi pour Python 2.7
echo    - Toutes les dependances pip
echo.
echo  Veuillez executer ce script en tant qu'Administrateur.
echo.
pause

:: ── Dossier temporaire pour les téléchargements ─────────────
set "TEMP_DIR=%~dp0_install_temp"
if not exist "!TEMP_DIR!" mkdir "!TEMP_DIR!"

:: =============================================================
:: ÉTAPE 1 : Python 2.7.18
:: =============================================================
echo.
echo [1/5] ====== PYTHON 2.7.18 ======
echo.

if exist "C:\Python27\python.exe" (
    echo Python 2.7 deja installe dans C:\Python27\
    C:\Python27\python.exe --version
) else (
    echo Telechargement de Python 2.7.18...
    powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/2.7.18/python-2.7.18.amd64.msi' -OutFile '!TEMP_DIR!\python2.msi' }"

    if not exist "!TEMP_DIR!\python2.msi" (
        echo ERREUR : Echec du telechargement de Python 2.7.18
        echo Telechargez manuellement depuis https://www.python.org/downloads/release/python-2718/
        echo et installez dans C:\Python27\
        pause
        goto :step2
    )

    echo Installation de Python 2.7.18 dans C:\Python27\ ...
    msiexec /i "!TEMP_DIR!\python2.msi" /qn TARGETDIR=C:\Python27 ALLUSERS=1 ADDLOCAL=ALL
    timeout /t 5 /nobreak >nul

    if exist "C:\Python27\python.exe" (
        echo Python 2.7.18 installe avec succes !
    ) else (
        echo ERREUR : L'installation de Python 2.7 a echoue.
        echo Tentative avec l'installeur interactif...
        msiexec /i "!TEMP_DIR!\python2.msi" TARGETDIR=C:\Python27
        timeout /t 10 /nobreak >nul
    )
)

:: Installer pip pour Python 2.7 si absent
if exist "C:\Python27\python.exe" (
    C:\Python27\python.exe -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo Installation de pip pour Python 2.7...
        if exist "%~dp0get-pip.py" (
            C:\Python27\python.exe "%~dp0get-pip.py"
        ) else (
            powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/pip/2.7/get-pip.py' -OutFile '!TEMP_DIR!\get-pip-py2.py' }"
            if exist "!TEMP_DIR!\get-pip-py2.py" (
                C:\Python27\python.exe "!TEMP_DIR!\get-pip-py2.py"
            )
        )
    ) else (
        echo pip deja present pour Python 2.7
    )
)

:: =============================================================
:: ÉTAPE 2 : Python 3.10
:: =============================================================
:step2
echo.
echo [2/5] ====== PYTHON 3.10 ======
echo.

:: Détecter si Python 3 est déjà disponible
set "PY3="
where py >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%V in ('py -3 --version 2^>^&1') do (
        echo %%V | findstr /C:"3." >nul && set "PY3=py -3"
    )
)
if "!PY3!"=="" (
    where python3 >nul 2>&1
    if not errorlevel 1 set "PY3=python3"
)
if "!PY3!"=="" (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%V in ('python --version 2^>^&1') do (
            echo %%V | findstr /C:"3." >nul && set "PY3=python"
        )
    )
)

if not "!PY3!"=="" (
    echo Python 3 deja installe : !PY3!
    !PY3! --version
) else (
    echo Telechargement de Python 3.10.11...
    powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe' -OutFile '!TEMP_DIR!\python3.exe' }"

    if not exist "!TEMP_DIR!\python3.exe" (
        echo ERREUR : Echec du telechargement de Python 3.10.11
        echo Telechargez manuellement depuis https://www.python.org/downloads/
        echo IMPORTANT : Cochez "Add Python to PATH" pendant l'installation !
        pause
        goto :step3
    )

    echo Installation de Python 3.10.11 (ajout au PATH)...
    "!TEMP_DIR!\python3.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
    timeout /t 15 /nobreak >nul

    :: Rafraîchir le PATH dans cette session
    for /f "delims=" %%P in ('powershell -Command "[System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')"') do set "PATH=%%P"

    :: Re-détecter Python 3
    set "PY3="
    where py >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%V in ('py -3 --version 2^>^&1') do (
            echo %%V | findstr /C:"3." >nul && set "PY3=py -3"
        )
    )
    if "!PY3!"=="" (
        where python >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%V in ('python --version 2^>^&1') do (
                echo %%V | findstr /C:"3." >nul && set "PY3=python"
            )
        )
    )

    if not "!PY3!"=="" (
        echo Python 3 installe avec succes : !PY3!
    ) else (
        echo ATTENTION : Python 3 n'est pas detecte dans le PATH.
        echo Vous devrez peut-etre redemarrer le PC puis relancer ce script.
        echo Ou installez Python 3 manuellement en cochant "Add to PATH".
        pause
    )
)

:: =============================================================
:: ÉTAPE 3 : SDK NAOqi pour Python 2.7
:: =============================================================
:step3
echo.
echo [3/5] ====== SDK NAOQI ======
echo.

set "NAOQI_SRC=%~dp0pynaoqi-python2.7-2.5.7.1-win32-vs2013\lib"
set "NAOQI_DST=C:\Python27\Lib\site-packages"

if exist "C:\Python27\Lib\site-packages\naoqi.py" (
    echo SDK NAOqi deja installe dans site-packages.
) else if exist "!NAOQI_SRC!" (
    echo Copie du SDK NAOqi vers C:\Python27\Lib\site-packages\ ...
    xcopy "!NAOQI_SRC!\*" "!NAOQI_DST!\" /E /Y /Q >nul 2>&1
    if exist "C:\Python27\Lib\site-packages\naoqi.py" (
        echo SDK NAOqi copie avec succes !
    ) else (
        echo ATTENTION : La copie du SDK NAOqi a peut-etre echoue.
        echo Copiez manuellement le contenu de :
        echo   !NAOQI_SRC!
        echo vers :
        echo   !NAOQI_DST!
    )
) else (
    echo ATTENTION : Dossier SDK NAOqi introuvable :
    echo   !NAOQI_SRC!
    echo.
    echo Le SDK NAOqi Windows est inclus dans le depot.
    echo Si le dossier pynaoqi-python2.7-2.5.7.1-win32-vs2013\ est manquant,
    echo recuperez-le depuis le repo Git ou copiez-le manuellement.
)

:: =============================================================
:: ÉTAPE 4 : Dépendances pip
:: =============================================================
echo.
echo [4/5] ====== DEPENDANCES PIP ======
echo.

:: ── Python 2 ─────────────────────────────────────────────────
if exist "C:\Python27\python.exe" (
    echo --- Installation des dependances Python 2.7 ---
    C:\Python27\python.exe -m pip install --upgrade pip setuptools 2>nul
    C:\Python27\python.exe -m pip install -r "%~dp0requirements_py2.txt"
    echo.
) else (
    echo [SKIP] Python 2.7 non installe, dependances py2 ignorees.
)

:: ── Python 3 ─────────────────────────────────────────────────
if not "!PY3!"=="" (
    echo --- Installation des dependances Python 3 ---
    !PY3! -m pip install --upgrade pip setuptools
    !PY3! -m pip install -r "%~dp0requirements_py3.txt"
    echo.
) else (
    echo [SKIP] Python 3 non detecte, dependances py3 ignorees.
)

:: =============================================================
:: ÉTAPE 5 : Fichier .env
:: =============================================================
echo.
echo [5/5] ====== CONFIGURATION .env ======
echo.

if exist "%~dp0.env" (
    echo Fichier .env deja present.
    echo Verifiez que ROBOT_IP et GEMINI_API_KEY sont corrects :
    echo.
    type "%~dp0.env"
    echo.
) else (
    echo Creation du fichier .env ...
    set /p "ROBOT_IP_INPUT=Entrez l'IP du robot Pepper [192.168.1.76] : "
    if "!ROBOT_IP_INPUT!"=="" set "ROBOT_IP_INPUT=192.168.1.76"

    set /p "GEMINI_KEY_INPUT=Entrez votre cle API Gemini : "

    (
        echo LOGDIR=logs
        echo OPENAI_PROMPTFILE=openai.prompt
        echo CHATBOT_SERVER_ADDRESS=tcp://localhost:5556
        echo ROBOT_IP=!ROBOT_IP_INPUT!
        echo GEMINI_API_KEY=!GEMINI_KEY_INPUT!
        echo GEMINI_MODEL=gemini-2.5-flash
    ) > "%~dp0.env"

    echo Fichier .env cree avec succes !
)

:: Créer le dossier logs s'il n'existe pas
if not exist "%~dp0logs" mkdir "%~dp0logs"

:: =============================================================
:: Nettoyage
:: =============================================================
echo.
echo Nettoyage des fichiers temporaires...
if exist "!TEMP_DIR!" rd /s /q "!TEMP_DIR!" >nul 2>&1

:: =============================================================
:: Résumé final
:: =============================================================
echo.
echo ============================================================
echo   INSTALLATION TERMINEE !
echo ============================================================
echo.
echo  Verifications :
echo.

:: Vérification Python 2
if exist "C:\Python27\python.exe" (
    echo  [OK] Python 2.7 :
    C:\Python27\python.exe --version 2>&1
) else (
    echo  [!!] Python 2.7 : NON INSTALLE
)

:: Vérification Python 3
if not "!PY3!"=="" (
    echo  [OK] Python 3   :
    !PY3! --version 2>&1
) else (
    echo  [!!] Python 3   : NON DETECTE (redemarrez le PC si vous venez de l'installer)
)

:: Vérification NAOqi
if exist "C:\Python27\Lib\site-packages\naoqi.py" (
    echo  [OK] SDK NAOqi  : installe
) else (
    echo  [!!] SDK NAOqi  : NON INSTALLE
)

:: Vérification .env
if exist "%~dp0.env" (
    echo  [OK] .env       : present
) else (
    echo  [!!] .env       : ABSENT
)

echo.
echo  Prochaine etape :
echo    1. Verifiez le fichier .env (ROBOT_IP, GEMINI_API_KEY)
echo    2. Allumez le robot Pepper et notez son IP
echo    3. Double-cliquez sur START_APP.bat pour lancer PepperChat !
echo.
echo  Si Python 3 n'est pas detecte, REDEMARREZ le PC puis relancez
echo  ce script (le PATH sera alors a jour).
echo.
echo ============================================================
echo.
pause
