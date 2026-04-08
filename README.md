# PepperChat — Guide d'utilisation

## ▶️ Démarrer l'application

**Double-cliquez sur `START_APP.bat`**

C'est tout. Le script s'occupe de tout démarrer automatiquement.

---

## ⏹️ Arrêter l'application

**Double-cliquez sur `STOP_APP.bat`**

---

## ✅ Prérequis (à vérifier avant le premier lancement)

### 1. Docker Desktop
- Télécharger et installer : https://www.docker.com/products/docker-desktop
- **Docker Desktop doit être ouvert et démarré** (icône baleine visible dans la barre des tâches) avant de lancer `START_APP.bat`

### 2. Python 2.7 + SDK NaoQI
- Python 2.7 doit être installé dans `C:\Python27\`
- Le SDK NaoQI doit être présent dans `C:\Python27\Lib\site-packages\` (fichiers `naoqi.py`, `qi\`, etc.)
- *(Fournis par votre intégrateur)*

### 3. Fichier de configuration `.env`
- Le fichier `.env` doit être présent à la racine du dossier `pepperchat-master\`
- Vérifier que `ROBOT_IP=` contient bien l'adresse IP de votre robot Pepper sur le réseau local
- Exemple : `ROBOT_IP=192.168.1.76`

### 4. Connexion réseau
- Le PC et le robot Pepper doivent être **sur le même réseau Wi-Fi ou câble**

---

## 🔧 En cas de problème

| Symptôme | Solution |
|----------|----------|
| « Docker Desktop n'est pas démarré » | Ouvrir Docker Desktop, attendre l'icône baleine, relancer `START_APP.bat` |
| Le robot ne répond pas | Vérifier que `ROBOT_IP` dans `.env` est correct. Tester : `ping 192.168.1.76` dans un terminal |
| Une fenêtre s'ouvre et se ferme immédiatement | Contacter le support technique |
| Erreur « python.exe introuvable » | Vérifier l'installation de Python 2.7 dans `C:\Python27\` |

---

## 📂 Structure des fichiers importants

```
pepperchat-master\
├── START_APP.bat          ← Démarrer l'application
├── STOP_APP.bat           ← Arrêter l'application
├── .env                   ← Configuration (IP robot, clés API)
├── credentials.json       ← Identifiants Google Cloud (ne pas supprimer)
└── docker-compose.yml     ← Configuration des services Docker (ne pas modifier)
```

---

## ℹ️ Architecture technique (pour information)

L'application lance automatiquement 5 services dans l'ordre :

| # | Service | Technologie |
|---|---------|-------------|
| 1 | Serveur IA Gemini | Docker (Python 3) |
| 1 | Reconnaissance vocale Google | Docker (Python 3) |
| 2 | Interface web tablette | Docker (Python 3) |
| 2 | Module reconnaissance vocale Pepper | Python 2.7 (hôte Windows) |
| 3 | Module dialogue Pepper | Python 2.7 (hôte Windows) |
