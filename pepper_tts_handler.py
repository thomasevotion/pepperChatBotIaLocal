#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import codecs
import re
from naoqi import ALProxy

PEPPER_IP = "192.168.1.58"
PEPPER_PORT = 9559
TTS_RESPONSE_DIR = "tts_responses"
TTS_ACTIVE_FLAG = "pepper_speaking.flag"

def clean_text_for_tts(text):
    """Nettoie le texte pour le TTS en conservant les caractères Latin-1 (accents)"""
    if isinstance(text, unicode):
        # Encode en Latin-1 en ignorant les caractères hors plage
        text = text.encode('latin-1', 'ignore')
    elif isinstance(text, str):
        try:
            # Décode UTF-8 puis encode Latin-1
            text = text.decode('utf-8', 'ignore').encode('latin-1', 'ignore')
        except:
            pass
    # Supprime seulement les contrôles non imprimables
    return re.sub(r'[\x00-\x1f\x7f]', '', text.decode('latin-1')).strip()

def init_pepper_tts():
    """Initialise TTS et posture debout (voix par défaut)"""
    try:
        tts = ALProxy("ALTextToSpeech", PEPPER_IP, PEPPER_PORT)
        posture = ALProxy("ALRobotPosture", PEPPER_IP, PEPPER_PORT)
        
        tts.setLanguage("French")
        # Paramètres par défaut (pas de modification de speed/pitch)
        
        posture.goToPosture("Stand", 0.8)
        time.sleep(2)
        
        return tts, posture
        
    except Exception as e:
        print("Erreur connexion Pepper:", e)
        return None, None

def get_all_response_files():
    """Retourne tous les fichiers .txt du dossier triés"""
    if not os.path.isdir(TTS_RESPONSE_DIR):
        return []
    files = [f for f in os.listdir(TTS_RESPONSE_DIR) if f.endswith(".txt")]
    files.sort()
    return [os.path.join(TTS_RESPONSE_DIR, f) for f in files]

def monitor_tts_responses_fluid(tts, posture):
    """Accumulateur pour un rendu fluide sans saccades, délais personnalisés"""
    buffer = ""
    last_write = time.time()
    
    while True:
        files = get_all_response_files()
        
        # Lecture des fichiers
        for path in files:
            try:
                with codecs.open(path, "r", encoding="utf-8") as f:
                    chunk = f.read().strip()
                os.remove(path)
                clean = clean_text_for_tts(chunk)
                if clean:
                    buffer += clean + " "
                    last_write = time.time()
            except:
                continue
        
        if buffer:
            elapsed = time.time() - last_write
            
            # Si le dernier caractère est une ponctuation, on parle plus vite :
            ends_with_punct = buffer.strip()[-1] in ".!?"
            # Délai normal : 0.5s ; après ponctuation on parle dès 0.2s
            threshold = 0.2 if ends_with_punct else 0.5
            
            if elapsed > threshold:
                with open(TTS_ACTIVE_FLAG, "w") as f:
                    f.write("1")
                
                text = buffer.strip()
                print("Pepper dit:", text)
                
                try:
                    if posture.getPosture() != "Stand":
                        posture.goToPosture("Stand", 0.6)
                except:
                    pass
                
                tts.say(str(text))
                
                buffer = ""
                if os.path.exists(TTS_ACTIVE_FLAG):
                    os.remove(TTS_ACTIVE_FLAG)
        
        time.sleep(0.1)


if __name__ == "__main__":
    print("Init TTS fluide (voix par défaut) pour Pepper...")
    
    if os.path.exists(TTS_ACTIVE_FLAG):
        os.remove(TTS_ACTIVE_FLAG)
    if os.path.isdir(TTS_RESPONSE_DIR):
        for f in os.listdir(TTS_RESPONSE_DIR):
            try: os.remove(os.path.join(TTS_RESPONSE_DIR, f))
            except: pass
    
    tts, posture = init_pepper_tts()
    if tts and posture:
        print("TTS fluide prêt!")
        monitor_tts_responses_fluid(tts, posture)
    else:
        print("Impossible de connecter à Pepper")
