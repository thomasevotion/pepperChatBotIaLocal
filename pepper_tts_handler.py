#!/usr/bin/env python
# pepper_tts_handler.py -- Surveille un dossier de reponses

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

def init_pepper_services():
    """Initialise TTS et Posture"""
    try:
        tts = ALProxy("ALTextToSpeech", PEPPER_IP, PEPPER_PORT)
        posture = ALProxy("ALRobotPosture", PEPPER_IP, PEPPER_PORT)
        
        tts.setLanguage("French")
        
        print("Mise en position debout...")
        posture.goToPosture("Stand", 0.8)
        time.sleep(2)
        
        return tts, posture
        
    except Exception as e:
        print("Erreur connexion Pepper:", e)
        return None, None

def get_oldest_response_file():
    """Trouve le plus ancien fichier de reponse"""
    if not os.path.exists(TTS_RESPONSE_DIR):
        return None
    
    files = [f for f in os.listdir(TTS_RESPONSE_DIR) if f.endswith('.txt')]
    if not files:
        return None
    
    # Trie par nom (timestamp) pour avoir le plus ancien
    files.sort()
    return os.path.join(TTS_RESPONSE_DIR, files[0])

def monitor_tts_responses(tts, posture):
    """Surveille le dossier de reponses"""
    processed_files = set()
    
    while True:
        try:
            response_file = get_oldest_response_file()
            
            if response_file and response_file not in processed_files:
                try:
                    with codecs.open(response_file, "r", encoding="utf-8") as f:
                        response = f.read().strip()
                    
                    if response:
                        clean_response = clean_text_for_tts(response)
                        
                        if clean_response:
                            # Cree le flag AVANT de parler
                            with open(TTS_ACTIVE_FLAG, "w") as f:
                                f.write("speaking")
                            
                            print("Pepper dit:", clean_response)
                            
                            # Remet debout si necessaire
                            try:
                                current_posture = posture.getPosture()
                                if current_posture != "Stand":
                                    print("Remise en position debout...")
                                    posture.goToPosture("Stand", 0.6)
                            except:
                                pass
                            
                            # PARLE
                            tts.say(str(clean_response))
                            
                            # Supprime le flag APRES avoir parle
                            if os.path.exists(TTS_ACTIVE_FLAG):
                                os.remove(TTS_ACTIVE_FLAG)
                            
                            print("Pepper a fini de parler")
                    
                    # Supprime le fichier traite
                    os.remove(response_file)
                    processed_files.add(response_file)
                    
                except Exception as e:
                    print("Erreur traitement fichier:", e)
                    # Supprime le fichier meme en cas d'erreur
                    try:
                        os.remove(response_file)
                    except:
                        pass
        
        except Exception as e:
            print("Erreur surveillance:", e)
        
        time.sleep(0.1)

if __name__ == "__main__":
    print("Initialisation TTS et Posture Pepper...")
    
    # Nettoie au demarrage
    if os.path.exists(TTS_ACTIVE_FLAG):
        os.remove(TTS_ACTIVE_FLAG)
    
    if os.path.exists(TTS_RESPONSE_DIR):
        for f in os.listdir(TTS_RESPONSE_DIR):
            try:
                os.remove(os.path.join(TTS_RESPONSE_DIR, f))
            except:
                pass
    
    tts, posture = init_pepper_services()
    
    if tts and posture:
        print("TTS Pepper pret, surveillance dossier active!")
        monitor_tts_responses(tts, posture)
    else:
        print("Impossible de se connecter a Pepper!")
