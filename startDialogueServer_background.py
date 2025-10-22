# -*- coding: utf-8 -*-

###########################################################
# This is the main startup script for the GPT-3 OpenAI chatbot server.  
# Version modifiée pour fonctionner en arrière-plan
#
# Syntax:
#    python3 startDialogueServer_background.py [--prompt yourPromptFile.prompt]
#
# Author: Erik Billing, University of Skovde
# Created: June 2022. 
# License: Copyright reserved to the author. 
###########################################################

from oaichat.oaiserver import OaiServer
from optparse import OptionParser
import time
import signal
import sys

def signal_handler(sig, frame):
    print('\nArrêt du serveur...')
    server.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

parser = OptionParser()
parser.add_option("--prompt",
    help="Path to propot file.",
    dest="prompt")
parser.set_defaults(prompt='pepper')
  
if __name__ == '__main__':
    (opts, args_) = parser.parse_args()
    server = OaiServer(user='User 1',prompt=opts.prompt + '.prompt')
    server.start()
    
    print('Serveur OpenAI démarré en arrière-plan...')
    print('Appuyez sur Ctrl+C pour arrêter')
    
    try: 
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    print('GPT Server fermé.')

