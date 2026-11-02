#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import torch
import whisper

# Fichiers et paramètres
AUDIO_FILENAME = "audio_pepper.wav"
STT_RESULT_FILE = "stt_result.txt"
LANGUAGE = "fr"

# Choix du device GPU/CPU
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Chargement du modèle Whisper large sur {device}...")
model = whisper.load_model("large").to(device)
print("Modèle chargé.")

def transcribe(path):
    """Transcrit un fichier audio en texte français avec Whisper."""
    result = model.transcribe(path, language=LANGUAGE)
    text = result.get("text", "").strip()
    print("---RESULT---:", text)
    return text

def main():
    print("Attente de fichiers audio (Ctrl+C pour quitter)...")
    try:
        while True:
            if os.path.exists(AUDIO_FILENAME):
                try:
                    text = transcribe(AUDIO_FILENAME)
                    if text:
                        with open(STT_RESULT_FILE, "w", encoding="utf-8") as f:
                            f.write(text)
                    os.remove(AUDIO_FILENAME)
                except Exception as e:
                    print("Erreur transcription:", e)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Arrêt par l'utilisateur.")

if __name__ == "__main__":
    main()
