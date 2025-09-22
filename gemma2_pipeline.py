# gemma2_pipeline.py -- Pipeline complet STT → Gemma2 → envoi TTS
import os
import time
import requests
import json

# Configuration Gemma2 (adapte selon ton setup)
GEMMA2_URL = "http://localhost:11434/api/generate"  # Ollama par défaut
MODEL_NAME = "gemma2:9b"

STT_FILE = "stt_result.txt"
TTS_RESPONSE_FILE = "tts_response.txt"

def send_to_gemma2(prompt):
    """Envoie le prompt à Gemma2 via Ollama et retourne la réponse"""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False  # Mettre True pour streaming si voulu
    }
    
    try:
        response = requests.post(GEMMA2_URL, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result.get("response", "").strip()
        else:
            print(f"Erreur Gemma2 HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"Erreur connexion Gemma2: {e}")
        return None

def monitor_stt_and_respond():
    """Surveille le fichier STT et traite les nouvelles transcriptions"""
    last_text = ""
    
    while True:
        if os.path.exists(STT_FILE):
            try:
                with open(STT_FILE, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                
                if text and text != last_text:
                    print(f"Nouvelle transcription: {text}")
                    
                    # Envoie à Gemma2
                    response = send_to_gemma2(text)
                    
                    if response:
                        print(f"Réponse Gemma2: {response}")
                        
                        # Écrit la réponse pour le TTS
                        with open(TTS_RESPONSE_FILE, "w", encoding="utf-8") as f:
                            f.write(response)
                    
                    last_text = text
                    # Efface le fichier STT après traitement
                    open(STT_FILE, "w").close()
                    
            except Exception as e:
                print(f"Erreur traitement: {e}")
        
        time.sleep(0.3)

if __name__ == "__main__":
    print("Démarrage pipeline Gemma2...")
    print(f"URL Gemma2: {GEMMA2_URL}")
    print(f"Modèle: {MODEL_NAME}")
    monitor_stt_and_respond()
