# ============================================================
# Dockerfile — PepperChat (services Python 3)
#
# ⚠️  Ce Dockerfile couvre UNIQUEMENT les services Python 3 :
#     google_stt_server.py, startDialogueServer_background.py,
#     PepperWebLocal/main.py
#
# Les modules module_dialogue.py et module_speechrecognition.py
# nécessitent Python 2.7 + le SDK NaoQI (Windows uniquement) et
# doivent être lancés DIRECTEMENT sur la machine hôte.
# Voir README.md pour les instructions complètes.
# ============================================================

FROM python:3.10-slim

# Dépendances système minimales (compiler certaines libs C)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installer les dépendances Python en premier (couche cachée)
COPY requirements.py3.txt .
RUN pip install --no-cache-dir -r requirements.py3.txt

# Copier le code source
COPY . .

# Variable d'environnement pour afficher les logs sans buffer
ENV PYTHONUNBUFFERED=1
