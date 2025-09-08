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
import codecs
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

def write_console(text):
    if isinstance(text, unicode):
        try:
            sys.stdout.write(text.encode('utf-8', 'replace'))
        except Exception:
            try:
                sys.stdout.write(text.encode('cp1252', 'replace'))
            except Exception:
                return
    else:
        try:
            sys.stdout.write(text)
        except Exception:
            try:
                sys.stdout.write(unicode(text, errors='replace').encode('utf-8', 'replace'))
            except Exception:
                return
    try:
        sys.stdout.flush()
    except Exception:
        pass

# Ensure stdout can emit UTF-8 on Windows/Python2
try:
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
except Exception:
    pass

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
            self.BIND_PYTHON(self.getName(), "callback")
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
        # Allow runtime overrides via environment variables
        AUTODEC = os.getenv('SPEECH_AUTODEC', 'true').lower() == 'true'
        hold_time = float(os.getenv('SPEECH_HOLD_TIME', '2.5'))
        idle_release = float(os.getenv('SPEECH_IDLE_RELEASE', '2.0'))
        max_rec = int(float(os.getenv('SPEECH_MAX_RECORDING', '10')))
        lookahead = float(os.getenv('SPEECH_LOOKAHEAD', '0.5'))
        language = os.getenv('SPEECH_LANGUAGE', 'fr-fr')
        threshold = int(os.getenv('SPEECH_AUTODETECTION_THRESHOLD', '6'))
        if not AUTODEC:
            print(u"False, auto-detection not available")
            self.speechRecognition.setHoldTime(hold_time)
            self.speechRecognition.setIdleReleaseTime(idle_release)
            self.speechRecognition.setMaxRecordingDuration(max_rec)
        else:
            print(u"True, auto-detection selected")
            self.speechRecognition.setHoldTime(hold_time)
            self.speechRecognition.setIdleReleaseTime(idle_release)
            self.speechRecognition.setMaxRecordingDuration(max_rec)
            self.speechRecognition.setLookaheadDuration(lookahead)
            self.speechRecognition.setLanguage(language)
            self.speechRecognition.calibrate()
            self.speechRecognition.setAutoDetectionThreshold(threshold)
        self.listen(False)

    def listen(self, enable):
        if enable:
            self.speechRecognition.start()
            self.speechRecognition.enableAutoDetection()
        else:
            self.speechRecognition.disableAutoDetection()
            self.speechRecognition.pause()

    def speak(self, text):
        # Always encode as UTF-8 bytes before say()
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        self.aup.say(text)

    def processRemote(self, signalName, message):
        message = safe_decode(message)
        self.log.write(u'INP: ' + message + u'\n')
        if message == u'error':
            return
        
        self.listen(False)  # Couper l'écoute
        write_console(u"USER:\n" + message + u"\n")
        
        if message != u'error':
            self.misunderstandings = 0
            complete_answer = self.stream_and_speak(message)
            self.log.write(u'ANS: ' + complete_answer + u'\n')
        
        # Réactiver l'écoute seulement APRÈS que Pepper ait fini de parler
        self.listen(True)

    def stream_and_speak(self, message):
        """Génère en streaming, parle immédiatement, retourne la réponse complète"""
        word_buffer = ""
        sentence_buffer = ""
        complete_response = ""
        
        write_console(u'ROBOT (streaming):\n')
        
        for token in chatbot.stream_respond(message):
            complete_response += token  # Accumule pour les logs
            word_buffer += token
            
            # Parler par segments de 4-6 mots ou à la ponctuation forte
            if token.endswith(' ') or token in '.!?,:':
                sentence_buffer += word_buffer
                word_buffer = ""
                
                # Critères pour parler un segment
                word_count = len(sentence_buffer.split())
                if word_count >= 5 or token in '.!?' or token == ',':
                    segment = sentence_buffer.strip()
                    if segment:
                        write_console(segment + ' ')
                        self.speak(segment)      # Pepper parle immédiatement
                    sentence_buffer = ""
        
        # Parler le dernier segment s'il reste quelque chose
        if sentence_buffer.strip():
            self.speak(sentence_buffer.strip())
            print(sentence_buffer.strip())
        
        write_console(u'\n')  # Nouvelle ligne après la réponse complète
        return complete_response


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
    parser.add_option("--pip", help="Parent broker port. The IP address of your robot", dest="pip")
    parser.add_option("--pport", help="Parent broker port. The port NAOqi is listening to", dest="pport", type="int")
    parser.set_defaults(
        pip=ROBOT_IP,
        pport=ROBOT_PORT
    )
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
