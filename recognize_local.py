# recognize_local.py -- Python 3 (à placer avec module_speechrecognition.py)
import os
import time
import soundfile as sf
from vosk import Model, KaldiRecognizer
import wave
import json

SAMPLE_RATE = 48000
MODEL_PATH = r"C:\Users\thoma\Travail\pepperchat-master\vosk-model-fr-0.22"
#MODEL_PATH = "vosk-model-fr-0.22"
AUDIO_FILENAME = "audio_pepper.wav"

vosk_model = Model(MODEL_PATH)
print("Vosk model loaded.")

def recognize_wav(path):
    wf = wave.open(path, "rb")
    rec = KaldiRecognizer(vosk_model, wf.getframerate())
    txt = ''
    while True:
        buf = wf.readframes(4000)
        if len(buf) == 0:
            break
        if rec.AcceptWaveform(buf):
            txt += json.loads(rec.Result()).get('text','')
    txt += json.loads(rec.FinalResult()).get('text','')
    print("---RESULT---: " + txt.strip())
    with open("stt_result.txt", "w", encoding="utf-8") as f:
        f.write(txt.strip())

print("Attente de fichiers audio (Ctrl+C pour quitter)...")
while True:
    if os.path.exists(AUDIO_FILENAME):
        try:
            recognize_wav(AUDIO_FILENAME)
            os.remove(AUDIO_FILENAME)
        except Exception as e:
            print("Erreur reco :", e)
    time.sleep(0.5)
