# -*- coding: utf-8 -*-
# This module implements the main dialogue functionality for Pepper, based on ChatGPT.
# Syntax:
#   python scriptname --pip <ip> --pport <port>
#   --pip <ip>: specify the IP of your robot (without specification it will use the ROBOT_IP defined below)

# Author: Erik Billing, University of Skovde, etc.
# Adapted for always-on, no autonomous life, always standing, animated speech, French accents handled.
# License: MIT

ROBOT_PORT = 9559
ROBOT_IP = "172.20.10.3" # Anciennement "pepper.local"

from optparse import OptionParser
import re
import time
import sys, os
import codecs
import socket
import json

try:
    import urllib2
except ImportError:
    import urllib.request as urllib2

import naoqi
from naoqi import ALProxy
from oaichat.oaiclient import OaiClient

# --- Robust UTF-8 decoder ---
def safedecode(s):
    if isinstance(s, unicode):
        return s
    elif isinstance(s, str):
        try:
            return s.decode('utf-8')
        except Exception:
            return unicode(s, errors='replace')
    else:
        return unicode(s)

STARTPROMPT_PATH = os.getenv('DIALOGUE_STARTPROMPT_FILE')
if STARTPROMPT_PATH and os.path.isfile(STARTPROMPT_PATH):
    with codecs.open(STARTPROMPT_PATH, encoding='utf-8') as f:
        STARTPROMPT = f.read()
else:
    STARTPROMPT = None

participantId = raw_input("Participant ID: ")
chatbot = OaiClient(user=participantId)
chatbot.reset()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def update_tablet_interface(user_text, robot_text, status=None):
    """Envoie les mises a jour au serveur Web local de la tablette"""
    try:
        pc_ip = get_local_ip()
        url = "http://" + pc_ip + ":9091/update"
        
        data = {}
        if user_text is not None:
            if isinstance(user_text, unicode):
                data['user'] = user_text.encode('utf-8')
            else:
                data['user'] = str(user_text)
                
        if robot_text is not None:
            if isinstance(robot_text, unicode):
                data['robot'] = robot_text.encode('utf-8')
            else:
                data['robot'] = str(robot_text)
                
        if status is not None:
            data['status'] = status
            
        req = urllib2.Request(url)
        req.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(req, json.dumps(data))
    except Exception as e:
        pass # On retire le print d'erreur pour ne pas polluer la console si la tablette n'est pas prete


class DialogueModule(naoqi.ALModule):
    """Main dialogue module. Depends on both the ChatGPT service and the Speech Recognition module."""

    def __init__(self, strModuleName, strNaoIp):
        self.misunderstandings = 0
        self.processing = False
        self.log = codecs.open('dialogue.log', 'a', encoding='utf-8')
        
        # NOUVEAU : Variables d'etat pour gerer la tablette
        self.app_mode = "menu"
        self.force_recog_disabled = False
        self.history = [] # Historique local de la conversation (User + Robot)
        
        try:
            naoqi.ALModule.__init__(self, strModuleName)
            self.BIND_PYTHON(self.getName(), "processRemote")
            self.BIND_PYTHON(self.getName(), "onAppModeChanged") # Lier event app mode
            self.BIND_PYTHON(self.getName(), "onRecogDisabled")  # Lier event desactiv_reco
            self.strNaoIp = strNaoIp
        except BaseException, err:
            print(u"ERR: ReceiverModule loading error: %s" % safedecode(err))

    def __del__(self):
        print(u"INF: ReceiverModule.__del__ cleaning everything")
        self.stop()

    def start(self):
        self.configureSpeechRecognition()
        self.memory = naoqi.ALProxy("ALMemory", self.strNaoIp, ROBOT_PORT)
        self.memory.subscribeToEvent("SpeechRecognition", self.getName(), "processRemote")
        
        # S'abonner aux evenements de la tablette
        self.memory.subscribeToEvent("PepperAppMode", self.getName(), "onAppModeChanged")
        self.memory.subscribeToEvent("PepperRecogDisabled", self.getName(), "onRecogDisabled")
        
        print(u"INF: ReceiverModule started!")

        # On essaie d'afficher la page sur la tablette des le debut
        try:
            self.tablet = ALProxy("ALTabletService", self.strNaoIp, ROBOT_PORT)
            self.tablet.enableWifi() # S'assurer que le Wifi est actif
            time.sleep(1)
            
            try:
                stat = self.tablet.getWifiStatus()
                print(">>> TABLET WIFI STATUS: " + str(stat))
                if stat != "CONNECTED":
                    print("ATTENTION: La tablette n'est pas connectee au Wifi !")
                    print("Veuillez connecter la tablette au meme reseau que le robot via les parametres Android.")
            except: pass
            
            # URL locale du PC hote (Pepper doit pouvoir acceder a cette IP)
            pc_ip = get_local_ip()
            url = "http://" + pc_ip + ":9091/"
            print("Tentative d'affichage tablette url: " + url)
            
            # Force refresh
            try:
                self.tablet.hideWebview()
                time.sleep(0.5)
            except: pass
            
            self.tablet.showWebview(url)
        except Exception as e:
            print("Erreur initialisation tablette: " + str(e))

        try:
            self.posture = ALProxy("ALRobotPosture", self.strNaoIp, ROBOT_PORT)
            self.aup = ALProxy("ALAnimatedSpeech", self.strNaoIp, ROBOT_PORT)
            self.tts = ALProxy("ALTextToSpeech", self.strNaoIp, ROBOT_PORT) # Ajout TTS standard
            
            # Ajouter le proxy pour les LEDs
            self.leds = ALProxy("ALLeds", self.strNaoIp, ROBOT_PORT)
            
            # Ajouter le proxy pour les mouvements
            self.motion = ALProxy("ALMotion", self.strNaoIp, ROBOT_PORT)
        except RuntimeError:
            print(u"Can't connect to Naoqi at ip \"%s\" on port %d. \n"
                  "Please check your script arguments. Run with -h option for help." % (self.strNaoIp, ROBOT_PORT))

        try:
            print("Mouvements naturels desactives (Breath)")
        except Exception as e:
            print(u"Erreur mouvements naturels: %s" % safedecode(e))

        if STARTPROMPT:
            answer = safedecode(chatbot.respond(STARTPROMPT))
            self.speak(answer)
            
        self.listen(True)
        print(u"Listening...")

    def stop(self):
        print(u"INF: ReceiverModule stopping...")
        self.memory.unsubscribe(self.getName())
        print(u"INF: ReceiverModule stopped!")

    def versions(self):
        return "2.0"

    def onAppModeChanged(self, signalName, mode):
        print("[MODE] Changement mode recu depuis tablette : " + str(mode))
        self.app_mode = str(mode)
        
        if self.app_mode in ["chat", "menu"]:
            if self.app_mode == "chat":
                # On ne reset PAS le chatbot ici pour garder le contexte si on revient du menu
                # chatbot.reset() 
                # print("[CHAT] Historique IA reinitialise.")
                
                # On renvoie l'historique a la tablette pour l'affichage
                self.restore_history_to_tablet()
                
            if not self.force_recog_disabled:
                self.listen(True)
        else:
            # SI MODE QUIZ (ou autre), COUPER L'ECOUTE DEFINITIVEMENT
            self.listen(False)

    def restore_history_to_tablet(self):
        """Renvoie tout l'historique a la tablette (utile si page rechargee)"""
        print("[HISTORY] Restauration de l'historique sur la tablette...")
        # On envoie un signal vide pour s'assurer que le canal est ouvert
        update_tablet_interface(None, None) 
        
        for msg in self.history:
            if msg['role'] == 'user':
                update_tablet_interface(msg['text'], None)
            elif msg['role'] == 'robot':
                update_tablet_interface(None, msg['text'])
            # DELAI AUGMENTE : 0.6s pour etre sur que le polling JS (0.5s) attrape chaque message
            time.sleep(0.9)


    def onRecogDisabled(self, signalName, disabled):
        print("[RECOG] Desactivation manuelle recue : " + str(disabled))
        if disabled == "True" or disabled == True:
            self.force_recog_disabled = True
            self.listen(False)
        else:
            self.force_recog_disabled = False
            if self.app_mode in ["chat", "menu"]:
                self.listen(True)

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
            self.speechRecognition.setHoldTime(0.8)
            self.speechRecognition.setIdleReleaseTime(0.4)
            self.speechRecognition.setMaxRecordingDuration(10)
            self.speechRecognition.setLookaheadDuration(0.5)

        self.speechRecognition.setLanguage("fr-fr")
        self.speechRecognition.calibrate()
        self.speechRecognition.setAutoDetectionThreshold(8)
        self.listen(False)

    def listen(self, enable):
        # SECURITE : Si on n'est pas dans le bon mode, on bloque l'activation quoiqu'il arrive
        if self.app_mode not in ["chat", "menu"]:
            enable = False
            
        if self.force_recog_disabled:
            enable = False
            
        if enable:
            print("[MIC] START LISTENING")
            self.speechRecognition.start()
            self.speechRecognition.enableAutoDetection()
            self.setEyeColor("green")
            update_tablet_interface(None, None, status="listening")
        else:
            print("[MIC] STOP LISTENING")
            self.speechRecognition.disableAutoDetection()
            self.speechRecognition.pause()
            self.setEyeColor("white")
            update_tablet_interface(None, None, status="waiting")

    def setEyeColor(self, color):
        try:
            duration = 0.1 
            if color == "green":
                self.leds.fadeRGB("FaceLeds", 0x00FF00, duration)
            elif color == "purple":
                self.leds.fadeRGB("FaceLeds", 0x800080, duration)
            elif color == "blue":
                self.leds.fadeRGB("FaceLeds", 0x0000FF, duration)
            elif color == "white":
                self.leds.fadeRGB("FaceLeds", 0xFFFFFF, duration)
            else:
                self.leds.fadeRGB("FaceLeds", 0xFFFFFF, duration)
        except Exception as e:
            print(u"Erreur leds : %s" % safedecode(e))

    def speak(self, text):
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        
        self.setEyeColor("purple")
        update_tablet_interface(None, text, status="robotspeaking")
        self.aup.say(text)
        self.setEyeColor("green")

    def speak_static(self, text):
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        
        self.setEyeColor("purple")
        self.tts.say(text)
        self.setEyeColor("green")

    def dance(self):
        try:
            self.animation = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            self.animation.runBehavior("peppers-date-dance-bis")
        except Exception as e:
            try:
                self.animation.runBehavior("animations/Stand/Waiting/FunnyDancer_1")
            except Exception as e2:
                try:
                    self.animation.runBehavior("locomotion-dancebehavior_1")
                except Exception as e3:
                    pass

    def wave(self):
        try:
            self.animation = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            self.animation.post.runBehavior("animations/Stand/Gestures/Hey_1")
        except Exception as e:
            pass
            
    def laugh(self):
        try:
            self.animation = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            self.animation.runBehavior("animations/Stand/Emotions/Positive/Laugh_1")
        except Exception as e:
            pass

    def speak_async(self, text):
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        try:
            return self.aup.post.say(text)
        except Exception as e:
            print("Erreur speak_async: ", e)
            self.aup.say(text)
            return None

    def clean_for_speech(self, text):
        import re
        if isinstance(text, str):
            try:
                t = text.decode('utf-8')
            except Exception:
                t = unicode(text, errors='replace')
        else:
            t = unicode(text)
            
        t = t.replace(u'\n', u' ').replace(u'\r', u' ').replace(u'**', u'').replace(u'*', u'')
        # On garde les accents pour la prononciation francaise !
        # t = t.replace(u'\xc3\x8a', u'e').replace(u'\u00ca', u'e')
        # t = t.replace(u'\u00c0', u'a').replace(u'\u00c9', u'e').replace(u'\u00c8', u'e')
        t = t.replace(u'•', u' ').replace(u'-', u' ')
        
        t = re.sub(ur'\s+', u' ', t).strip()
        return t.encode('utf-8')

    def handle_streaming_response(self, input_text):
        full_answer = u""
        sentence_buffer = u""
        print(">> ROBOT streaming...")
        
        self.setEyeColor("purple")
        update_tablet_interface(None, u"...", status="robotspeaking")
        last_task_id = None
        
        try:
            for chunk in chatbot.respond_stream(input_text):
                chunk = safedecode(chunk)
                full_answer += chunk
                sentence_buffer += chunk

                try:
                    sys.stdout.write(chunk.encode(sys.stdout.encoding or 'utf-8', 'replace'))
                    sys.stdout.flush()
                except: pass

                # Maj de la tablette EN TEMPS REEL (tres important pour voir le texte s'ecrire)
                update_tablet_interface(None, full_answer)

                # BOUCLE DE DECOUPAGE DES PHRASES
                # On traite toutes les phrases completes presentes dans le buffer
                while True:
                    match = re.search(ur'[.!?]\s', sentence_buffer)
                    if not match:
                        break # Pas de fin de phrase trouvee, on attend le prochain chunk
                    
                    # On a trouve une fin de phrase
                    end_index = match.end()
                    
                    # On extrait la phrase complete
                    current_sentence = sentence_buffer[:end_index]
                    # ET SURTOUT : On garde le reste du buffer pour la suite !
                    sentence_buffer = sentence_buffer[end_index:]
                    
                    clean_sentence = self.clean_for_speech(current_sentence)
                    
                    if last_task_id:
                        try:
                            self.aup.wait(last_task_id, 0)
                        except Exception: pass
                    
                    # SECURITE ANTI LETTRE ISOLEE
                    import re as reg_test
                    mots_seulement = reg_test.sub(ur'[^\w]', u'', clean_sentence)
                    
                    if len(mots_seulement) > 1:
                        last_task_id = self.speak_async(clean_sentence)

            # Fin du flux (derniers mots restants dans le buffer)
            if sentence_buffer:
                clean_sentence = self.clean_for_speech(sentence_buffer)

                if last_task_id:
                    try:
                        self.aup.wait(last_task_id, 0)
                    except Exception: pass
                
                import re as reg_test2
                mots_seulement = reg_test2.sub(ur'[^\w]', u'', clean_sentence)
                
                if len(mots_seulement) > 1:
                    last_task_id = self.speak_async(clean_sentence)
                    
                print("") # Retour a la ligne dans la console
                
            # ENVOI FINAL OBLIGATOIRE POUR L'HISTORIQUE (verrouille le robot_text final)
            update_tablet_interface(None, full_answer)
            self.log.write(u"ANS: " + full_answer + u"\n")
            
            # Ajout a l'historique local
            self.history.append({'role': 'robot', 'text': full_answer})

            if last_task_id is not None:
                try:
                    self.aup.wait(last_task_id, 0)
                except Exception as e:
                    time.sleep(1.0)
                    
        except Exception as e:
            print("Stream error: ", repr(e))
            self.speak("Desole, j'ai eu un probleme technique.")
            
        finally:
            self.setEyeColor("white")
            update_tablet_interface(None, None, status="waiting")
            try:
                self.speechRecognition.pause()
            except: pass
            
            time.sleep(0.2)
            self.processing = False
            
            if hasattr(self, 'app_mode'):
                if self.app_mode in ["chat", "menu"] and getattr(self, 'force_recog_disabled', False) == False:
                    self.listen(True)
            else:
                self.listen(True)

    def processRemote(self, signalName, message):
        print("DEBUG_RAW_RECEIVE: Signal: {} Content: {}".format(signalName, message))
        
        if self.app_mode not in ["chat", "menu"]:
            return

        if self.processing:
            print("Message ignore car deja en traitement.")
            return

        if message is None or message == "None" or message == "<error>":
            if self.app_mode in ["chat", "menu"] and not self.force_recog_disabled:
                self.listen(True)
            return

        self.processing = True
        
        try:
            message_str = safedecode(message)
            if len(message_str.strip()) == 0:
                self.processing = False
                if self.app_mode in ["chat", "menu"] and not self.force_recog_disabled:
                    self.listen(True)
                return
                
            self.log.write(u"INP: " + message_str + u"\n")
            self.listen(False)
            print(u"USER: " + message_str)
            
            # Ajout a l'historique local
            self.history.append({'role': 'user', 'text': message_str})
            
            update_tablet_interface(message_str, None, status="waiting")
            
            if message_str == u"<error>":
                self.misunderstandings += 1
                if self.misunderstandings == 1:
                    answer = u"Je n'ai pas compris, peux-tu repeter ?"
                elif self.misunderstandings == 2:
                    answer = u"Desole, je n'ai pas compris. Pourrais-tu repeter encore ?"
                else:
                    answer = u"Aujourd'hui j'ai des difficultes a comprendre, desole."
                
                print(u"ERREUR, REPONSE PAR DEFAUT: " + answer)
                update_tablet_interface(None, answer)
                self.speak(answer)
            else:
                self.misunderstandings = 0
                message_lower = message_str.lower()
                
                if u"danse" in message_lower or u"dance" in message_lower:
                    answer = u"Je danse pour vous !"
                    update_tablet_interface(None, answer)
                    self.speak(answer)
                    self.dance()
                elif u"serre" in message_lower and u"main" in message_lower:
                    answer = u"Je ne peux pas serrer la main, mais je peux faire coucou."
                    update_tablet_interface(None, answer)
                    self.speak(answer)
                    self.wave()
                elif u"blague" in message_lower or u"rigole" in message_lower or u"rire" in message_lower:
                    self.handle_streaming_response(message_str)
                    self.laugh()
                elif u"bonjour" in message_lower or u"salut" in message_lower or u"hello" in message_lower:
                    self.wave()
                    self.handle_streaming_response(message_str)
                else:
                    self.handle_streaming_response(message_str)
                    
        finally:
            self.processing = False
            if self.app_mode in ["chat", "menu"] and not self.force_recog_disabled:
                self.listen(True)

    def react(self, s):
        s = safedecode(s)
        if re.match(u".*je.*m.asseoir.*", s):
            self.posture.goToPosture("Sit", 1.0)
        elif re.match(u".*je.*me.*lève.*", s):
            self.posture.goToPosture("Stand", 1.0)
        elif re.match(u".*je.*m.allonge.*", s):
            self.posture.goToPosture("LyingBack", 1.0)

def main():
    parser = OptionParser()
    parser.add_option("--pip",
        help="IP/hostname of broker. Default is 192.168.1.103",
        dest="pip", default=ROBOT_IP)
    parser.add_option("--pport",
        help="port of broker. Default is 9559",
        dest="pport", default=ROBOT_PORT)
    parser.add_option("--prompt",
        help="prompt file name without .prompt extension. Default pepper",
        dest="prompt", default="pepper")
    
    (opts, args_) = parser.parse_args()
    pip   = opts.pip
    pport = opts.pport

    myBroker = naoqi.ALBroker("myBroker",
       "0.0.0.0",   # listen to anyone
       0,           # find a free port and use it
       pip,         # parent broker IP
       pport)       # parent broker port

    try:
        p = ALProxy("dialogueModule")
        p.exit()
    except:
        pass

    try:
        audio = ALProxy("ALAudioDevice")
        audio.setOutputVolume(70)
    except: pass

    # Toujours DESACTIVER AutonomousLife et mettre debout
    try:
        AutonomousLife = ALProxy('ALAutonomousLife')
        if AutonomousLife.getState() != 'disabled':
            AutonomousLife.setState('disabled')

        RobotPosture = ALProxy('ALRobotPosture')
        RobotPosture.goToPosture('Stand', 0.5)
        print(u"Vie autonome desactivee. Robot debout, pret a interagir avec gestuelle animee.")
        
        TabletService = ALProxy('ALTabletService')
        try:
            TabletService.wakeUp()
        except: pass
    except: pass

    global dialogueModule
    dialogueModule = DialogueModule("dialogueModule", pip)
    dialogueModule.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(u"Interrompu par l'utilisateur, extinction...")
        myBroker.shutdown()
        sys.exit(0)

if __name__ == '__main__':
    main()
