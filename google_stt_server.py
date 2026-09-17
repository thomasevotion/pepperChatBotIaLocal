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

LANGUAGE_PHRASE_HINTS = [
    "parle en anglais", "parle-moi en anglais", "anglais",
    "parle en français", "parle-moi en français", "français",
    "parle en japonais", "parle-moi en japonais", "japonais",
    "parle en allemand", "parle-moi en allemand", "allemand",
    "parle en espagnol", "parle-moi en espagnol", "espagnol",
    "parle en italien", "parle-moi en italien", "italien",
    "parle en arabe", "parle-moi en arabe", "arabe",
    "parle en chinois", "parle-moi en chinois", "chinois",
    "parle en mandarin", "parle-moi en mandarin", "mandarin",
    "parle en taïwanais", "parle-moi en taïwanais", "taïwanais",
    "parle en tchèque", "parle-moi en tchèque", "tchèque",
    "parle en danois", "parle-moi en danois", "danois",
    "parle en néerlandais", "parle-moi en néerlandais", "néerlandais",
    "parle en finnois", "parle-moi en finnois", "finnois",
    "parle en grec", "parle-moi en grec", "grec",
    "parle en coréen", "parle-moi en coréen", "coréen",
    "parle en norvégien", "parle-moi en norvégien", "norvégien",
    "parle en polonais", "parle-moi en polonais", "polonais",
    "parle en portugais", "parle-moi en portugais", "portugais",
    "parle en brésilien", "parle-moi en brésilien", "brésilien",
    "parle en russe", "parle-moi en russe", "russe",
    "parle en suédois", "parle-moi en suédois", "suédois",
    "parle en turc", "parle-moi en turc", "turc",
]

class GoogleSTTServer:
    def __init__(self, api_key="AIzaSyAC10StUbYwR_xy1v4nPAxyGjx0D1XftuE", port=8889):
        self.api_key = api_key
        self.port = port
        self.client = None
        self.server_socket = None
        self.running = False
        
    def load_credentials(self):
        """Charger les credentials Google OAuth via API Key"""
        try:
            print(f"Chargement du client Google Speech avec API Key...")
            
            # Utilisation de l'API Key via client_options
            from google.api_core.client_options import ClientOptions
            options = ClientOptions(api_key=self.api_key)
            
            # Créer le client Speech sans credentials explicites mais avec l'API key
            self.client = speech.SpeechClient(client_options=options)
            print("Client Google Speech chargé avec succès (API Key)!")
            return True
            
        except Exception as e:
            print(f"ERREUR lors du chargement du client: {e}")
            return False
    
    def request_generator(self, clientsocket):
        # Timeout de silence avant de considerer la phrase terminee. Etait a 3.0s (temps de
        # respiration genereux mais ajoute jusqu'a 3s de latence fixe avant meme d'appeler le LLM).
        # 1.5s reste confortable pour une pause naturelle tout en coupant ce delai de moitie.
        # Remonter vers 3.0 si des utilisateurs se font couper la parole en testant.
        clientsocket.settimeout(1.5)
        print("Debut du streaming audio...")
        try:
            while True:
                try:
                    data = clientsocket.recv(4096)
                    if not data:
                        print("Fin du flux audio (socket fermé par le client).")
                        break
                    yield speech.StreamingRecognizeRequest(audio_content=data)
                except socket.timeout:
                    print("Silence détecté (timeout socket 4s), fin de la phrase.")
                    break 
        except Exception as e:
            print(f"Erreur lecture socket: {e}")
            
    def handle_client(self, client_socket, address):
        """Gérer un client en mode Streaming complet"""
        try:
            print(f"Client connecté: {address}")
            sent_final = False
            
            if not self.client:
                print("Erreur: Client Google non initialisé")
                return

            # Configuration Google Speech API Streaming
            # Pepper est en 48kHz
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=48000, 
                language_code='fr-FR',
                alternative_language_codes=['en-US', 'es-ES'],
                enable_automatic_punctuation=True,
                model='latest_short',
                use_enhanced=True,
                speech_contexts=[
                    speech.SpeechContext(
                        phrases=LANGUAGE_PHRASE_HINTS,
                        boost=18.0
                    )
                ]
            )
            
            # single_utterance=False: la fin de la phrase est décidée uniquement par la fermeture
            # du socket côté client (cf. request_generator). Avec single_utterance=True, Google
            # gère son propre endpointing en parallèle de celui du client, et les deux détections
            # entrent en concurrence: si le client ferme le socket juste avant que l'endpointer de
            # Google n'ait fini, Google renvoie un FINAL avec un transcript tronqué/vide au lieu
            # d'une vraie erreur.
            streaming_config = speech.StreamingRecognitionConfig(
                config=config,
                interim_results=True,
                single_utterance=False
            )

            # Lancer la reconnaissance
            # Cette fonction bloque et consomme le générateur
            print("Lancement de streaming_recognize...")
            requests = self.request_generator(client_socket)
            
            # On itère sur les réponses au fur et à mesure
            responses = self.client.streaming_recognize(config=streaming_config, requests=requests)
            
            last_partial = None
            last_language_code = 'fr-FR'

            for response in responses:
                if not response.results:
                    continue
                
                result = response.results[0]
                if not result.alternatives:
                    continue
                    
                transcript = result.alternatives[0].transcript
                language_code = getattr(result, "language_code", None) or 'fr-FR'
                last_language_code = language_code
                
                # Gestion des résultats
                if result.is_final and transcript.strip():
                    print(f"FINAL [{language_code}]: {transcript}")
                    msg = "FINAL_JSON:" + json.dumps({
                        "transcript": transcript,
                        "languageCode": language_code
                    }, ensure_ascii=False)
                    # Envoyer la taille (4 bytes) puis le message
                    # msg_bytes = msg.encode('utf-8')
                    # client_socket.send(len(msg_bytes).to_bytes(4, 'big') + msg_bytes)

                    # Simplification: Protocole texte simple avec séparateur, car Python 2.7 struct est chiant
                    # On envoie juste le texte brut utf-8. Le client lira tout.
                    client_socket.send(msg.encode('utf-8'))
                    sent_final = True

                elif result.is_final:
                    # Final vide/tronqué (race entre l'endpointing de Google et la fermeture du
                    # socket côté client) : on l'ignore et on laisse le fallback last_partial
                    # prendre le relais en fin de fonction.
                    print(f"FINAL [{language_code}] vide, ignoré (fallback sur last_partial)")

                else:
                    # Resultat partiel (interim)
                    last_partial = transcript
                    print(f"PARTIAL: {transcript}")
                    # On pourrait renvoyer les partiels au robot pour affichage tablette
                    # msg = f"PARTIAL:{transcript}"
                    # client_socket.send(msg.encode('utf-8'))

            if not sent_final and last_partial:
                print(f"FINAL_FALLBACK [{last_language_code}]: {last_partial}")
                msg = "FINAL_JSON:" + json.dumps({
                    "transcript": last_partial,
                    "languageCode": last_language_code
                }, ensure_ascii=False)
                try:
                    client_socket.send(msg.encode('utf-8'))
                except Exception as e_send:
                    print(f"Erreur envoi FINAL_FALLBACK: {e_send}")
            elif not sent_final:
                print("Aucun transcript exploitable, pas d'evenement envoye au dialogue.")
            
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
                    self.server_socket.settimeout(1.0) # Timeout pour permettre le CTRL+C
                    try:
                        client_socket, address = self.server_socket.accept()
                        # Thread pour chaque client pour ne pas bloquer
                        client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
                        client_thread.daemon = True
                        client_thread.start()
                    except socket.timeout:
                        continue
                        
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
