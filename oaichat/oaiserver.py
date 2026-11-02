# -*- coding: utf-8 -*-

###########################################################
# This is the server interface for the GPT-3 OpenAI chatbot.  
#
# Syntax:
#    python3 oaiserver.py
#
# Author: Erik Billing, University of Skovde
# Created: June 2022. 
# License: Copyright reserved to the author. 
###########################################################
"""Zmq server interface for the OpenAI chatbot"""

import zmq, os
import datetime
from threading import Thread
from oaichat.openaichat import OaiChat

class OaiServer(OaiChat):

    def __init__(self, user, prompt=None):
        super().__init__(user, prompt)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind('tcp://*:'+os.getenv('CHATBOT_SERVER_ADDRESS').split(':')[-1])
        self.thread = None

    def start(self):
        self.thread = Thread(target=self._run)
        self.thread.start()

    def _run(self): 
        print('Starting OpenAI chat server...')
        try:
            while self.thread:
                response = {}
                print('Listening for msg...')
                i = self.listen()
                print('Input received:',i)
                if 'handshake' in i: 
                    print('New client connected:',i['handshake'])
                    response['handshake'] = 'ok'
                if 'reset' in i and i['reset']:
                    print('Resetting history.')
                    self.reset(i['user'])
                    response['reset']='ok'
                if 'history' in i:
                    print('Extending history:')
                    for row in i['history']: 
                        print('\t'+row.strip())
                        self.history.append(row.strip())
                    response['history']='ok'
                if 'input' in i:
                    # Recuperer l'image si presente (envoyee par module_dialogue.py)
                    image_data = i.get('image_data', None)

                    if i.get('stream'):
                        print('Starting stream for input:', i['input'])
                        # Sauvegarder l'input pour l'historique apres le stream
                        self.current_stream_input = i['input']
                        try:
                            # respond_stream() (pas respond()) : tour de dialogue principal.
                            # Generateur "paresseux" : rien ne s'execute avant le premier
                            # next_chunk (voir plus bas), qui declenche la classification de
                            # l'emotion_tag PUIS ouvre le vrai stream reseau Gemini pour "speech".
                            self.stream_generator = self.respond_stream(
                                i['input'], image_data=image_data
                            )
                            self.full_stream_response = ""
                            response['stream'] = 'started'
                        except Exception as e_stream_start:
                            print("Erreur demarrage stream Gemini:", e_stream_start)
                            response['error'] = str(e_stream_start)
                            self.stream_generator = None
                    else:
                        try:
                            # respond() (pas respond_stream()) : appel non-streaming classique
                            # (accueil, commentaire environnement...), retourne un OaiResponse
                            # avec .json, pas un generateur.
                            r = self.respond(i['input'], image_data=image_data)
                            for k, v in r.json.items():
                                response[k] = v
                        except Exception as e_respond:
                            # 503 UNAVAILABLE, 429 quota, etc. → ne pas planter le serveur
                            print("Erreur respond Gemini (non-stream):", e_respond)
                            response['error'] = str(e_respond)
                            response['response'] = "Désole, Gemini est temporairement indisponible."

                elif 'next_chunk' in i:
                    if self.stream_generator:
                        try:
                            chunk = next(self.stream_generator)
                            # Format Gemini : chunk.text (et non chunk.choices[0].delta.content)
                            try:
                                content = chunk.text if chunk.text else ""
                            except (AttributeError, ValueError):
                                content = ""

                            if content:
                                response['chunk'] = content
                                self.full_stream_response += content
                            else:
                                response['chunk'] = ""

                        except StopIteration:
                            response['stream_finished'] = True
                            # Mettre a jour l'historique avec l'echange complet
                            self.add_to_history(
                                self.current_stream_input,
                                self.full_stream_response
                            )
                            self.stream_generator = None

                        except Exception as e:
                            print("Stream error:", e)
                            response['error'] = str(e)
                            self.stream_generator = None
                    else:
                        response['error'] = "No active stream"
                        response['stream_finished'] = True

                # emotion_tag choisi par le LLM (voir OaiChat.respond_stream) : deja connu
                # avant meme le premier chunk, donc toujours present des la 1ere reponse
                # au client pour qu'il puisse lancer l'animation en parallele du TTS.
                response['emotion_tag'] = getattr(self, 'last_emotion_tag', None)

                response['time'] = datetime.datetime.now().isoformat()
                print('Sending response:',response)        
                self.send(response)
        except zmq.error.ContextTerminated as e:
            pass
                
    def stop(self):
        #self.socket.close()
        self.thread = None
        #self.log.close()
        self.context.destroy()

    def listen(self):
        #  Wait for next request from client
        return self.socket.recv_json()

    def send(self,s):
        return self.socket.send_json(s)

def main():
    server = OaiServer()
    server.start()
    try: 
        while True:
            i = input('Enter q to quit. > ')
            if i == 'q': break
    finally:
        server.stop()
