#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Serveur STT Google avec OAuth
Remplace l'ancien système Google API qui ne marchait plus
"""

import os
import sys
import json
import base64
import socket
import threading
import tempfile
import wave
import numpy as np
from google.cloud import speech
from google.oauth2 import service_account

class GoogleSTTServer:
    def __init__(self, credentials_path="divine-data-472416-c3-6107ddcf03d9.json", port=8888):
        self.credentials_path = credentials_path
        self.port = port
        self.client = None
        self.server_socket = None
        self.running = False
        
    def load_credentials(self):
        """Charger les credentials Google OAuth"""
        try:
            if not os.path.exists(self.credentials_path):
                print(f"ERREUR: Fichier credentials non trouvé: {self.credentials_path}")
                return False
                
            print(f"Chargement des credentials Google: {self.credentials_path}")
            
            # Charger les credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            
            # Créer le client Speech
            self.client = speech.SpeechClient(credentials=credentials)
            print("Client Google Speech chargé avec succès!")
            return True
            
        except Exception as e:
            print(f"ERREUR lors du chargement des credentials: {e}")
            return False
    
    def recognize_audio(self, audio_data, sample_rate=16000):
        """Reconnaître l'audio avec Google Speech API v1"""
        try:
            if not self.client:
                return "Erreur: Client non chargé"
            
            print(f"Reçu {len(audio_data)} bytes d'audio")
            
            # Convertir les données audio si nécessaire
            if isinstance(audio_data, str):
                audio_data = base64.b64decode(audio_data)
            elif isinstance(audio_data, bytes):
                pass
            else:
                audio_data = audio_data.tobytes()
            
            print(f"Audio traité: {len(audio_data)} bytes")
            
            # Convertir en numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Vérifier si l'audio est assez fort
            if abs(audio_array.max()) < 1000:
                print("Audio trop faible")
                return ""
            
            # Configuration Google Speech API - Optimisée pour mots courts
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=48000,  # Audio de Pepper est à 48kHz !
                language_code='fr-FR',
                enable_automatic_punctuation=True,
                model='latest_short',  # Modèle optimisé pour mots courts
                # Paramètres plus permissifs
                max_alternatives=1,
                profanity_filter=False,
                enable_word_time_offsets=False,
                enable_word_confidence=False,
                # Essayer avec différents modèles
                use_enhanced=True
            )
            
            # Créer l'audio pour Google
            audio = speech.RecognitionAudio(content=audio_data)
            
            # Reconnaissance avec Google Speech API v1
            print("Envoi vers Google Speech API...")
            print(f"Audio envoyé: {len(audio_data)} bytes, sample_rate: {sample_rate}")
            print(f"Audio min/max: {audio_array.min()}/{audio_array.max()}")
            
            response = self.client.recognize(config=config, audio=audio)
            
            print(f"Réponse Google: {response}")
            
            # Extraire le résultat
            if response.results:
                print(f"Nombre de résultats: {len(response.results)}")
                for i, result in enumerate(response.results):
                    print(f"Résultat {i}: {result}")
                    if result.alternatives:
                        text = result.alternatives[0].transcript
                        confidence = result.alternatives[0].confidence
                        print(f"Résultat Google: '{text}' (confiance: {confidence:.2f})")
                        return text.strip()
            else:
                print("Aucun résultat dans la réponse Google")
            
            print("Aucun résultat Google")
            return ""
                    
        except Exception as e:
            print(f"Erreur de reconnaissance: {e}")
            return "Erreur de reconnaissance"
    
    def handle_client(self, client_socket, address):
        """Gérer un client connecté"""
        try:
            print(f"Client connecté: {address}")
            
            while True:
                # Recevoir la taille des données
                size_data = client_socket.recv(4)
                if not size_data:
                    break
                    
                data_size = int.from_bytes(size_data, 'big')
                
                # Recevoir les données audio
                audio_data = b''
                while len(audio_data) < data_size:
                    chunk = client_socket.recv(min(4096, data_size - len(audio_data)))
                    if not chunk:
                        break
                    audio_data += chunk
                
                if len(audio_data) != data_size:
                    print("Erreur: Taille des données incorrecte")
                    break
                
                # Reconnaissance
                result = self.recognize_audio(audio_data)
                
                # Envoyer le résultat
                result_bytes = result.encode('utf-8')
                result_size = len(result_bytes).to_bytes(4, 'big')
                print(f"Envoi de '{result}' -> {len(result_bytes)} bytes")
                client_socket.send(result_size + result_bytes)
                
        except Exception as e:
            print(f"Erreur avec le client {address}: {e}")
        finally:
            client_socket.close()
            print(f"Client déconnecté: {address}")
    
    def start_server(self):
        """Démarrer le serveur"""
        if not self.load_credentials():
            return False
            
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.running = True
            print(f"Serveur Google STT démarré sur le port {self.port}")
            print("En attente de connexions...")
            
            while self.running:
                try:
                    print("En attente de connexion...")
                    client_socket, address = self.server_socket.accept()
                    print(f"Client connecté: {address}")
                    # Traiter la connexion directement
                    try:
                        self.handle_client(client_socket, address)
                    except Exception as e:
                        print(f"Erreur dans handle_client: {e}")
                    finally:
                        client_socket.close()
                        print(f"Client déconnecté: {address}")
                except Exception as e:
                    if self.running:
                        print(f"Erreur d'acceptation: {e}")
                        
        except Exception as e:
            print(f"Erreur du serveur: {e}")
            return False
        finally:
            self.stop_server()
    
    def stop_server(self):
        """Arrêter le serveur"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("Serveur arrêté")

if __name__ == "__main__":
    server = GoogleSTTServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        server.stop_server()
    print("Serveur Google STT fermé.")
