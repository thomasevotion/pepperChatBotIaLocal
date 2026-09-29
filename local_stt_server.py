#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Serveur STT 100% local (faster-whisper), remplace google_stt_server.py.

Meme protocole que le serveur Google, donc pepperspeechrecognition/speechrecognition.py
n'a pas besoin de changer :
  - ecoute sur le port 8889
  - recoit l'audio brut Pepper (PCM int16 mono 48 kHz) en continu
  - fin de phrase = fermeture du socket par le client (SHUT_WR) ou 1.5 s sans donnees
  - renvoie "FINAL_JSON:{"transcript": ..., "languageCode": "fr-FR"}"

Whisper n'est pas un modele de streaming : l'audio est accumule puis transcrit d'un bloc en
fin de phrase. Sur GPU (large-v3-turbo) une phrase de quelques secondes se transcrit en
~0.3-0.6 s, soit du meme ordre que la latence reseau de Google.

Config (.env) :
  WHISPER_MODEL      (defaut large-v3-turbo ; "small" ou "medium" si pas de GPU)
  WHISPER_DEVICE     (defaut auto : cuda si dispo, sinon cpu)
  WHISPER_COMPUTE    (defaut float16 sur cuda, int8 sur cpu)
  WHISPER_LANGUAGES  (defaut fr,en,es : langues autorisees pour la detection automatique)
  WHISPER_DEFAULT_LANGUAGE (defaut fr)
  WHISPER_BEAM_SIZE  (defaut 1)
"""

import os
import sys
import json
import glob
import socket
import threading
import time

# numpy (MKL, ex: Anaconda) et ctranslate2 embarquent chacun libiomp5md.dll : sans ceci, le
# process s'arrete net au chargement de Whisper ("OMP: Error #15").
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

PORT = 8889
PEPPER_SAMPLE_RATE = 48000
WHISPER_SAMPLE_RATE = 16000
SILENCE_TIMEOUT = 1.5  # meme valeur que google_stt_server.py
MIN_AUDIO_SECONDS = 0.3

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whisper_models")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "")
DEFAULT_LANGUAGE = os.getenv("WHISPER_DEFAULT_LANGUAGE", "fr")
# 1 = decodage glouton, le plus rapide ; 5 = un peu plus precis sur audio bruite, ~2x plus lent.
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
ALLOWED_LANGUAGES = [l.strip() for l in os.getenv("WHISPER_LANGUAGES", "fr,en,es").split(",") if l.strip()]

# Code Whisper (ISO 639-1) -> code BCP-47 attendu par module_dialogue.py
# (_map_stt_language_to_naoqi se rabat de toute facon sur la langue primaire).
BCP47 = {
    "fr": "fr-FR", "en": "en-US", "es": "es-ES", "de": "de-DE", "it": "it-IT",
    "ja": "ja-JP", "zh": "zh-CN", "ar": "ar-SA", "cs": "cs-CZ", "da": "da-DK",
    "nl": "nl-NL", "fi": "fi-FI", "el": "el-GR", "ko": "ko-KR", "no": "nb-NO",
    "nn": "nb-NO", "pl": "pl-PL", "pt": "pt-PT", "ru": "ru-RU", "sv": "sv-SE",
    "tr": "tr-TR",
}

# Contexte donne a Whisper : vocabulaire propre au robot (equivalent des phrase hints Google).
INITIAL_PROMPT = os.getenv(
    "WHISPER_PROMPT",
    "Pepper, parle en anglais, parle en français, parle en espagnol, parle en allemand, "
    "parle en italien, parle en japonais, parle en chinois.",
)

# Hallucinations classiques de Whisper sur du silence / bruit (sous-titres de videos).
HALLUCINATIONS = [
    "sous-titres réalisés par", "sous-titrage", "amara.org", "merci d'avoir regardé",
    "thanks for watching", "thank you for watching", "abonnez-vous", "subscribe",
    "sous-titres fait par",
]


def _add_cuda_dll_dirs():
    """Sous Windows, ctranslate2 a besoin de cuBLAS/cuDNN : on ajoute au chemin DLL ceux
    installes par pip (nvidia-cublas-cu12 / nvidia-cudnn-cu12), sans installer le CUDA Toolkit."""
    if os.name != "nt":
        return
    for base in sys.path:
        for d in glob.glob(os.path.join(base, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass


def _resample_48k_to_16k(pcm48):
    """Filtre passe-bas (sinc fenetre, coupure 7.5 kHz) puis decimation par 3."""
    x = pcm48.astype(np.float32) / 32768.0
    taps = 63
    n = np.arange(taps) - (taps - 1) / 2.0
    cutoff = 7500.0 / PEPPER_SAMPLE_RATE
    h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hamming(taps)
    h /= h.sum()
    y = np.convolve(x, h, mode="same")
    return y[::3].astype(np.float32)


class LocalSTTServer:
    def __init__(self, port=PORT):
        self.port = port
        self.model = None
        self.model_lock = threading.Lock()
        self.server_socket = None
        self.running = False

    def load_model(self):
        _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel

        attempts = []
        if WHISPER_DEVICE in ("auto", "cuda"):
            attempts.append(("cuda", WHISPER_COMPUTE or "float16"))
        if WHISPER_DEVICE in ("auto", "cpu"):
            attempts.append(("cpu", WHISPER_COMPUTE or "int8"))

        for device, compute in attempts:
            try:
                print(f"Chargement Whisper '{WHISPER_MODEL}' sur {device} ({compute})...")
                start = time.time()
                model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute,
                                     download_root=MODEL_DIR)
                # Warmup : force le chargement des DLL CUDA maintenant plutot qu'a la 1ere phrase.
                segments, _ = model.transcribe(np.zeros(WHISPER_SAMPLE_RATE, dtype=np.float32), language="fr")
                list(segments)  # transcribe() est paresseux
                self.model = model
                print(f"Whisper pret sur {device} en {time.time() - start:.1f}s")
                return True
            except Exception as e:
                print(f"Echec Whisper sur {device}: {e}")
        return False

    def _pick_language(self, audio):
        """Detection de langue restreinte a ALLOWED_LANGUAGES (evite qu'une phrase courte en
        francais soit prise pour du portugais ou du gallois)."""
        if len(ALLOWED_LANGUAGES) == 1:
            return ALLOWED_LANGUAGES[0]
        try:
            _, _, probs = self.model.detect_language(audio)
            best = max(
                ((lang, p) for lang, p in probs if lang in ALLOWED_LANGUAGES),
                key=lambda lp: lp[1], default=(DEFAULT_LANGUAGE, 0.0),
            )
            return best[0]
        except Exception as e:
            print(f"Detection de langue impossible ({e}), fallback {DEFAULT_LANGUAGE}")
            return DEFAULT_LANGUAGE

    def transcribe(self, pcm_bytes):
        pcm_bytes = pcm_bytes[: len(pcm_bytes) // 2 * 2]
        pcm48 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(pcm48) < MIN_AUDIO_SECONDS * PEPPER_SAMPLE_RATE:
            return None, None
        audio = _resample_48k_to_16k(pcm48)

        with self.model_lock:
            start = time.time()
            language = self._pick_language(audio)
            segments, _ = self.model.transcribe(
                audio,
                language=language,
                beam_size=WHISPER_BEAM_SIZE,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                condition_on_previous_text=False,
                initial_prompt=INITIAL_PROMPT,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            print(f"Transcription {len(audio) / WHISPER_SAMPLE_RATE:.1f}s audio "
                  f"en {time.time() - start:.2f}s [{language}]")

        low = text.lower()
        if not text or any(h in low for h in HALLUCINATIONS):
            if text:
                print(f"Hallucination Whisper ignoree: {text}")
            return None, None
        return text, BCP47.get(language, language)

    def handle_client(self, client_socket, address):
        try:
            print(f"Client connecté: {address}")
            client_socket.settimeout(SILENCE_TIMEOUT)
            chunks = []
            while True:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        print("Fin du flux audio (socket fermé par le client).")
                        break
                    chunks.append(data)
                except socket.timeout:
                    print(f"Silence détecté (timeout socket {SILENCE_TIMEOUT}s), fin de la phrase.")
                    break

            transcript, language_code = self.transcribe(b"".join(chunks))
            if transcript:
                print(f"FINAL [{language_code}]: {transcript}")
                msg = "FINAL_JSON:" + json.dumps({
                    "transcript": transcript,
                    "languageCode": language_code,
                }, ensure_ascii=False)
                client_socket.sendall(msg.encode("utf-8"))
            else:
                print("Aucun transcript exploitable, pas d'evenement envoye au dialogue.")
        except Exception as e:
            print(f"Erreur dans handle_client: {e}")
        finally:
            try:
                client_socket.close()
            except Exception:
                pass
            print(f"Client déconnecté: {address}")

    def start_server(self):
        print("Initialisation du serveur STT local (Whisper)...")
        if not self.load_model():
            print("ERREUR : impossible de charger Whisper.")
            return False

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)  # pour permettre le CTRL+C
        self.running = True
        print(f"Serveur STT local prêt sur le port {self.port}")
        print(f"Langues autorisées : {', '.join(ALLOWED_LANGUAGES)}")
        try:
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                except socket.timeout:
                    continue
                t = threading.Thread(target=self.handle_client, args=(client_socket, address))
                t.daemon = True
                t.start()
        finally:
            self.stop_server()

    def stop_server(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("Serveur arrêté")


if __name__ == "__main__":
    server = LocalSTTServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        server.stop_server()
    print("Serveur STT local fermé.")
