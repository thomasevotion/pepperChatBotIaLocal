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

anim_tts = ALProxy("ALAnimatedSpeech", PEPPER_IP, PEPPER_PORT)
posture  = ALProxy("ALRobotPosture",    PEPPER_IP, PEPPER_PORT)
leds      = ALProxy("ALLeds",            PEPPER_IP, PEPPER_PORT)
motion    = ALProxy("ALMotion",          PEPPER_IP, PEPPER_PORT)

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
    # Met Pepper debout et active la rigidité
    posture.goToPosture("Stand", 0.8)
    motion.setStiffnesses("Body", 1.0)
    # Active les mouvements contextuels
    anim_tts.setBodyLanguageMode(1)  # 1 = contextual gestures
    time.sleep(1)
    leds.fadeRGB("FaceLeds", 0.0, 0.0, 0.0, 1.0)

def get_all_response_files():
    if not os.path.isdir(TTS_RESPONSE_DIR):
        return []
    files = [f for f in os.listdir(TTS_RESPONSE_DIR) if f.endswith(".txt")]
    files.sort()
    return [os.path.join(TTS_RESPONSE_DIR, f) for f in files]

def monitor_tts_responses_led():
    """TTS avec ALAnimatedSpeech, LEDs et mouvements contextuels."""
    init_pepper_tts()

    while True:
        # Mode écoute : yeux verts
        leds.fadeRGB("FaceLeds", 0.0, 1.0, 0.0, 0.5)

        files = get_all_response_files()
        if files:
            # Mode parole : yeux violets
            leds.fadeRGB("FaceLeds", 1.0, 0.0, 1.0, 0.5)
            # Bloque STT
            with open(TTS_ACTIVE_FLAG, "w") as f:
                f.write("speaking")

            for path in files:
                try:
                    with codecs.open(path, "r", encoding="utf-8") as f:
                        sentence = f.read().strip()
                    os.remove(path)
                except:
                    continue

                clean_sentence = clean_text_for_tts(sentence)
                if clean_sentence:
                    print("Pepper dit:", clean_sentence)
                    # ALAnimatedSpeech gère les gestes automatiquement
                    anim_tts.say(clean_sentence.encode('utf-8'))
                    time.sleep(0.2)

            # Fin parole : LEDs off + libère STT
            leds.fadeRGB("FaceLeds", 0.0, 0.0, 0.0, 1.0)
            if os.path.exists(TTS_ACTIVE_FLAG):
                os.remove(TTS_ACTIVE_FLAG)

        time.sleep(0.1)

if __name__ == "__main__":
    # Nettoyage initial
    if os.path.exists(TTS_ACTIVE_FLAG):
        os.remove(TTS_ACTIVE_FLAG)
    if os.path.isdir(TTS_RESPONSE_DIR):
        for f in os.listdir(TTS_RESPONSE_DIR):
            try:
                os.remove(os.path.join(TTS_RESPONSE_DIR, f))
            except:
                pass

    print("TTS Pepper avec ALAnimatedSpeech contextuel prêt.")
    monitor_tts_responses_led()
