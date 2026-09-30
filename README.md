# PepperChat — Guide d'utilisation

> **Branche `Local` : tout tourne sur le PC, aucune donnée ne part sur Internet.**
> - Reconnaissance vocale : **Whisper** (faster-whisper, GPU) au lieu de Google Speech
> - IA de dialogue : **Ollama** (`qwen3.5`, multilingue + vision caméra) au lieu de Gemini
> - Synthèse vocale : voix NAOqi du robot (déjà locale)
>
> Voir la section [Mode 100 % local](#mode-100--local) plus bas.

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
| STT | Reconnaissance vocale locale Whisper | Python 3 |
| IA | Serveur IA local Ollama (ZMQ) | Python 3 |
| Speech Recognition | Module audio Pepper → STT | Python 2.7 |
| Dialogue NaoQI | Module dialogue principal | Python 2.7 |

### Mode Immobile ou Mobile
Réglé dans `.env` (lu par `START_APP.bat`, aucune question au lancement) :

| Variable | Valeurs | Rôle |
|----------|---------|------|
| `PEPPER_MOBILE` | `0` (défaut) / `1` | 1 : Pepper se déplace (6ᵉ fenêtre *PepperChat Navigation*) |
| `MAP` | vide / chemin `.explo` sur le robot | Vide : Pepper crée une nouvelle carte ; sinon il reprend cette carte |
| `NAV_RADIUS` | `3` | Rayon d'exploration (m) quand `MAP` est vide |

Avec `MAP` vide, Pepper explore seul au lancement (dégager la zone), puis la fenêtre Navigation
affiche le chemin de la carte créée : le copier dans `MAP=` pour la reprendre ensuite. Pour
reprendre une carte, placer Pepper à l'endroit où elle a été créée avant de lancer
`START_APP.bat`.

En mode mobile, Pepper se promène en continu (marche avant uniquement) dans un rayon de
`NAV_RADIUS` autour de son point de départ. **L'évitement d'obstacles est prioritaire** : il choisit
en permanence la direction la plus dégagée (lasers + sonar), ralentit à l'approche d'un obstacle
et tourne sur place s'il est bloqué ; la protection anti-collision de NAOqi reste active en
dernier recours.

- **Il voit un visage** (< 2,5 m) : il s'arrête, se tourne vers la personne, dit bonjour et attend
  30 s une réponse.
- **Pas de réponse**, ou « pars », « continue », « au revoir », « non merci »… : il répond
  « D'accord, à bientôt ! », se détourne et reprend sa promenade.
- **On lui parle pendant qu'il roule** : il s'arrête et discute ; il repart après 30 s sans
  parole.

Réglages fins (vitesses, distances, délais) en haut de `pepper_navigation.py`. `STOP_APP.bat`
arrête d'abord tous les déplacements du robot.

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
- Contient : `ROBOT_IP`, `LLM_BACKEND`, `OLLAMA_MODEL`, `WHISPER_MODEL`, `CHATBOT_SERVER_ADDRESS`, etc.

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
├── local_stt_server.py     ← Serveur STT local Whisper (Python 3)
├── google_stt_server.py    ← Ancien serveur STT Google (en ligne, non utilisé)
├── startDialogueServer_background.py  ← Serveur IA (Ollama local ou Gemini) (Python 3)
├── module_speechrecognition.py  ← Module audio Pepper (Python 2)
├── module_dialogue.py      ← Module dialogue Pepper (Python 2)
├── oaichat\                ← Client/Serveur IA (ZMQ) : localchat.py (Ollama), openaichat.py (Gemini)
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
   │ STT Whisper  │  │  Serveur IA  │          │
   │ (Python 3)   │  │  (Python 3)  │          │
   └──────────────┘  └──────┬───────┘          │
                            │ HTTP:11434        │
                     ┌──────▼───────┐          │
                     │    Ollama    │          │
                     │ (qwen3.5 GPU)│          │
                     └──────────────┘          │
```

---

## Mode 100 % local

### Matériel conseillé
- GPU NVIDIA avec **8 Go de VRAM** minimum (testé sur RTX 4070 Laptop 8 Go)
- ~15 Go d'espace disque libre pour les modèles

Sans GPU, tout fonctionne sur CPU mais la latence devient trop élevée pour une conversation
fluide (utiliser alors `WHISPER_MODEL=small` et `OLLAMA_MODEL=qwen3.5:4b`).

### Installation
`INSTALL_APP.bat` s'occupe de tout : installation d'Ollama (winget), téléchargement du modèle
IA et du modèle Whisper. Ensuite plus aucune connexion Internet n'est nécessaire.

Les modèles occupent ~8 Go (qwen3.5:9b 6,6 Go + Whisper 1,5 Go). Si le disque `C:` manque de
place, changer le dossier des modèles **avant** l'installation : icône Ollama (barre des tâches)
→ *Settings* → *Model location* (ex. `E:\ollama_models`). L'application Ollama impose ce réglage
et ignore la variable d'environnement `OLLAMA_MODELS`.

### Performances mesurées (RTX 4070 Laptop 8 Go)

| Étape | Temps |
|-------|-------|
| Transcription Whisper (fin de parole → texte) | ~0,5-0,8 s |
| Premier mot de l'IA (qwen3.5:9b) | ~0,25-0,6 s |
| Tour avec image caméra | ~4 s |

Point d'attention : toujours utiliser `127.0.0.1` et non `localhost` pour joindre Ollama sous
Windows (sinon +2 s par requête, tentative IPv6).

### Réglages `.env`

| Variable | Défaut | Rôle |
|----------|--------|------|
| `LLM_BACKEND` | `ollama` | `ollama` (local) ou `gemini` (en ligne, nécessite `GEMINI_API_KEY`) |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Modèle de dialogue (multilingue, lit aussi les images caméra) |
| `OLLAMA_VISION_MODEL` | = `OLLAMA_MODEL` | Modèle pour les tours avec image, si le modèle principal ne voit pas |
| `OLLAMA_THINK` | `false` | Réflexion des modèles Qwen (plus intelligent mais +plusieurs secondes) |
| `WHISPER_MODEL` | `large-v3-turbo` | Modèle STT (`small`/`medium` si pas de GPU) |
| `WHISPER_LANGUAGES` | `fr,en,es` | Langues reconnues automatiquement (codes ISO, ex. `fr,en,es,de,it,ja`) |
| `WHISPER_BEAM_SIZE` | `1` | 1 = plus rapide, 5 = un peu plus précis en milieu bruyant |

Tester l'IA seule, sans le robot : `py -3 -m oaichat.localchat`

