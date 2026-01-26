#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Serveur STT Google avec OAuth
Mode: Streaming Continu
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
    def __init__(self, credentials_path="divine-data-472416-c3-6107ddcf03d9.json", port=8889):
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
    
    def request_generator(self, client_socket):
        """Générateur qui lit le socket et produit des chunks pour Google"""
        client_socket.settimeout(None) # Mode bloquant
        print("Debut du streaming audio...")
        
        # Buffer pour accumuler un peu de données si nécessaire
        try:
            while True:
                # Lecture bloquante du socket
                data = client_socket.recv(4096)
                if not data:
                    print("Fin du flux audio (socket fermé par le client).")
                    break
                
                # On envoie direct à Google
                yield speech.StreamingRecognizeRequest(audio_content=data)
        except Exception as e:
            print(f"Erreur lecture socket: {e}")
            
    def handle_client(self, client_socket, address):
        """Gérer un client en mode Streaming complet"""
        try:
            print(f"Client connecté: {address}")
            
            if not self.client:
                print("Erreur: Client Google non initialisé")
                return

            # Configuration Google Speech API Streaming
            # Pepper est en 48kHz
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=48000, 
                language_code='fr-FR',
                enable_automatic_punctuation=True,
                model='latest_short',
                use_enhanced=True
            )
            
            # config single_utterance=True permet de dire à Google de s'arrêter dès qu'une phrase est finie
            # Mais ici on veut contrôler manuellement via le client
            streaming_config = speech.StreamingRecognitionConfig(
                config=config,
                interim_results=True # Important pour le feedback et la rapidité
            )

            # Lancer la reconnaissance
            # Cette fonction bloque et consomme le générateur
            print("Lancement de streaming_recognize...")
            requests = self.request_generator(client_socket)
            
            # On itère sur les réponses au fur et à mesure
            responses = self.client.streaming_recognize(config=streaming_config, requests=requests)
            
            for response in responses:
                if not response.results:
                    continue
                
                result = response.results[0]
                if not result.alternatives:
                    continue
                    
                transcript = result.alternatives[0].transcript
                
                # Gestion des résultats
                if result.is_final:
                    print(f"FINAL: {transcript}")
                    msg = f"FINAL:{transcript}"
                    # Envoyer la taille (4 bytes) puis le message
                    # msg_bytes = msg.encode('utf-8')
                    # client_socket.send(len(msg_bytes).to_bytes(4, 'big') + msg_bytes)
                    
                    # Simplification: Protocole texte simple avec séparateur, car Python 2.7 struct est chiant
                    # On envoie juste le texte brut utf-8. Le client lira tout.
                    client_socket.send(msg.encode('utf-8'))
                    
                else:
                    # Resultat partiel (interim)
                    print(f"PARTIAL: {transcript}")
                    # On pourrait renvoyer les partiels au robot pour affichage tablette
                    # msg = f"PARTIAL:{transcript}"
                    # client_socket.send(msg.encode('utf-8'))
            
            print("Fin de la session de reconnaissance.")
                
        except Exception as e:
            print(f"Erreur dans handle_client: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            print(f"Client déconnecté: {address}")
    
    def start_server(self):
        """Démarrer le serveur"""
        print("Initialisation du serveur STT (Mode Streaming)...")
        
        if not self.load_credentials():
            return False
            
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.running = True
            print(f"Serveur Google STT prêt sur le port {self.port}")
            print("En attente de connexions...")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    # Thread pour chaque client pour ne pas bloquer
                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
                    client_thread.daemon = True
                    client_thread.start()
                    
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
