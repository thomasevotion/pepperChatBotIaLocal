#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import time
import requests
import json
import datetime

GEMMA2_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma2:9b"
STT_FILE = "stt_result.txt"
TTS_RESPONSE_DIR = "tts_responses"

# PROMPT SYSTÈME PEPPER
with open("pepper_prompt.txt", "r", encoding="utf-8") as f:
    PEPPER_SYSTEM_PROMPT = f.read()

def clean_response_for_windows(text):
    """Nettoie la reponse pour l'affichage Windows"""
    if isinstance(text, str):
        text = text.encode('ascii', 'ignore').decode('ascii')
    return text.strip()

def create_tts_response_file(text):
    """Cree un fichier de reponse unique avec timestamp"""
    if not os.path.exists(TTS_RESPONSE_DIR):
        os.makedirs(TTS_RESPONSE_DIR)
    
    timestamp = int(time.time() * 1000)
    filename = os.path.join(TTS_RESPONSE_DIR, f"response_{timestamp}.txt")
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Reponse sauvee: {filename}")
        return filename
    except Exception as e:
        print(f"Erreur sauvegarde: {e}")
        return None

def send_to_gemma2_streaming(user_input):
    # Construit le prompt complet avec le contexte Pepper
    full_prompt = PEPPER_SYSTEM_PROMPT + user_input
    
    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 150  # Limite pour des réponses courtes
        }
    }
    
    try:
        response = requests.post(GEMMA2_URL, json=payload, stream=True, timeout=60)
        if response.status_code == 200:
            full_text = ""
            
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line.decode('utf-8'))
                        if 'response' in data:
                            chunk = data['response']
                            full_text += chunk
                            
                            # Envoie par phrases completes
                            if chunk.endswith(('.', '!', '?')) and len(full_text.strip()) > 10:
                                clean_text = clean_response_for_windows(full_text)
                                create_tts_response_file(clean_text)
                                print("Pepper repond:", clean_text[:50] + "...")
                                full_text = ""
                                time.sleep(0.2)
                    except Exception as e:
                        continue
            
            # Envoie le reste
            if full_text.strip():
                clean_text = clean_response_for_windows(full_text)
                create_tts_response_file(clean_text)
                print("Reponse finale Pepper:", clean_text[:50] + "...")
            
            return True
        else:
            print("Erreur Gemma2 HTTP", response.status_code)
            return False
            
    except Exception as e:
        print("Erreur connexion Gemma2:", str(e).encode('ascii', 'ignore').decode('ascii'))
        return False

def monitor_stt_and_respond():
    last_text = ""
    print("Pepper AI Pipeline actif - Surveillance:", STT_FILE)
    print("Prompt système:", PEPPER_SYSTEM_PROMPT[:100] + "...")
    
    while True:
        if os.path.exists(STT_FILE):
            try:
                with open(STT_FILE, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                
                if text and text != last_text:
                    print("Utilisateur dit:", text)
                    result = send_to_gemma2_streaming(text)
                    print("Traitement Pepper:", "OK" if result else "ERREUR")
                    last_text = text
                    
                    # Efface le fichier
                    try:
                        os.remove(STT_FILE)
                    except:
                        try:
                            with open(STT_FILE, "w") as f:
                                f.write("")
                        except:
                            pass
                    
            except Exception as e:
                print("Erreur traitement:", str(e).encode('ascii', 'ignore').decode('ascii'))
        
        time.sleep(0.2)

if __name__ == "__main__":
    print("=== PEPPER AI CHATBOT ===")
    print("Demarrage pipeline Pepper avec personnalite...")
    
    # Nettoie le dossier au demarrage
    if os.path.exists(TTS_RESPONSE_DIR):
        for f in os.listdir(TTS_RESPONSE_DIR):
            try:
                os.remove(os.path.join(TTS_RESPONSE_DIR, f))
            except:
                pass
    
    # Test connexion Ollama
    try:
        test_response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if test_response.status_code == 200:
            print("Connexion Ollama/Gemma2 OK")
        else:
            print("Ollama non accessible, code:", test_response.status_code)
    except Exception as e:
        print("Erreur connexion Ollama:", str(e).encode('ascii', 'ignore').decode('ascii'))
        print("Verifiez qu'Ollama tourne sur localhost:11434")
    
    monitor_stt_and_respond()
