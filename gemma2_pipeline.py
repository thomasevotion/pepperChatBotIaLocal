#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import requests
import json

GEMMA2_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma2:9b"
STT_FILE = "stt_result.txt"
TTS_RESPONSE_DIR = "tts_responses"

with open("pepper_prompt.txt", "r", encoding="utf-8") as f:
    PEPPER_SYSTEM_PROMPT = f.read()

def clean_response_for_windows(text):
    if isinstance(text, str):
        text = text.encode('ascii', 'ignore').decode('ascii')
    return text.strip()

def create_tts_response_file(text, chunk_id):
    if not os.path.exists(TTS_RESPONSE_DIR):
        os.makedirs(TTS_RESPONSE_DIR)
    timestamp = int(time.time() * 1000)
    filename = os.path.join(TTS_RESPONSE_DIR, "response_{:d}_{:03d}.txt".format(timestamp, chunk_id))
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        print("Groupe sauve: [{}]".format(text))
        return filename
    except Exception as e:
        print("Erreur sauvegarde: {}".format(e))
        return None

def send_to_gemma2_streaming_sentence(user_input):
    """Version phrase par phrase au lieu de groupes de mots"""
    full_prompt = PEPPER_SYSTEM_PROMPT + user_input
    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 150
        }
    }
    try:
        response = requests.post(GEMMA2_URL, json=payload, stream=True, timeout=60)
        if response.status_code != 200:
            print("Erreur Gemma2 HTTP {}".format(response.status_code))
            return False

        accumulated_text = ""
        chunk_counter = 0

        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode('utf-8'))
                if 'response' not in data:
                    continue
                token = data['response']
                accumulated_text += token

                # Envoie par phrase complète (ponctuation forte)
                if any(p in token for p in '.!?'):
                    clean_text = clean_response_for_windows(accumulated_text)
                    if clean_text:
                        create_tts_response_file(clean_text, chunk_counter)
                        chunk_counter += 1
                        time.sleep(0.2)
                    accumulated_text = ""
            except:
                continue

        # Envoie le reste
        if accumulated_text.strip():
            clean_text = clean_response_for_windows(accumulated_text.strip())
            if clean_text:
                create_tts_response_file(clean_text, chunk_counter)

        return True

    except Exception as e:
        msg = str(e).encode('ascii', 'ignore').decode('ascii')
        print("Erreur connexion Gemma2: {}".format(msg))
        return False

def monitor_stt_and_respond():
    last_text = ""
    print("Pepper AI Pipeline - STREAMING PHRASES COMPLETES actif")
    print("Surveillance du fichier: {}".format(STT_FILE))

    while True:
        if os.path.exists(STT_FILE):
            try:
                with open(STT_FILE, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text and text != last_text:
                    print("Utilisateur dit: {}".format(text))
                    result = send_to_gemma2_streaming_sentence(text)
                    print("Streaming Pepper: {}".format("OK" if result else "ERREUR"))
                    last_text = text
                try:
                    os.remove(STT_FILE)
                except:
                    with open(STT_FILE, "w") as f:
                        f.write("")
            except Exception as e:
                msg = str(e).encode('ascii', 'ignore').decode('ascii')
                print("Erreur traitement: {}".format(msg))
        time.sleep(0.2)

if __name__ == "__main__":
    print("=== PEPPER AI CHATBOT - STREAMING PHRASES COMPLETES ===")
    if os.path.isdir(TTS_RESPONSE_DIR):
        for f in os.listdir(TTS_RESPONSE_DIR):
            try:
                os.remove(os.path.join(TTS_RESPONSE_DIR, f))
            except:
                pass
    monitor_stt_and_respond()
