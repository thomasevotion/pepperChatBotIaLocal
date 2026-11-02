# -*- coding: utf-8 -*-

###########################################################
# This is the client interfacve for the GPT-3 OpenAI chatbot.  
#
# Syntax:
#    python oaiclient.py (runs under both python2 and python3)
#
# Author: Erik Billing, University of Skovde
# Created: June 2022. 
# License: Copyright reserved to the author. 
###########################################################
"""Zmq cloent interface for the OpenAI chatbot"""

import zmq
import sys, os, json
from datetime import datetime
from oairesponse import OaiResponse

import dotenv
dotenv.load_dotenv()

if sys.version_info[0] > 2:
    raw_input = input

class OaiClient:

    def __init__(self, name='OaiClient', user=None):
        self.name = name
        self.user = user
        self.context = zmq.Context()
        # emotion_tag choisi par le LLM pour le tour de dialogue en cours (voir respond_stream) :
        # deja connu des le premier chunk recu, module_dialogue.py peut le lire immediatement
        # pour lancer l'animation en parallele du TTS.
        self.last_emotion_tag = None

        self.log = None
        if user:
            logdir = os.getenv('LOGDIR')
            if not os.path.isdir(logdir): os.mkdir(logdir)
            log = 'dialogue.%s.%s.log'%(user,datetime.now().strftime("%Y-%m-%d_%H%M%S"))
            self.log = open(os.path.join(logdir,log),'a')
            
        sys.stdout.write("Connecting to OpenAI chatbot server... ")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(os.getenv('CHATBOT_SERVER_ADDRESS'))
        handshake = self.send({'handshake':self.name})
        print("Done." if handshake.get('handshake') == 'ok' else "Unexpected response '%s'"%handshake)

    def respond(self,s):
        return OaiResponse(self.send({'input':s})).getText()

<<<<<<< HEAD
    def send(self,o):
=======
        image_data (optionnel) : dict avec les cles 'raw', 'width', 'height'
                                 (sortie de capture_camera_image dans module_dialogue.py)
        """
        msg = {'input': s}
        if image_data:
            msg['image_data'] = image_data
        return OaiResponse(self.send(msg)).getText()

    def respond_stream(self, s, image_data=None):
        """
        Envoie un message en mode streaming. Retourne un generateur de chunks texte.

        image_data (optionnel) : idem que respond()
        """
        msg = {'input': s, 'stream': True}
        if image_data:
            msg['image_data'] = image_data

        # Demarrer le stream
        self.send(msg)

        while True:
            r = self.send({'next_chunk': True})
            if 'emotion_tag' in r:
                self.last_emotion_tag = r['emotion_tag']
            if r.get('stream_finished'):
                break
            if r.get('error'):
                print("Stream error:", r['error'])
                break

            chunk = r.get('chunk', '')
            if chunk:
                yield chunk

    def send(self, o):
>>>>>>> Groupama
        o['time'] = datetime.now().isoformat()
        if self.log: 
            json.dump({'sending':o},self.log)
            self.log.write(',\n')
        self.socket.send_json(o)
        r = self.socket.recv_json()
        if self.log: 
            json.dump({'receiving':r},self.log)
            self.log.write(',\n')
        return r 

    def reset(self):
        r = self.send({'reset':True,'user':self.user})
        if r.get('reset') == 'ok':
            print('Dialogue history reset')
        else:
            print('Error resetting dialoge history')

if __name__ == '__main__':
    client = OaiClient(('Your name is Pepper.','We are currently at the Interaction Lab in Skovde, Sweden.','You are a robot.'))
    while True:
        s = raw_input('> ')
        if s:
            print('Response: ' + client.respond(s).getText())
        else:
            break