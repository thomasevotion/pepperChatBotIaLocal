#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Serveur Vosk local pour la reconnaissance vocale
Utilise le modèle vosk-model-fr-0.22 déjà téléchargé
"""

import os
import sys
import json
import base64
import socket
import threading
import vosk
import wave
import io
import numpy as np
import tempfile

class VoskServer:
    def __init__(self, model_path="vosk-model-fr-0.22", port=8888):
        self.model_path = model_path
        self.port = port
        self.model = None
        self.recognizer = None
        self.server_socket = None
        self.running = False
        
    def load_model(self):
        """Charger le modèle Vosk"""
        try:
            if not os.path.exists(self.model_path):
                print(f"ERREUR: Modèle Vosk non trouvé: {self.model_path}")
                return False
                
            print(f"Chargement du modèle Vosk: {self.model_path}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
            print("Modèle Vosk chargé avec succès!")
            return True
            
        except Exception as e:
            print(f"ERREUR lors du chargement du modèle: {e}")
            return False
    
    def recognize_audio(self, audio_data, sample_rate=16000):
        """STT LOCAL RAPIDE - Remplace Google"""
        try:
            if not self.recognizer:
                return "Erreur: Modèle non chargé"
            
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
            
            # Filtre de bruit simple (moyenne mobile)
            if len(audio_array) > 100:
                # Appliquer un filtre de bruit basique
                audio_array = np.convolve(audio_array, np.ones(5)/5, mode='same')
            
            # Vérifier si l'audio est assez fort (seuil plus bas pour fond bruyant)
            if abs(audio_array.max()) < 500:  # Seuil plus bas
                print("Audio trop faible")
                return ""
            
            # STT LOCAL SIMPLE - Détection de parole
            print("=== STT LOCAL ===")
            
            # Analyser l'audio pour détecter des mots
            # Calculer l'énergie audio
            audio_energy = np.sum(audio_array ** 2) / len(audio_array)
            print(f"Énergie audio: {audio_energy}")
            
            # Si l'énergie est élevée, c'est de la parole (seuil adaptatif)
            # Seuil plus bas pour fond bruyant
            seuil_energie = 500 if audio_energy < 2000 else 1000
            if audio_energy > seuil_energie:
                print(f"Parole détectée! (énergie: {audio_energy}, seuil: {seuil_energie})")
                
                # VRAIE RECONNAISSANCE VOCALE
                print("Parole détectée - reconnaissance en cours...")
                
                # Utiliser Vosk pour la vraie reconnaissance
                try:
                    # Réinitialiser le recognizer
                    self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
                    
                    # Envoyer tout l'audio d'un coup à Vosk
                    if self.recognizer.AcceptWaveform(audio_array.tobytes()):
                        result = self.recognizer.Result()
                        print(f"Résultat Vosk: {result}")
                        try:
                            result_json = json.loads(result)
                            text = result_json.get('text', '').strip()
                            if text:
                                print(f"TEXTE RECONNU: '{text}'")
                                return text
                        except:
                            pass
                    else:
                        # Essayer PartialResult
                        partial = self.recognizer.PartialResult()
                        print(f"Résultat partiel: {partial}")
                        try:
                            partial_json = json.loads(partial)
                            text = partial_json.get('partial', '').strip()
                            if text:
                                print(f"TEXTE PARTIEL: '{text}'")
                                return text
                        except:
                            pass
                    
                    # Essayer FinalResult
                    final = self.recognizer.FinalResult()
                    print(f"Résultat final: {final}")
                    try:
                        final_json = json.loads(final)
                        text = final_json.get('text', '').strip()
                        if text:
                            print(f"TEXTE FINAL: '{text}'")
                            return text
                    except:
                        pass
                    
                    # Si Vosk ne trouve rien, retourner "error" comme avant
                    print("Aucun texte reconnu par Vosk")
                    return "error"
                    
                except Exception as e:
                    print(f"Erreur Vosk: {e}")
                    return "error"
            else:
                print("Pas de parole détectée")
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
                
                # Envoyer le résultat en ASCII pur pour Python 2.7
                result_ascii = result.encode('ascii', errors='ignore')
                result_size = len(result_ascii).to_bytes(4, 'big')
                print(f"DEBUG SERVEUR: Envoi de '{result}' -> ASCII: {repr(result_ascii)}")
                print(f"DEBUG SERVEUR: Taille: {len(result_ascii)} bytes")
                client_socket.send(result_size + result_ascii)
                
        except Exception as e:
            print(f"Erreur avec le client {address}: {e}")
        finally:
            client_socket.close()
            print(f"Client déconnecté: {address}")
    
    def start_server(self):
        """Démarrer le serveur"""
        if not self.load_model():
            return False
            
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.running = True
            print(f"Serveur Vosk démarré sur le port {self.port}")
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

def main():
    server = VoskServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        server.stop_server()

if __name__ == "__main__":
    main()
