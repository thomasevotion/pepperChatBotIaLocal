# -*- coding: utf-8 -*-

###########################################################
# This module implements the main dialogue functionality for Pepper, based on ChatGPT.
#
# Syntax:
#    python scriptname --pip <ip> --pport <port>
#
#    --pip <ip>: specify the IP of your robot (without specification it will use the ROBOT_IP defined below)
#
# Author: Erik Billing, University of Skovde, etc.
# Adapted for always-on, no autonomous life, always standing, animated speech, French accents handled.
# License: MIT
###########################################################

ROBOT_PORT = 9559
ROBOT_IP = "pepper.local"

from optparse import OptionParser
import re
import naoqi
import time
import sys, os
import codecs
from naoqi import ALProxy
from oaichat.oaiclient import OaiClient

# --- Robust UTF-8 decoder ---
def safe_decode(s):
    if isinstance(s, unicode):
        return s
    elif isinstance(s, str):
        try:
            return s.decode('utf-8')
        except Exception:
            return unicode(s, errors='replace')
    else:
        return unicode(s)

START_PROMPT_PATH = os.getenv('DIALOGUE_START_PROMPTFILE')
if START_PROMPT_PATH and os.path.isfile(START_PROMPT_PATH):
    with codecs.open(START_PROMPT_PATH, encoding='utf-8') as f:
        START_PROMPT = f.read()
else:
    START_PROMPT = None

participantId = raw_input('Participant ID: ')

chatbot = OaiClient(user=participantId)
chatbot.reset()

class DialogueModule(naoqi.ALModule):
    """
    Main dialogue module. Depends on both the ChatGPT service and the Speech Recognition module.
    """
    def __init__(self, strModuleName, strNaoIp):
        self.misunderstandings = 0
        self.log = codecs.open('dialogue.log', 'a', encoding='utf-8')
        try:
            naoqi.ALModule.__init__(self, strModuleName)
            self.BIND_PYTHON(self.getName(), "processRemote")
            self.strNaoIp = strNaoIp
        except BaseException, err:
            print(u"ERR: ReceiverModule: loading error: %s" % safe_decode(err))

    def __del__(self):
        print(u"INF: ReceiverModule.__del__: cleaning everything")
        self.stop()

    def start(self):
        self.configureSpeechRecognition()
        self.memory = naoqi.ALProxy("ALMemory", self.strNaoIp, ROBOT_PORT)
        self.memory.subscribeToEvent("SpeechRecognition", self.getName(), "processRemote")
        print(u"INF: ReceiverModule: started!")
        try:
            self.posture = ALProxy("ALRobotPosture", self.strNaoIp, ROBOT_PORT)
            self.aup = ALProxy("ALAnimatedSpeech", self.strNaoIp, ROBOT_PORT)
            # Ajouter le proxy pour les LEDs
            self.leds = ALProxy("ALLeds", self.strNaoIp, ROBOT_PORT)
        except RuntimeError:
            print(u"Can't connect to Naoqi at ip \"%s\" on port %d.\nPlease check your script arguments. Run with -h option for help." % (self.strNaoIp, ROBOT_PORT))
        if START_PROMPT:
            answer = safe_decode(chatbot.respond(START_PROMPT))
            self.speak(answer)
        self.listen(True)
        print(u'Listening...')

    def stop(self):
        print(u"INF: ReceiverModule: stopping...")
        self.memory.unsubscribe(self.getName())
        print(u"INF: ReceiverModule: stopped!")

    def version(self):
        return "2.0"

    def configureSpeechRecognition(self):
        self.speechRecognition = ALProxy("SpeechRecognition")
        AUTODEC = True
        if not AUTODEC:
            print(u"False, auto-detection not available")
            self.speechRecognition.setHoldTime(5)
            self.speechRecognition.setIdleReleaseTime(1.7)
            self.speechRecognition.setMaxRecordingDuration(10)
        else:
            print(u"True, auto-detection selected")
            self.speechRecognition.setHoldTime(2.5)
            self.speechRecognition.setIdleReleaseTime(2.0)
            self.speechRecognition.setMaxRecordingDuration(10)
            self.speechRecognition.setLookaheadDuration(0.5)
            self.speechRecognition.setLanguage("fr-fr")
            self.speechRecognition.calibrate()
            self.speechRecognition.setAutoDetectionThreshold(6)
        self.listen(False)

    def listen(self, enable):
        if enable:
            self.speechRecognition.start()
            self.speechRecognition.enableAutoDetection()
            # Yeux VERT quand Pepper écoute
            self.setEyeColor("green")
        else:
            self.speechRecognition.disableAutoDetection()
            self.speechRecognition.pause()
    
    def setEyeColor(self, color):
        """Changer la couleur des yeux de Pepper"""
        try:
            if color == "green":
                # Vert pour écouter
                self.leds.fadeRGB("FaceLeds", 0x00FF00, 0.5)  # Vert
            elif color == "purple":
                # Violet pour parler
                self.leds.fadeRGB("FaceLeds", 0x800080, 0.5)  # Violet
            elif color == "blue":
                # Bleu par défaut
                self.leds.fadeRGB("FaceLeds", 0x0000FF, 0.5)  # Bleu
            else:
                # Couleur par défaut
                self.leds.fadeRGB("FaceLeds", 0xFFFFFF, 0.5)  # Blanc
        except Exception as e:
            print(u"Erreur lors du changement de couleur des yeux: %s" % safe_decode(e))

    def speak(self, text):
        # Always encode as UTF-8 bytes before say()
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        # Yeux VIOLET quand Pepper parle
        self.setEyeColor("purple")
        self.aup.say(text)
        # Remettre les yeux verts après avoir parlé
        self.setEyeColor("green")

    def processRemote(self, signalName, message):
        # NAOqi ALMemory subscribeToEvent callback signature:
        # (signalName, message)
        print("DEBUG - signalName:", signalName)
        print("DEBUG - message:", message)
        message = safe_decode(message)
        self.log.write(u'INP: ' + message + u'\n')
        if message == u'error':
            return
        self.listen(False)
        print(u"USER:\n" + message)
        if message == u'error':
            self.misunderstandings += 1
            if self.misunderstandings == 1:
                answer = u"Je n'ai pas compris, peux-tu répéter ?"
            elif self.misunderstandings == 2:
                answer = u"Désolé, je n’ai pas compris. Pourrais-tu répéter encore ?"
            elif self.misunderstandings == 3:
                answer = u"Aujourd'hui j'ai des difficultés à comprendre, désolé."
            else:
                answer = u"Peux-tu répéter cela ?"
            print(u'ERREUR, REPONSE PAR DEFAUT:\n' + answer)
        else:
            self.misunderstandings = 0
            answer = safe_decode(chatbot.respond(message))
            print(u'ROBOT:\n' + answer)
        self.log.write(u'ANS: ' + answer + u'\n')
        self.speak(answer)
        self.react(answer)
        self.listen(True)

    def react(self, s):
        s = safe_decode(s)
        if re.match(u".*je.*m.*asseoir.*", s):
            self.posture.goToPosture("Sit", 1.0)
        elif re.match(u".*je.*me l[e|ai]ve.*", s):
            self.posture.goToPosture("Stand", 1.0)
        elif re.match(u".*je.*m.*allonge.*", s):
            self.posture.goToPosture("LyingBack", 1.0)

def main():
    parser = OptionParser()
    parser.add_option("--pip", dest="pip", default=ROBOT_IP,
                      help="IP/hostname of broker. Default: 192.168.1.188")
    parser.add_option("--pport", dest="pport", default=ROBOT_PORT,
                      help="port of broker. Default: 9559")
    parser.add_option("--prompt", dest="prompt", default="pepper",
                      help="prompt file name (without .prompt extension). Default: pepper")

    (opts, args_) = parser.parse_args()
    pip = opts.pip
    pport = opts.pport

    myBroker = naoqi.ALBroker("myBroker", "0.0.0.0", 0, pip, pport)

    try:
        p = ALProxy("dialogueModule")
        p.exit()
    except:
        pass

    audio = ALProxy("ALAudioDevice")
    audio.setOutputVolume(70)

    # Toujours DESACTIVER AutonomousLife et mettre debout :
    AutonomousLife = ALProxy('ALAutonomousLife')
    if AutonomousLife.getState() != 'disabled':
        AutonomousLife.setState('disabled')
    RobotPosture = ALProxy('ALRobotPosture')
    RobotPosture.goToPosture('Stand', 0.5)
    print(u'Vie autonome désactivée. Robot debout, prêt à interagir avec gestuelle animée.')

    TabletService = ALProxy('ALTabletService')
    TabletService.goToSleep()

    global dialogueModule
    dialogueModule = DialogueModule("dialogueModule", pip)
    dialogueModule.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(u"\nInterrompu par l'utilisateur, extinction")
        myBroker.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()
