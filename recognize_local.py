# -*- coding: utf-8 -*-
"""
recognize_local.py

Écoute des chunks audio 48 kHz, 16 bits mono de 50 ms,
enregistre le flux brut en WAV, regroupe 1 s d’audio pour Whisper.
"""

import socket
import time
import wave
import os
import numpy as np
import librosa
from faster_whisper import WhisperModel

HOST         = "0.0.0.0"
PORT         = 11434
ORIG_SR      = 48000             # Fréquence d’origine
TARGET_SR    = 16000             # Fréquence attendue par Whisper
SAMPWIDTH    = 2                 # 16 bits = 2 octets
CHANNELS     = 1
CHUNK_BYTES  = int(ORIG_SR * 0.05 * SAMPWIDTH)  # 50 ms
WINDOW_SEC   = 1.0
WINDOW_BYTES = int(ORIG_SR * WINDOW_SEC * SAMPWIDTH)
OUTPUT_WAV   = "received_full.wav"

model = WhisperModel("small", device="cpu", compute_type="int8")

def main():
    # Supprime l'ancien WAV
    if os.path.exists(OUTPUT_WAV):
        os.remove(OUTPUT_WAV)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, PORT))
    sock.listen(1)
    print(f"🎧 En attente de connexion sur {HOST}:{PORT}…")
    conn, addr = sock.accept()
    print("🔌 Connecté par", addr)

    buffer = b""
    all_frames = []

    try:
        while True:
            data = conn.recv(CHUNK_BYTES)
            if not data:
                break
            all_frames.append(data)
            buffer += data

            # Dès qu’on a 1 s, on transcrit
            while len(buffer) >= WINDOW_BYTES:
                segment = buffer[:WINDOW_BYTES]
                buffer = buffer[WINDOW_BYTES:]

                # Bytes→int16→float32[-1,1]
                audio48 = np.frombuffer(segment, dtype=np.int16).astype(np.float32) / 32768.0
                # Resample 48 kHz→16 kHz
                audio16 = librosa.resample(audio48, orig_sr=ORIG_SR, target_sr=TARGET_SR)
                # Transcription
                segments, _ = model.transcribe(audio16, beam_size=5, language="fr")
                text = " ".join(s.text.strip() for s in segments)
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] {text or '<silence>'}")

    except Exception as e:
        print("ERR :", e)
    finally:
        conn.close()
        sock.close()
        # Sauvegarde du WAV complet reçu
        wf = wave.open(OUTPUT_WAV, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPWIDTH)
        wf.setframerate(ORIG_SR)
        wf.writeframes(b"".join(all_frames))
        wf.close()
        print(f"🔒 Fin de la connexion, audio brut sauvegardé dans {OUTPUT_WAV}")

if __name__ == "__main__":
    main()
