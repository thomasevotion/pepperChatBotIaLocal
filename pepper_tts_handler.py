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

tts = ALProxy("ALTextToSpeech", PEPPER_IP, PEPPER_PORT)
posture = ALProxy("ALRobotPosture", PEPPER_IP, PEPPER_PORT)
leds = ALProxy("ALLeds", PEPPER_IP, PEPPER_PORT)

def clean_text_for_tts(text):
    if isinstance(text, unicode):
        text = text.encode('latin-1', 'ignore')
    elif isinstance(text, str):
        try:
            text = text.decode('utf-8', 'ignore').encode('latin-1', 'ignore')
        except:
            pass
    return re.sub(r'[\x00-\x1f\x7f]', '', text.decode('latin-1')).strip()

def init_pepper_tts():
    tts.setLanguage("French")
    posture.goToPosture("Stand", 0.8)
    time.sleep(2)
    leds.fadeRGB("FaceLeds", 0.0, 0.0, 0.0, 1.0)

def get_all_response_files():
    if not os.path.isdir(TTS_RESPONSE_DIR):
        return []
    files = [f for f in os.listdir(TTS_RESPONSE_DIR) if f.endswith(".txt")]
    files.sort()
    return [os.path.join(TTS_RESPONSE_DIR, f) for f in files]

def monitor_tts_responses_led():
    """Version avec LED et TTS phrase par phrase"""
    init_pepper_tts()
    
    while True:
        # Mode ecoute : yeux verts
        leds.fadeRGB("FaceLeds", 0.0, 1.0, 0.0, 0.5)
        
        files = get_all_response_files()
        if files:
            # Mode parole : yeux violets
            leds.fadeRGB("FaceLeds", 1.0, 0.0, 1.0, 0.5)
            
            # Cree flag anti-boucle
            with open(TTS_ACTIVE_FLAG, "w") as f:
                f.write("speaking")
            
            # Dit chaque phrase
            for path in files:
                try:
                    with codecs.open(path, "r", encoding="utf-8") as f:
                        sentence = f.read().strip()
                    os.remove(path)
                    
                    clean_sentence = clean_text_for_tts(sentence)
                    if clean_sentence:
                        print("Pepper dit: {}".format(clean_sentence))
                        tts.say(str(clean_sentence))  # TTS bloquant
                        time.sleep(0.3)  # Pause entre phrases
                except Exception as e:
                    print("Erreur TTS: {}".format(e))
                    try:
                        os.remove(path)
                    except:
                        pass
            
            # Supprime flag et eteint violets
            if os.path.exists(TTS_ACTIVE_FLAG):
                os.remove(TTS_ACTIVE_FLAG)
            leds.fadeRGB("FaceLeds", 0.0, 0.0, 0.0, 1.0)
            
        time.sleep(0.2)

if __name__ == "__main__":
    if os.path.exists(TTS_ACTIVE_FLAG): 
        os.remove(TTS_ACTIVE_FLAG)
    if os.path.isdir(TTS_RESPONSE_DIR):
        for f in os.listdir(TTS_RESPONSE_DIR):
            try: 
                os.remove(os.path.join(TTS_RESPONSE_DIR, f))
            except: 
                pass
    print("TTS Pepper avec LED - phrases completes pret")
    monitor_tts_responses_led()
