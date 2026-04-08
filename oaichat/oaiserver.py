# -*- coding: utf-8 -*-

###########################################################
# Serveur ZMQ pour le chatbot Gemini (remplace OpenAI).
# Gere les requetes texte et multimodales (texte + image).
#
# Author: adapte depuis Erik Billing, University of Skovde
###########################################################
"""Zmq server interface for the Gemini chatbot"""

import zmq, os
import datetime
from threading import Thread
from oaichat.openaichat import OaiChat


class OaiServer(OaiChat):

    def __init__(self, user, prompt=None):
        super().__init__(user, prompt)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind('tcp://*:' + os.getenv('CHATBOT_SERVER_ADDRESS').split(':')[-1])
        self.thread = None
        self.stream_generator = None
        self.full_stream_response = ""
        self.current_stream_input = ""  # Pour l'historique apres streaming

    def start(self):
        self.thread = Thread(target=self._run)
        self.thread.start()

    def _run(self):
        print('Starting Gemini chat server...')
        try:
            while self.thread:
                response = {}
                print('Listening for msg...')
                i = self.listen()
                # On affiche le message recu sans l'image (trop long)
                debug_i = {k: v for k, v in i.items() if k != 'image_data'}
                print('Input received:', debug_i)

                if 'handshake' in i:
                    print('New client connected:', i['handshake'])
                    response['handshake'] = 'ok'

                if 'reset' in i and i['reset']:
                    print('Resetting history.')
                    self.reset(i['user'])
                    response['reset'] = 'ok'

                if 'history' in i:
                    print('Extending history:')
                    for row in i['history']:
                        print('\t' + row.strip())
                        self.history.append(row.strip())
                    response['history'] = 'ok'

                if 'input' in i:
                    # Recuperer l'image si presente (envoyee par module_dialogue.py)
                    image_data = i.get('image_data', None)

                    if i.get('stream'):
                        print('Starting stream for input:', i['input'])
                        # Sauvegarder l'input pour l'historique apres le stream
                        self.current_stream_input = i['input']
                        try:
                            self.stream_generator = self.respond(
                                i['input'], image_data=image_data, stream=True
                            )
                            self.full_stream_response = ""
                            response['stream'] = 'started'
                        except Exception as e_stream_start:
                            print("Erreur demarrage stream Gemini:", e_stream_start)
                            response['error'] = str(e_stream_start)
                            self.stream_generator = None
                    else:
                        try:
                            r = self.respond(i['input'], image_data=image_data)
                            for k, v in r.json.items():
                                response[k] = v
                        except Exception as e_respond:
                            # 503 UNAVAILABLE, 429 quota, etc. → ne pas planter le serveur
                            print("Erreur respond Gemini (non-stream):", e_respond)
                            response['error'] = str(e_respond)
                            response['response'] = "Desole, Gemini est temporairement indisponible."

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

                response['time'] = datetime.datetime.now().isoformat()
                print('Sending response:', {k: v for k, v in response.items() if k not in ('chunk',)})
                self.send(response)

        except zmq.error.ContextTerminated:
            pass

    def stop(self):
        self.thread = None
        self.context.destroy()

    def listen(self):
        return self.socket.recv_json()

    def send(self, s):
        return self.socket.send_json(s)


def main():
    server = OaiServer('pepper')
    server.start()
    try:
        while True:
            i = input('Enter q to quit. > ')
            if i == 'q':
                break
    finally:
        server.stop()
