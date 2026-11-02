# PepperChat — Guide d'utilisation

## Installation (nouveau PC)

**Double-cliquez sur `INSTALL_APP.bat` (en tant qu'Administrateur)**

Ce script installe automatiquement :
- Python 2.7.18 dans `C:\Python27\`
- Python 3.10 (ajouté au PATH)
- Le SDK NAOqi dans Python 2.7
- Toutes les dépendances pip (Python 2 et 3)
- Le fichier `.env` de configuration

---

## Démarrer l'application

**Double-cliquez sur `START_APP.bat`**

Le script lance 4 fenêtres (une par service) :

| Fenêtre | Rôle | Python |
|---------|------|--------|
| STT Google | Reconnaissance vocale Google Cloud | Python 3 |
| Gemini Server | Serveur IA Gemini (ZMQ) | Python 3 |
| Speech Recognition | Module audio Pepper → STT | Python 2.7 |
| Dialogue NaoQI | Module dialogue principal | Python 2.7 |

---

## Arrêter l'application

**Double-cliquez sur `STOP_APP.bat`**

---

## Prérequis

### 1. Python 2.7 + SDK NaoQI
- Installé automatiquement par `INSTALL_APP.bat`
- Ou manuellement : Python 2.7 dans `C:\Python27\`, SDK NAOqi dans `C:\Python27\Lib\site-packages\`

### 2. Python 3.10+
- Installé automatiquement par `INSTALL_APP.bat`
- Ou manuellement : https://www.python.org/downloads/ (cocher **Add to PATH**)

### 3. Fichier `.env`
- Créé automatiquement par `INSTALL_APP.bat`
- Contient : `ROBOT_IP`, `GEMINI_API_KEY`, `CHATBOT_SERVER_ADDRESS`, etc.

### 4. Connexion réseau
- Le PC et le robot Pepper doivent être sur le même réseau

---

## En cas de problème

| Symptôme | Solution |
|----------|----------|
| « Python 3 introuvable » | Relancer `INSTALL_APP.bat`, ou redémarrer le PC si Python 3 vient d'être installé |
| « Python 2.7 introuvable » | Relancer `INSTALL_APP.bat` en tant qu'Administrateur |
| Le robot ne répond pas | Vérifier `ROBOT_IP` dans `.env` ; tester `ping <ip_robot>` |
| Une fenêtre s'ouvre et se ferme | Ouvrir un terminal, lancer la commande manuellement pour voir l'erreur |
| Erreur pip / dépendance | Relancer `INSTALL_APP.bat` |

---

## Structure des fichiers

```
pepperchat-master\
├── INSTALL_APP.bat         ← Installation complète (nouveau PC)
├── START_APP.bat           ← Démarrer l'application
├── STOP_APP.bat            ← Arrêter l'application
├── kill_python.bat         ← Tuer tous les processus Python
├── .env                    ← Configuration (IP robot, clés API)
├── requirements_py2.txt    ← Dépendances Python 2.7
├── requirements_py3.txt    ← Dépendances Python 3.10
├── google_stt_server.py    ← Serveur STT Google (Python 3)
├── startDialogueServer_background.py  ← Serveur Gemini (Python 3)
├── module_speechrecognition.py  ← Module audio Pepper (Python 2)
├── module_dialogue.py      ← Module dialogue Pepper (Python 2)
├── oaichat\                ← Client/Serveur Gemini (ZMQ)
├── pepperspeechrecognition\  ← Module reconnaissance vocale
└── pynaoqi-python2.7-2.5.7.1-win32-vs2013\  ← SDK NAOqi Windows
```

---

## Architecture technique

```
                    ┌─────────────────────────┐
                    │     Robot Pepper         │
                    │  (NAOqi port 9559)       │
                    └────────┬────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                   │
   ┌──────▼───────┐  ┌──────▼───────┐          │
   │ Speech Recog │  │  Dialogue    │          │
   │ (Python 2.7) │  │  (Python 2.7)│          │
   └──────┬───────┘  └──────┬───────┘          │
          │ TCP:8889         │ ZMQ:5556         │
   ┌──────▼───────┐  ┌──────▼───────┐          │
   │  STT Google  │  │ Gemini Server│          │
   │ (Python 3)   │  │ (Python 3)   │          │
   └──────────────┘  └──────────────┘          │
```
