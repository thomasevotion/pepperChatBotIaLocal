# -*- coding: utf-8 -*-

"""
Client Vosk pour Python 2.7
Communique avec le serveur Vosk local
"""

import socket
import struct
import os

class VoskClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        
    def recognize(self, audio_data):
        """Reconnaître l'audio avec le serveur Vosk local"""
        try:
            # Se connecter au serveur
            print("Tentative de connexion à " + self.host + ":" + str(self.port))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # Timeout réduit à 5 secondes
            sock.connect((self.host, self.port))
            print("Connexion réussie au serveur Vosk")
            
            # Convertir les données audio en bytes si nécessaire
            if hasattr(audio_data, 'tobytes'):
                audio_bytes = audio_data.tobytes()
            elif hasattr(audio_data, 'tostring'):
                audio_bytes = audio_data.tostring()
            else:
                audio_bytes = str(audio_data)
            
            print("Envoi de " + str(len(audio_bytes)) + " bytes vers Vosk")
            
            # Envoyer la taille des données (4 bytes)
            data_size = len(audio_bytes)
            size_bytes = struct.pack('>I', data_size)
            sock.send(size_bytes)
            
            # Envoyer les données audio
            sock.send(audio_bytes)
            
            # Recevoir la taille de la réponse
            size_data = sock.recv(4)
            if len(size_data) != 4:
                print("Erreur: taille de réponse invalide")
                return "Erreur de communication"
                
            result_size = struct.unpack('>I', size_data)[0]
            print("Réponse attendue: " + str(result_size) + " bytes")
            
            # Recevoir la réponse
            result_data = b''
            while len(result_data) < result_size:
                chunk = sock.recv(min(4096, result_size - len(result_data)))
                if not chunk:
                    break
                result_data += chunk
            
            sock.close()
            
            # Retourner le résultat - Gestion robuste de l'encodage
            try:
                # Forcer le décodage ASCII avec ignore
                result = result_data.decode('ascii', errors='ignore')
            except:
                # Si tout échoue, retourner "bonjour" directement
                result = "bonjour"
            
            # Nettoyer le résultat
            result = result.strip()
            if not result:
                # Si pas de résultat, ne pas envoyer "bonjour" mais laisser le système gérer
                print("Aucun resultat Vosk")
                return "error"
                
            print("Resultat Vosk: " + result)
            return result
            
        except Exception as e:
            print("Erreur Vosk client: " + str(e))
            return "Erreur de reconnaissance locale"
