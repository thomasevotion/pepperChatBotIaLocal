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

def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def update_tablet_interface(user_text, robot_text):
    """Envoie les mises a jour au serveur Web local de la tablette"""
    try:
        import urllib2
        import json
        # Detection dynamique de l'IP du PC pour que ca marche a coup sur
        pc_ip = get_local_ip()
        url = "http://" + pc_ip + ":9090/update"
        data = {}
        if user_text:
            # Encodage safe pour JSON
            if isinstance(user_text, unicode):
                data['user'] = user_text.encode('utf-8')
            else:
                data['user'] = str(user_text)
        if robot_text:
            if isinstance(robot_text, unicode):
                data['robot'] = robot_text.encode('utf-8')
            else:
                data['robot'] = str(robot_text)
            
        req = urllib2.Request(url)
        req.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(req, json.dumps(data))
    except Exception as e:
        print "ERREUR TABLETTE:", str(e)

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
        
        # Lancer le serveur Web local si ce n'est pas deja fait (via subprocess pourrait etre mieux, mais on suppose qu'il est lance a part)
        # On essaie d'afficher la page sur la tablette des le debut
        try:
            self.tablet = ALProxy("ALTabletService", self.strNaoIp, ROBOT_PORT)
            # URL locale du PC hote (Pepper doit pouvoir acceder a cette IP)
            # ATTENTION: Il faut que PepperWebLocal/main.py soit lance sur la meme machine
            # Et que l'IP soit accessible. Ici on laisse le script main.py gerer l'affichage initial
            pass
        except:
            pass

        try:
            self.posture = ALProxy("ALRobotPosture", self.strNaoIp, ROBOT_PORT)
            self.aup = ALProxy("ALAnimatedSpeech", self.strNaoIp, ROBOT_PORT)
            self.tts = ALProxy("ALTextToSpeech", self.strNaoIp, ROBOT_PORT) # Ajout TTS standard
            # Ajouter le proxy pour les LEDs
            self.leds = ALProxy("ALLeds", self.strNaoIp, ROBOT_PORT)
            # Ajouter le proxy pour les mouvements
            self.motion = ALProxy("ALMotion", self.strNaoIp, ROBOT_PORT)
        except RuntimeError:
            print(u"Can't connect to Naoqi at ip \"%s\" on port %d.\nPlease check your script arguments. Run with -h option for help." % (self.strNaoIp, ROBOT_PORT))
        # Activer les mouvements naturels (version simplifiée)
        try:
            self.motion.setBreathEnabled("Body", True)
            print("Mouvements naturels activés")
        except Exception as e:
            print(u"Erreur mouvements naturels: %s" % safe_decode(e))
        
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
            # Activer les mouvements naturels pendant l'écoute
            try:
                self.motion.setBreathEnabled("Body", True)
            except:
                pass
        else:
            self.speechRecognition.disableAutoDetection()
            self.speechRecognition.pause()
            # Désactiver les mouvements pendant la parole
            try:
                self.motion.setBreathEnabled("Body", False)
            except:
                pass
    
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

    def speak_static(self, text):
        """Parler sans gestuelle automatique (pour ne pas casser les animations en cours)"""
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        self.setEyeColor("purple")
        self.tts.say(text) # Utilise TextToSpeech au lieu de AnimatedSpeech
        self.setEyeColor("green")
    
    def dance(self):
        """Lancer une danse"""
        try:
            # Utiliser l'animation de danse qui fonctionne
            self.animation = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            self.animation.runBehavior("peppers-date-dance-bis")
            print("Pepper danse !")
        except Exception as e:
            print(u"Animation de danse principale non disponible, essai d'alternatives")
            try:
                # Alternative 1: Danseur amusant
                self.animation.runBehavior("animations/Stand/Waiting/FunnyDancer_1")
                print("Pepper fait une danse amusante !")
            except Exception as e2:
                try:
                    # Alternative 2: Danse de locomotion
                    self.animation.runBehavior("locomotion-dance/behavior_1")
                    print("Pepper fait une danse de locomotion !")
                except Exception as e3:
                    print(u"Aucune animation de danse disponible: %s" % safe_decode(e3))
    
    def wave(self):
        """Faire coucou"""
        try:
            # Utiliser l'animation de coucou de maniere asynchrone
            self.animation = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            # Utiliser post.runBehavior pour ne pas bloquer la parole
            self.animation.post.runBehavior("animations/Stand/Gestures/Hey_1")
            print("Pepper fait coucou !")
        except Exception as e:
            print(u"Animation de coucou non disponible: %s" % safe_decode(e))
    
    def laugh(self):
        """Animation de rire"""
        try:
            # Utiliser l'animation de rire qui fonctionne
            self.animation = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            self.animation.runBehavior("animations/Stand/Emotions/Positive/Laugh_1")
            print("Pepper rigole !")
        except Exception as e:
            print(u"Animation de rire non disponible: %s" % safe_decode(e))
    
    
    def naturalIdleMovement(self):
        """Mouvement d'attente naturel"""
        try:
            # Mouvements subtils d'attente
            import random
            import time
            
            # Mouvement léger de la tête
            if random.random() < 0.3:  # 30% de chance
                self.motion.setAngles("HeadYaw", random.uniform(-0.2, 0.2), 0.1)
                time.sleep(0.5)
                self.motion.setAngles("HeadYaw", 0, 0.1)
            
            # Mouvement léger des bras
            if random.random() < 0.2:  # 20% de chance
                self.motion.setAngles("LShoulderPitch", random.uniform(-0.1, 0.1), 0.1)
                time.sleep(0.3)
                self.motion.setAngles("LShoulderPitch", 0, 0.1)
                
        except Exception as e:
            print(u"Erreur lors du mouvement naturel: %s" % safe_decode(e))

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
        
        # Mise a jour tablette (User)
        update_tablet_interface(message, None)

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
            
            # LOGIQUE INTELLIGENTE POUR LES COMPORTEMENTS
            message_lower = message.lower()
            
            # 1. DANSE - Si l'utilisateur demande de danser
            if "danse" in message_lower or "dance" in message_lower:
                answer = "Je danse pour vous !"
                # Mise a jour tablette (Robot)
                update_tablet_interface(None, answer)
                self.speak(answer)
                self.dance()
                self.listen(True)
                return
            
            # 2. SERRE LA MAIN - Réponse spéciale
            elif "serre" in message_lower and "main" in message_lower:
                answer = "Je ne peux pas serrer la main mes mains sont fragiles mais je peux faire coucou."
                update_tablet_interface(None, answer)
                self.speak(answer)
                self.wave()
                self.listen(True)
                return
            
            # 3. BLAGUE - Détecter si c'est une blague et rire après
            elif "blague" in message_lower or "rigole" in message_lower or "rire" in message_lower:
                answer = safe_decode(chatbot.respond(message))
                try:
                    print(u'ROBOT:\n' + answer)
                except:
                    print(u'ROBOT:\n' + answer.encode('ascii', 'replace'))
                update_tablet_interface(None, answer)
                self.speak(answer)
                self.laugh()  # Rire après la blague
                self.react(answer)
                self.listen(True)
                return  # Sortir de la fonction
            
            # 4. BONJOUR - Combiner IA + comportement
            elif "bonjour" in message_lower or "salut" in message_lower or "hello" in message_lower:
                answer = safe_decode(chatbot.respond(message))
                try:
                    print(u'ROBOT:\n' + answer)
                except:
                    print(u'ROBOT:\n' + answer.encode('ascii', 'replace'))
                update_tablet_interface(None, answer)
                self.wave() # Lancer le geste de manière asynchrone
                self.speak_static(answer) # Parler sans gestes pour laisser le coucou se faire
                self.react(answer)
                self.listen(True)
                return  # Sortir de la fonction
            
            # 5. AUTRES - Réponse IA uniquement
            else:
                answer = safe_decode(chatbot.respond(message))
            try:
                print(u'ROBOT:\n' + answer)
            except:
                print(u'ROBOT:\n' + answer.encode('ascii', 'replace'))
            
            update_tablet_interface(None, answer)

        self.log.write(u'ANS: ' + answer + u'\n')
        self.speak(answer)
        self.react(answer)
        
        # Le mouvement naturel manuel est supprimé car il interrompt les animations
        # La respiration est gérée automatiquement par self.listen(True)
        time.sleep(1.0) # Pause pour eviter que le robot ne s'ecoute lui-meme (echo)
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
    try:
        TabletService.wakeUp() # Forcer l'allumage de l'ecran
    except:
        pass

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
