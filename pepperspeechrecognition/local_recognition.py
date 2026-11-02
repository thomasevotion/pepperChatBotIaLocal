# -*- coding: utf-8 -*-

"""
Reconnaissance vocale locale avec Vosk (alternative à Google Speech)
"""

import os
import json
import wave
import numpy as np

class LocalRecognizer:
    def __init__(self):
        self.model_path = "vosk-model-fr-0.22"
        self.model = None
        self.recognizer = None
        self._load_model()
    
    def _load_model(self):
        """Charger le modèle Vosk"""
        try:
            import vosk
            if os.path.exists(self.model_path):
                self.model = vosk.Model(self.model_path)
                self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
                print("Modèle Vosk chargé avec succès")
            else:
                print("Modèle Vosk non trouvé, reconnaissance locale désactivée")
        except ImportError:
            print("Vosk non installé, reconnaissance locale désactivée")
        except Exception as e:
            print("Erreur lors du chargement de Vosk:", str(e))
    
    def recognize(self, audio_data, samplerate=16000):
        """Reconnaître la parole avec Vosk"""
        if not self.recognizer:
            return "Reconnaissance locale non disponible"
        
        try:
            # Convertir les données audio
            if isinstance(audio_data, np.ndarray):
                audio_data = audio_data.tobytes()
            
            # Reconnaissance
            if self.recognizer.AcceptWaveform(audio_data):
                result = json.loads(self.recognizer.Result())
                return result.get('text', '').strip()
            else:
                # Résultat partiel
                result = json.loads(self.recognizer.PartialResult())
                return result.get('partial', '').strip()
                
        except Exception as e:
            print("Erreur de reconnaissance Vosk:", str(e))
            return "Erreur de reconnaissance locale"

