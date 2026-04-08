# -*- coding: utf-8 -*-

###########################################################
# Client ZMQ pour le chatbot Gemini (compatible Python 2 et 3).
# Supporte l'envoi optionnel d'une image (camera Pepper).
#
# Author: adapte depuis Erik Billing, University of Skovde
###########################################################
"""Zmq client interface for the Gemini chatbot"""

import zmq
import sys, os, json
from datetime import datetime
from oairesponse import OaiResponse

import dotenv
dotenv.load_dotenv()

# Charger les variables d'environnement depuis config.env
try:
    with open('config.env', 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
except:
    pass

if sys.version_info[0] > 2:
    raw_input = input


class OaiClient:

    def __init__(self, name='OaiClient', user=None):
        self.name = name
        self.user = user
        self.context = zmq.Context()

        self.log = None
        if user:
            logdir = os.getenv('LOGDIR')
            if logdir and not os.path.isdir(logdir):
                os.mkdir(logdir)
            if logdir:
                log = 'dialogue.%s.%s.log' % (user, datetime.now().strftime("%Y-%m-%d_%H%M%S"))
                self.log = open(os.path.join(logdir, log), 'a')

        sys.stdout.write("Connecting to Gemini chatbot server... ")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(os.getenv('CHATBOT_SERVER_ADDRESS'))
        handshake = self.send({'handshake': self.name})
        print("Done." if handshake.get('handshake') == 'ok' else "Unexpected response '%s'" % handshake)

    def respond(self, s, image_data=None):
        """
        Envoie un message au serveur et retourne la reponse texte.

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
            if r.get('stream_finished'):
                break
            if r.get('error'):
                print("Stream error:", r['error'])
                break

            chunk = r.get('chunk', '')
            if chunk:
                yield chunk

    def send(self, o):
        o['time'] = datetime.now().isoformat()
        if self.log:
            json.dump({'sending': o}, self.log)
            self.log.write(',\n')
        self.socket.send_json(o)
        r = self.socket.recv_json()
        if self.log:
            json.dump({'receiving': r}, self.log)
            self.log.write(',\n')
        return r

    def reset(self):
        r = self.send({'reset': True, 'user': self.user})
        if r.get('reset') == 'ok':
            print('Dialogue history reset')
        else:
            print('Error resetting dialogue history')


if __name__ == '__main__':
    client = OaiClient(user='test')
    while True:
        s = raw_input('> ')
        if s:
            print('Response: ' + client.respond(s))
        else:
            break
