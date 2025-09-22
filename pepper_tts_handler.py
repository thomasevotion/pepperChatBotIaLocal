#!/usr/bin/env python
# pepper_tts_handler.py -- Python 2 pour TTS Pepper (ASCII pur)

import os
import time
import codecs
import re
from naoqi import ALProxy

PEPPER_IP = "192.168.1.58"
PEPPER_PORT = 9559
TTS_RESPONSE_FILE = "tts_response.txt"

def clean_text_for_tts(text):
    """Nettoie le texte pour le TTS"""
    if isinstance(text, unicode):
        text = text.encode('ascii', 'ignore')
    elif isinstance(text, str):
        try:
            text = text.decode('utf-8', 'ignore').encode('ascii', 'ignore')
        except:
            pass
    
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    return text.strip()

def init_pepper_tts():
    """Initialise la connexion TTS avec Pepper"""
    try:
        tts = ALProxy("ALTextToSpeech", PEPPER_IP, PEPPER_PORT)
        tts.setLanguage("French")
        return tts
    except Exception as e:
        print("Erreur connexion Pepper TTS:", e)
        return None

def monitor_tts_responses(tts):
    """Surveille les reponses a faire prononcer par Pepper"""
    last_response = ""
    
    while True:
        if os.path.exists(TTS_RESPONSE_FILE):
            try:
                with codecs.open(TTS_RESPONSE_FILE, "r", encoding="utf-8") as f:
                    response = f.read().strip()
                
                if response and response != last_response:
                    clean_response = clean_text_for_tts(response)
                    
                    if clean_response:
                        print("Pepper dit:", clean_response)
                        tts.say(str(clean_response))
                    else:
                        print("Texte vide apres nettoyage")
                    
                    last_response = response
                    with open(TTS_RESPONSE_FILE, "w") as f:
                        f.write("")
                    
            except Exception as e:
                print("Erreur TTS:", e)
        
        time.sleep(0.3)

if __name__ == "__main__":
    print("Initialisation TTS Pepper...")
    tts = init_pepper_tts()
    
    if tts:
        print("TTS Pepper pret!")
        monitor_tts_responses(tts)
    else:
        print("Impossible de se connecter a Pepper!")
