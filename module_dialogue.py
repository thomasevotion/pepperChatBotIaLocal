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
import unicodedata

try:
    import urllib2
except ImportError:
    import urllib.request as urllib2

import base64
import threading
import naoqi
from naoqi import ALProxy
from oaichat.oaiclient import OaiClient
import animation_selector

# --- Configuration camera ---
# Mettre a False pour desactiver completement l'envoi d'image a Gemini
CAMERA_ENABLED = True
# Resolution NaoQI : 0=160x120, 1=320x240, 2=640x480
# On utilise 1 (320x240) : assez de detail, taille raisonnable
CAMERA_RESOLUTION = 1
# Intervalle en secondes entre deux captures automatiques
CAMERA_INTERVAL = 45

# --- Commentaires proactifs sur l'environnement ---
# Pepper observe la scene et fait spontanement un commentaire si quelque chose est notable
ENV_COMMENT_ENABLED  = True  # Mettre False pour desactiver
ENV_COMMENT_INTERVAL = 180   # Secondes entre deux tentatives de commentaire
ENV_COMMENT_MIN_IDLE = 60    # Pepper parle seulement s'il est inactif depuis X secondes

# --- Langues TTS NAOqi ---
# Anglais par defaut : Pepper parle et ecoute en anglais, et ne bascule vers une autre
# langue que si l'utilisateur la parle explicitement (detection STT) ou la demande
# explicitement (voir _detect_requested_tts_language / LANGUAGE_NAME_ALIASES).
DEFAULT_STT_LANGUAGE_CODE = "en-US"
DEFAULT_NAOQI_LANGUAGE = "English"
BCP47_TO_NAOQI_LANGUAGE = {
    "fr": "French",
    "fr-fr": "French",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "es": "Spanish",
    "es-es": "Spanish",
    "de": "German",
    "de-de": "German",
    "it": "Italian",
    "it-it": "Italian",
    "ja": "Japanese",
    "ja-jp": "Japanese",
    "ar": "Arabic",
    "ar-sa": "Arabic",
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-tw": "Taiwanese",
    "cs": "Czech",
    "cs-cz": "Czech",
    "da": "Danish",
    "da-dk": "Danish",
    "nl": "Dutch",
    "nl-nl": "Dutch",
    "fi": "Finnish",
    "fi-fi": "Finnish",
    "el": "Greek",
    "el-gr": "Greek",
    "ko": "Korean",
    "ko-kr": "Korean",
    "no": "Norwegian",
    "nb": "Norwegian",
    "nb-no": "Norwegian",
    "pl": "Polish",
    "pl-pl": "Polish",
    "pt": "Portuguese",
    "pt-pt": "Portuguese",
    "pt-br": "Brazilian",
    "ru": "Russian",
    "ru-ru": "Russian",
    "sv": "Swedish",
    "sv-se": "Swedish",
    "tr": "Turkish",
    "tr-tr": "Turkish",
}

LANGUAGE_NAME_ALIASES = [
    ("English",    [u"anglais", u"english", u"ingles", u"inglés", u"englisch", u"英語", u"英语", u"英文"]),
    ("French",     [u"francais", u"français", u"french", u"frances", u"francés", u"franzosisch", u"französisch", u"francese", u"francés"]),
    ("Japanese",   [u"japonais", u"japanese", u"japones", u"japonés", u"giapponese", u"japanisch", u"日本語", u"日本"]),
    ("German",     [u"allemand", u"german", u"deutsch", u"aleman", u"alemán", u"tedesco"]),
    ("Spanish",    [u"espagnol", u"spanish", u"espanol", u"español", u"castellano", u"spagnolo"]),
    ("Italian",    [u"italien", u"italian", u"italiano", u"italienisch"]),
    ("Arabic",     [u"arabe", u"arabic", u"arabe", u"arabisch", u"العربية", u"عربي"]),
    ("Chinese",    [u"chinois", u"mandarin", u"chinese", u"中文", u"普通话", u"漢語", u"汉语"]),
    ("Taiwanese",  [u"taiwanais", u"taiwanese", u"taiwan", u"台灣", u"台湾"]),
    ("Czech",      [u"tcheque", u"tchèque", u"czech", u"cesky", u"česky", u"ceco"]),
    ("Danish",     [u"danois", u"danish", u"dansk", u"danese"]),
    ("Dutch",      [u"neerlandais", u"néerlandais", u"dutch", u"nederlands", u"hollandais", u"olandese"]),
    ("Finnish",    [u"finnois", u"finnish", u"suomi", u"finlandese"]),
    ("Greek",      [u"grec", u"greek", u"ellinika", u"ελληνικά", u"greco"]),
    ("Korean",     [u"coreen", u"coréen", u"korean", u"hanguk", u"한국어", u"coreano"]),
    ("Norwegian",  [u"norvegien", u"norvégien", u"norwegian", u"norsk", u"norvegese"]),
    ("Polish",     [u"polonais", u"polish", u"polski", u"polaco", u"polacco"]),
    ("Portuguese", [u"portugais", u"portuguese", u"portugues", u"português", u"portoghese"]),
    ("Brazilian",  [u"bresilien", u"brésilien", u"brazilian", u"brasilien", u"brasileiro", u"brasiliano"]),
    ("Russian",    [u"russe", u"russian", u"russkiy", u"русский", u"russo"]),
    ("Swedish",    [u"suedois", u"suédois", u"swedish", u"svenska", u"svedese"]),
    ("Turkish",    [u"turc", u"turkish", u"turkce", u"türkçe", u"turco"]),
]

# --- Corrections phonetiques TTS ---
# Le moteur TTS de Pepper mispronounce certains mots.
# Ajouter ici les substitutions : {mot_original: phonetique}.
# Attention : les remplacements sont appliques au texte envoye au TTS seulement,
# pas au texte affiche sur la tablette.
TTS_PHONETIC_MAP = {
    u"explorer":  u"exploré",
    u"Explorer":  u"Exploré",
    u"explorez":  u"exploré",
    u"Explorez":  u"Exploré",
    u"exploreur": u"exploreur",   # si le bug produit deja ce mot, on le laisse
    u"Véolia":    u"Véolia",      # force la prononciation avec accent
    u"Just Dance" : u"Jeust dennsse",
    u"photocall" : u"Photo kaulle",
    u"Encore plus" : u"Encore plusse",
    u"IATECH" : u"Iatech",
}

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

def safe_print(text):
    """print() qui ne plante jamais sur un caractere absent du codepage de la console
    (ex: 'oe' est present dans cp437 mais pas 'oe' ligature/'œ' -> UnicodeEncodeError).
    Utilise pour tout texte libre (parole utilisateur, reponse LLM) dont le contenu
    n'est pas maitrise."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or 'ascii'
        print(safedecode(text).encode(enc, 'replace'))

def repair_mojibake(text):
    """Repare les textes UTF-8 parfois interpretes comme CP437 par la chaine Python 2/ZMQ."""
    text_u = safedecode(text)
    suspicious_markers = [
        u"Ò", u"Þ", u"Õ", u"µ", u"╬", u"╧", u"╨", u"Ð", u"Ñ", u"╟", u"├", u"┘", u"┙", u"┌"
    ]
    if not any(marker in text_u for marker in suspicious_markers):
        return text_u

    try:
        repaired = text_u.encode('cp437').decode('utf-8')
        # On garde la correction seulement si elle produit de vrais caracteres non latins.
        if re.search(ur'[\u0370-\u03ff\u0400-\u04ff\u0600-\u06ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', repaired):
            return repaired
    except Exception:
        pass
    return text_u

def normalize_lang_text(text):
    text = repair_mojibake(text).lower()
    text = unicodedata.normalize('NFKD', text)
    text = u"".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(ur"[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0600-\u06ff]+", u" ", text, flags=re.UNICODE)
    return re.sub(ur"\s+", u" ", text).strip()

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

def apply_tts_fixes(text):
    """Applique les corrections phonetiques du dictionnaire TTS_PHONETIC_MAP.
    Prend une str ou unicode, retourne unicode.
    """
    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8')
        except Exception:
            text = unicode(text, errors='replace')
    for wrong, correct in TTS_PHONETIC_MAP.items():
        text = text.replace(wrong, correct)
    return text


def update_tablet_interface(user_text, robot_text, status=None):
    """Envoie les mises a jour au serveur Web local de la tablette"""
    try:
        pc_ip = get_local_ip()
        url = "http://" + pc_ip + ":9091/update"
        
        data = {}
        if user_text is not None:
            data['user'] = repair_mojibake(user_text)
                
        if robot_text is not None:
            data['robot'] = repair_mojibake(robot_text)
                
        if status is not None:
            data['status'] = status
            
        req = urllib2.Request(url)
        req.add_header('Content-Type', 'application/json')
        body = json.dumps(data, ensure_ascii=False)
        if isinstance(body, unicode):
            body = body.encode('utf-8')
        response = urllib2.urlopen(req, body)
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
        self.current_input_language_code = DEFAULT_STT_LANGUAGE_CODE
        self.current_tts_language = DEFAULT_NAOQI_LANGUAGE
        self._pending_recognition_message = None
        self._ai_user_message_count = 0
        
        # Camera : derniere image capturee (mise a jour toutes les CAMERA_INTERVAL s)
        self.last_image = None
        self._camera_thread = None
        self._camera_running = False
        
        # Timer de silence : timestamp de la derniere prise de parole (Pepper ou user)
        # Utilise par les commentaires proactifs pour ne pas interrompre une conversation
        self._last_speech_time = 0.0
        
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
        self.memory.subscribeToEvent("PepperVolumeSet", self.getName(), "onVolumeSet")
        
        # Demarrer la capture camera en arriere-plan
        if CAMERA_ENABLED:
            self._camera_running = True
            self._camera_thread = threading.Thread(target=self._camera_loop)
            self._camera_thread.daemon = True  # S'arrete automatiquement quand le programme quitte
            self._camera_thread.start()
            print(u"[CAM] Thread capture camera demarre (toutes les {}s)".format(CAMERA_INTERVAL))
            
            # Thread des commentaires proactifs sur l'environnement
            if ENV_COMMENT_ENABLED:
                _env_thread = threading.Thread(target=self._env_comment_loop)
                _env_thread.daemon = True
                _env_thread.start()
        
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
        # Arreter le thread camera
        self._camera_running = False
        self.memory.unsubscribe(self.getName())
        print(u"INF: ReceiverModule stopped!")

    def versions(self):
        return "2.0"

    def onAppModeChanged(self, signalName, mode):
        print("[MODE] Changement mode recu depuis tablette : " + str(mode))
        self.app_mode = str(mode)
        
        if self.app_mode not in ["quiz", "quizz"]:
            # Tous les modes SAUF quiz → Pepper ecoute et repond
            #if self.app_mode == "chat":
                # Restaurer l'historique sur la tablette quand on revient en mode chat
                #self.restore_history_to_tablet()
                
            if not self.force_recog_disabled:
                self.listen(True)
        else:
            # MODE QUIZ : couper l'ecoute (le quiz gere sa propre logique)
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
            if self.app_mode not in ["quiz", "quizz"]:
                self.listen(True)

    def onVolumeSet(self, signalName, vol):
        """Recu depuis la tablette via PepperVolumeSet → change le volume du robot."""
        try:
            vol_int = int(float(str(vol)))
            vol_int = max(0, min(100, vol_int))   # clamp 0-100
            audio = ALProxy("ALAudioDevice", self.strNaoIp, ROBOT_PORT)
            audio.setOutputVolume(vol_int)
            print(u"[VOL] Volume change a: {}%".format(vol_int))
        except Exception as e:
            print(u"[VOL] Erreur changement volume: " + str(e))

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

        self.speechRecognition.setLanguage("en-us")
        self.speechRecognition.calibrate()
        self.speechRecognition.setAutoDetectionThreshold(8)
        self.listen(False)

    def listen(self, enable):
        # SECURITE : en mode quiz, jamais activer le micro (le quiz gere sa propre logique)
        if self.app_mode in ["quiz", "quizz"]:
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

    def _parse_recognition_payload(self, message):
        """Accepte l'ancien texte brut et le nouveau JSON STT avec languageCode."""
        message_u = safedecode(message).strip()
        if not message_u.startswith(u"{"):
            return message_u, None

        try:
            payload = json.loads(message_u)
            text = repair_mojibake(payload.get("text", message_u)).strip()
            language_code = payload.get("languageCode")
            if language_code:
                language_code = safedecode(language_code)
            return text, language_code
        except Exception as e:
            print(u"[LANG] Payload STT non JSON, fallback texte brut: " + str(e))
            return message_u, None

    def _map_stt_language_to_naoqi(self, language_code):
        if not language_code:
            return DEFAULT_NAOQI_LANGUAGE
        code = safedecode(language_code).replace(u"_", u"-").lower()
        if code in BCP47_TO_NAOQI_LANGUAGE:
            return BCP47_TO_NAOQI_LANGUAGE[code]
        primary = code.split(u"-")[0]
        return BCP47_TO_NAOQI_LANGUAGE.get(primary, DEFAULT_NAOQI_LANGUAGE)

    def _detect_requested_tts_language(self, message_text):
        normalized_message = u" " + normalize_lang_text(message_text) + u" "
        for naoqi_language, aliases in LANGUAGE_NAME_ALIASES:
            for alias in aliases:
                normalized_alias = normalize_lang_text(alias)
                if not normalized_alias:
                    continue
                if u" " + normalized_alias + u" " in normalized_message:
                    return naoqi_language
                # Langues CJK/arabe/coreen : les separateurs de mots ne sont pas fiables.
                if normalized_alias in normalized_message and any(ord(ch) > 127 for ch in normalized_alias):
                    return naoqi_language
        return None

    def _set_tts_language_for_current_input(self):
        language_code = getattr(self, 'current_input_language_code', DEFAULT_STT_LANGUAGE_CODE)
        naoqi_language = getattr(self, 'current_tts_language', None) or self._map_stt_language_to_naoqi(language_code)
        try:
            self.tts.setLanguage(naoqi_language)
            print(u"[LANG] TTS NAOqi: {} depuis {}".format(naoqi_language, language_code))
            return naoqi_language
        except Exception as e:
            print(u"[LANG] Avertissement: langue '{}' indisponible ({}). Fallback {}.".format(
                naoqi_language, str(e), DEFAULT_NAOQI_LANGUAGE))
            try:
                self.tts.setLanguage(DEFAULT_NAOQI_LANGUAGE)
            except Exception as e_fr:
                print(u"[LANG] Avertissement: fallback {} impossible: {}".format(DEFAULT_NAOQI_LANGUAGE, str(e_fr)))
            return DEFAULT_NAOQI_LANGUAGE

    def speak(self, text):
        text = repair_mojibake(text)
        # Appliquer les corrections phonetiques AVANT encodage pour le TTS
        text_fixed = apply_tts_fixes(text)
        if isinstance(text_fixed, unicode):
            text_fixed = text_fixed.encode('utf-8')
        
        print(u"[TTS] speak: " + repr(text_fixed[:60]))
        self._last_speech_time = time.time()   # Pepper parle → reset timer de silence
        self.setEyeColor("purple")
        update_tablet_interface(None, text, status="robotspeaking")  # tablette : texte original
        self._set_tts_language_for_current_input()
        self.aup.say(text_fixed)              # TTS : texte avec corrections phonetiques
        self.setEyeColor("green")

    def speak_static(self, text):
        text = repair_mojibake(text)
        text_fixed = apply_tts_fixes(text)
        if isinstance(text_fixed, unicode):
            text_fixed = text_fixed.encode('utf-8')
        
        self.setEyeColor("purple")
        self._set_tts_language_for_current_input()
        self.tts.say(text_fixed)
        self.setEyeColor("green")

    def _dance_motion_fallback(self):
        """Danse simple via controle direct des joints (fallback si aucun behavior n'est installe)."""
        try:
            motion = self.motion
            motion.setStiffnesses("Body", 1.0)
            names = ["LShoulderPitch", "RShoulderPitch", "LElbowRoll", "RElbowRoll"]
            for _ in range(4):   # 4 oscillations bras gauche/droite
                motion.setAngles(names, [-0.5,  0.5, -0.5,  0.5], 0.25)
                time.sleep(0.55)
                motion.setAngles(names, [ 0.5, -0.5,  0.5, -0.5], 0.25)
                time.sleep(0.55)
            # Retour position neutre debout
            motion.setAngles(names, [1.4, 1.4, -0.3, 0.3], 0.3)
            time.sleep(0.5)
            print(u"[DANCE] Fallback ALMotion termine.")
        except Exception as e:
            print(u"[DANCE] Fallback ALMotion echec: " + str(e))

    def dance(self):
        print(u"[DANCE] Tentative de danse...")
        try:
            beh = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            behavior_list = [
                "peppers-date-dance-bis",
                # "animations/Stand/Waiting/FunnyDancer_1",
                # "locomotion-dancebehavior_1",
            ]
            for beh_name in behavior_list:
                try:
                    installed = beh.isBehaviorInstalled(beh_name)
                    print(u"[DANCE] {} - installe: {}".format(beh_name, installed))
                    if installed:
                        print(u"[DANCE] Lancement: " + beh_name)
                        beh.runBehavior(beh_name)
                        print(u"[DANCE] Termine: " + beh_name)
                        return
                except Exception as e_beh:
                    print(u"[DANCE] Echec {}: {}".format(beh_name, str(e_beh)))
            
            # Aucun behavior disponible → fallback ALMotion
            print(u"[DANCE] Aucun behavior installe, utilisation du fallback ALMotion.")
            self._dance_motion_fallback()

        except Exception as e:
            print(u"[DANCE] Erreur generale: " + str(e))
            self._dance_motion_fallback()

    def wave(self):
        try:
            # Initialisation des proxys (assure-toi que strNaoIp et port sont corrects)
            posture = ALProxy("ALRobotPosture", self.strNaoIp, 9559)
            animation = ALProxy("ALAnimationPlayer", self.strNaoIp, 9559)
            
            # 1. Mise en position de base (bras le long du corps)
            posture.goToPosture("StandInit", 0.5)
            
            # 2. Exécution bloquante de l'animation de wave
            animation.run("animations/Stand/Gestures/Hey_1")
            
            # 3. Sécurisation : on force le retour à l'origine
            posture.goToPosture("StandInit", 0.5)
            print(u"[WAVE] Termine - bras redescendu comme a l'origine.")
            
        except Exception as e:
            print(u"[WAVE] Erreur lors de l'animation : " + str(e))

    def laugh(self):
        try:
            beh = ALProxy("ALBehaviorManager", self.strNaoIp, ROBOT_PORT)
            beh.runBehavior("animations/Stand/Emotions/Positive/Laugh_2")
        except Exception as e:
            print(u"[LAUGH] Echec behavior: " + str(e))

    def _do_capture(self):
        """
        Capture une seule image depuis la camera frontale de Pepper.
        Essaie automatiquement plusieurs configurations (colorSpace, resolution).
        Retourne un dict {'raw': base64_str, 'width': int, 'height': int, 'mode': str,
                          'session_lost': bool}
        ou None en cas d'echec.
        Le champ 'session_lost' == True signale un echec temporaire (module destroyed /
        session fermee) : la boucle camera doit retenter rapidement.
        """
        cam_sub_name = "peppervis_bg"
        video = None

        # Strategies a essayer dans l'ordre.
        # Chaque entree : (methode, colorSpace, resolution, cameraIndex, label)
        # methode 'new' = subscribeCamera (NaoQI 2.5+)
        # methode 'old' = subscribe (NaoQI legacy, plus compatible)
        # colorSpace : 13=BGR, 11=RGB
        # resolution : 0=160x120, 1=320x240
        strategies = [
            # --- API ancienne (subscribe) : compatible avec toutes les versions ---
            # ('old', 13, 1, None, "old-API BGR 320x240"),
            # ('old', 11, 1, None, "old-API RGB 320x240"),
            # ('old', 13, 0, None, "old-API BGR 160x120"),
            # --- API nouvelle (subscribeCamera) avec camera 0 (top) puis 1 (bas) ---
            ('new', 13, 1, 0,   "new-API cam0 BGR 320x240"),
            # ('new', 11, 1, 0,   "new-API cam0 RGB 320x240"),
            # ('new', 13, 1, 1,   "new-API cam1 BGR 320x240"),
        ]

        try:
            video = ALProxy("ALVideoDevice", self.strNaoIp, ROBOT_PORT)

            # Nettoyer tous les abonnements residuels connus
            for old_name in [cam_sub_name, cam_sub_name + "_0", cam_sub_name + "_1"]:
                try:
                    video.unsubscribe(old_name)
                except: pass

            session_lost_count = 0  # Compter les erreurs "module destroyed"
            for (method, color_space, resolution, cam_idx, label) in strategies:
                actual_cam_id = None
                try:
                    if method == 'old':
                        # API legacy : subscribe(name, resolution, colorSpace, fps)
                        actual_cam_id = video.subscribe(cam_sub_name, resolution, color_space, 5)
                    else:
                        # API nouvelle : subscribeCamera(name, cameraIndex, resolution, colorSpace, fps)
                        actual_cam_id = video.subscribeCamera(cam_sub_name, cam_idx, resolution, color_space, 5)

                    # subscribeCamera retourne "" en cas d'echec sur certaines versions
                    if not actual_cam_id:
                        print("[CAM] {} : subscribeCamera a retourne vide, on passe".format(label))
                        continue

                    print("[CAM] Essai {} (cam_id='{}')".format(label, actual_cam_id))
                    time.sleep(1.0)  # Laisser le flux s'initialiser

                    nao_image = video.getImageRemote(actual_cam_id)
                    if nao_image is None:
                        # Une seule tentative supplementaire
                        time.sleep(1.0)
                        nao_image = video.getImageRemote(actual_cam_id)

                    try:
                        video.releaseImage(actual_cam_id)
                        video.unsubscribe(actual_cam_id)
                    except: pass

                    if nao_image is None:
                        print("[CAM] {} : getImageRemote toujours None".format(label))
                        continue

                    width  = nao_image[0]
                    height = nao_image[1]
                    if width == 0 or height == 0:
                        print("[CAM] {} : dimensions invalides {}x{}".format(label, width, height))
                        continue

                    print("[CAM] Succes '{}' - image {}x{}".format(label, width, height))

                    raw_data  = bytes(bytearray(nao_image[6]))
                    image_b64 = base64.b64encode(raw_data)
                    if not isinstance(image_b64, str):
                        image_b64 = image_b64.decode('ascii')

                    mode = 'BGR' if color_space == 13 else 'RGB'
                    return {'raw': image_b64, 'width': width, 'height': height, 'mode': mode}

                except Exception as e_strat:
                    err_str = str(e_strat)
                    print("[CAM] Erreur '{}': {}".format(label, err_str))
                    if "module destroyed" in err_str or "Session closed" in err_str:
                        session_lost_count += 1
                    try:
                        if actual_cam_id:
                            video.unsubscribe(actual_cam_id)
                    except: pass

            # Si toutes les erreurs sont "module destroyed" = session temporaire
            if session_lost_count == len(strategies):
                print("[CAM] Session NaoQI perdue (changement de mode ?), reessai rapide.")
                return {'session_lost': True}
            print("[CAM] Toutes les strategies ont echoue. La camera est peut-etre inaccessible depuis le PC.")
            return {'session_lost': True}  # Signal : retenter rapidement

        except Exception as e:
            err_str = str(e)
            print("[CAM] Erreur creation ALVideoDevice: " + err_str)
            # "module destroyed" ou "Session closed" = echec temporaire, retenter vite
            if "module destroyed" in err_str or "Session closed" in err_str or "Cannot connect" in err_str:
                return {'session_lost': True}
            return None

    def _get_env_comment(self):
        """
        Appelle Gemini avec l'image courante pour obtenir un commentaire spontane.
        Retourne une chaine ou None. Retourne 'RIEN' si Gemini juge la scene banale.
        """
        try:
            prompt = (
                u"Observe cette image. "
                u"En tant que Pepper, robot d'accueil chez Veolia, "
                u"fais UNE seule phrase spontanee et naturelle sur ce que tu observes : "
                u"presence d'une personne, objet remarquable, ambiance du lieu, lumiere... "
                u"Reply in English by default (or the language the visitor last spoke). "
                u"Keep it very short (1 sentence max, under 15 words). "
                u"Si rien de notable n'est visible ou si la scene est banale et vide, "
                u"reponds uniquement le mot: RIEN"
            )
            return chatbot.respond(prompt, image_data=self.last_image)
        except Exception as e:
            print(u"[ENV] Erreur _get_env_comment: " + str(e))
            return None

    def _env_comment_loop(self):
        """
        Thread de fond : Pepper fait des observations spontanees sur son environnement.
        Se declenche seulement si Pepper est inactif depuis ENV_COMMENT_MIN_IDLE secondes.
        """
        print(u"[ENV] Thread commentaires proactifs demarre.")
        # Attente initiale : laisser le robot se stabiliser completement
        for _ in range(ENV_COMMENT_INTERVAL * 2):
            if not self._camera_running:
                return
            time.sleep(0.5)

        while self._camera_running:
            try:
                idle_time = time.time() - self._last_speech_time
                mode = getattr(self, 'app_mode', 'menu')
                has_image = self.last_image is not None
                
                # Log de diagnostic toutes les X secondes pour savoir pourquoi ENV ne parle pas
                if not has_image:
                    print(u"[ENV] Pas encore d'image disponible, attente...")
                elif mode in [u"quiz", u"quizz"]:
                    print(u"[ENV] Mode quiz actif, commentaire inhibe.")
                elif self.processing:
                    print(u"[ENV] Traitement en cours (processing=True), commentaire differe.")
                elif idle_time < ENV_COMMENT_MIN_IDLE:
                    print(u"[ENV] Inactif depuis {:.0f}s (min {}s), pas encore.".format(
                        idle_time, ENV_COMMENT_MIN_IDLE))
                else:
                    print(u"[ENV] Conditions OK (idle={:.0f}s) - observation...".format(idle_time))
                    comment = self._get_env_comment()
                    if comment:
                        comment_clean = comment.strip()
                        if comment_clean.upper() != u"RIEN" and len(comment_clean) > 8:
                            safe_print(u"[ENV] >>> Commentaire spontane: " + comment_clean)
                            self._last_speech_time = time.time()
                            # Couper le micro AVANT de parler pour eviter que Pepper
                            # s'entende et se reponde a lui-meme
                            try:
                                self.listen(False)
                            except Exception:
                                pass
                            update_tablet_interface(None, comment_clean)
                            try:
                                self.speak(comment_clean)
                            except Exception as e:
                                print(u"[ENV] Erreur parole spontanee: " + str(e))
                            # Courte pause pour laisser le son se dissiper dans la piece
                            # avant de reactivier le micro (evite l'echo)
                            time.sleep(0.7)
                            if not self.force_recog_disabled and self.app_mode not in ["quiz", "quizz"]:
                                try:
                                    self.listen(True)
                                except Exception:
                                    pass
                        else:
                            print(u"[ENV] Gemini dit RIEN - scene banale, silence conserve.")
                    else:
                        print(u"[ENV] Pas de reponse Gemini.")
            except Exception as e:
                print(u"[ENV] Erreur boucle: " + str(e))

            # Attente fractionnee pour pouvoir s'arreter proprement
            for _ in range(ENV_COMMENT_INTERVAL * 2):
                if not self._camera_running:
                    break
                time.sleep(0.5)
        print(u"[ENV] Boucle commentaires proactifs arretee.")

    def _camera_loop(self):
        """
        Thread de fond : capture une image toutes les CAMERA_INTERVAL secondes
        et la stocke dans self.last_image pour les prochaines reponses Gemini.
        """
        print("[CAM] Boucle camera demarree.")
        # Attendre que le robot soit completement initialise avant la 1ere capture
        for _ in range(10):  # 5 secondes d'attente initiale
            if not self._camera_running:
                return
            time.sleep(0.5)
        print("[CAM] Initialisation terminee, debut des captures.")
        while self._camera_running:
            img = self._do_capture()
            
            if img and not img.get('session_lost'):
                # Capture reussie
                self.last_image = img
                print("[CAM] Image mise a jour en arriere-plan ({}x{})".format(
                    img['width'], img['height']
                ))
                wait_seconds = CAMERA_INTERVAL  # Attente normale entre deux captures
            elif img and img.get('session_lost'):
                # Session temporairement perdue (changement de mode, reconnexion)
                # Retenter rapidement (3s) sans effacer last_image
                print("[CAM] Session perdue (module destroyed), reessai dans 3s...")
                wait_seconds = 3
            else:
                # Echec definitif (camera inaccessible)
                print("[CAM] Echec de capture, prochaine tentative dans {}s".format(CAMERA_INTERVAL))
                wait_seconds = CAMERA_INTERVAL
            
            # Attente fractionnee pour pouvoir s'arreter proprement
            for _ in range(wait_seconds * 2):
                if not self._camera_running:
                    break
                time.sleep(0.5)
        print("[CAM] Boucle camera arretee.")

    def speak_async(self, text):
        text = repair_mojibake(text)
        # Appliquer les corrections phonetiques AVANT encodage
        text_fixed = apply_tts_fixes(text)
        if isinstance(text_fixed, unicode):
            text_fixed = text_fixed.encode('utf-8')
        try:
            self._set_tts_language_for_current_input()
            return self.aup.post.say(text_fixed)
        except Exception as e:
            err_str = str(e)
            # Si la session NaoQI est morte (module destroyed / Socket not connected),
            # le fallback aup.say() plante aussi → on abandonne silencieusement
            if "module destroyed" in err_str or "not connected" in err_str or "Session closed" in err_str:
                print("[WARN] speak_async: session perdue, parole ignoree.")
                return None
            print("Erreur speak_async: ", e)
            try:
                self._set_tts_language_for_current_input()
                self.aup.say(text_fixed)
            except Exception:
                pass
            return None

    def clean_for_speech(self, text):
        import re
        t = repair_mojibake(text)
            
        t = t.replace(u'\n', u' ').replace(u'\r', u' ').replace(u'**', u'').replace(u'*', u'')
        # On garde les accents pour la prononciation francaise !
        # t = t.replace(u'\xc3\x8a', u'e').replace(u'\u00ca', u'e')
        # t = t.replace(u'\u00c0', u'a').replace(u'\u00c9', u'e').replace(u'\u00c8', u'e')
        t = t.replace(u'•', u' ').replace(u'-', u' ')
        
        t = re.sub(ur'\s+', u' ', t).strip()
        return t

    def _trigger_emotion_animation(self):
        """Lance (thread non-bloquant) l'emotion_tag choisi par le LLM lui-meme pour ce tour
        de dialogue (voir oaichat/openaichat.py:respond_stream, qui recoit le catalogue
        tag/description_courte dans son prompt systeme et renvoie {"speech","emotion_tag"}).
        Si emotion_tag est absent/invalide, on ne lance rien : ALAnimatedSpeech (self.aup)
        genere deja un geste de parole neutre standard (bras qui bougent) a chaque say(),
        c'est le fallback par defaut, pas un pool aleatoire d'emotions."""
        try:
            tag = getattr(chatbot, 'last_emotion_tag', None)
            if not animation_selector.is_valid_tag(tag):
                return
            print(u"[ANIM] emotion_tag choisi par le LLM (parallele au TTS): " + tag)
            t_reac = threading.Thread(target=animation_selector.play_animation,
                                       args=(self.strNaoIp, ROBOT_PORT, tag))
            t_reac.daemon = True
            t_reac.start()
        except Exception as e_anim:
            print(u"[ANIM] Erreur lancement emotion_tag: " + str(e_anim))

    def handle_streaming_response(self, input_text, image_data=None, skip_reactive_animation=False):
        full_answer = u""
        sentence_buffer = u""
        print(">> ROBOT streaming...")

        self.setEyeColor("purple")
        update_tablet_interface(None, u"...", status="robotspeaking")
        last_task_id = None
        reactive_triggered = skip_reactive_animation
        first_speech_logged = False

        try:
            for chunk in chatbot.respond_stream(input_text, image_data=image_data):
                chunk = repair_mojibake(chunk)
                full_answer += chunk
                sentence_buffer += chunk

                try:
                    sys.stdout.write(chunk.encode('utf-8'))
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
                    mots_seulement = reg_test.sub(ur'[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0600-\u06ff]', u'', clean_sentence)
                    
                    if len(mots_seulement) > 1:
                        last_task_id = self.speak_async(clean_sentence)
                        if not first_speech_logged:
                            first_speech_logged = True
                            print("[LATENCE] Fin STT -> 1ere reponse parlee: {:.2f}s".format(
                                time.time() - self._last_speech_time))
                        if not reactive_triggered:
                            reactive_triggered = True
                            self._trigger_emotion_animation()

            # Fin du flux (derniers mots restants dans le buffer)
            if sentence_buffer:
                clean_sentence = self.clean_for_speech(sentence_buffer)

                if last_task_id:
                    try:
                        self.aup.wait(last_task_id, 0)
                    except Exception: pass

                import re as reg_test2
                mots_seulement = reg_test2.sub(ur'[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0600-\u06ff]', u'', clean_sentence)

                if len(mots_seulement) > 1:
                    last_task_id = self.speak_async(clean_sentence)
                    if not first_speech_logged:
                        first_speech_logged = True
                        print("[LATENCE] Fin STT -> 1ere reponse parlee: {:.2f}s".format(
                            time.time() - self._last_speech_time))
                    if not reactive_triggered:
                        reactive_triggered = True
                        self._trigger_emotion_animation()

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
            err_str = repr(e)
            print("Stream error: ", err_str)
            # Si la session NaoQI est morte, ne pas essayer de speak() (plante aussi)
            session_dead = any(k in err_str for k in [
                "module destroyed", "not connected", "Session closed", "Socket is not"
            ])
            if not session_dead:
                try:
                    self.speak("Sorry, I had a technical problem.")
                except Exception:
                    pass
            
        finally:
            self.setEyeColor("white")
            update_tablet_interface(None, None, status="waiting")
            try:
                self.speechRecognition.pause()
            except: pass
            
            time.sleep(0.2)
            self.processing = False
            
            if hasattr(self, 'app_mode'):
                if self.app_mode not in ["quiz", "quizz"] and getattr(self, 'force_recog_disabled', False) == False:
                    self.listen(True)
            else:
                self.listen(True)

    def processRemote(self, signalName, message):
        safe_print("DEBUG_RAW_RECEIVE: Signal: {} Content: {}".format(signalName, message))
        
        # Bloquer uniquement en mode quiz ; tous les autres modes → on traite
        if self.app_mode in ["quiz", "quizz"]:
            return

        if self.processing:
            if message is not None and message != "None" and message != "<error>":
                self._pending_recognition_message = message
                print("Message mis en attente car deja en traitement.")
            else:
                print("Message ignore car deja en traitement.")
            return

        if message is None or message == "None" or message == "<error>":
            if not self.force_recog_disabled:
                self.listen(True)
            return

        self.processing = True
        
        try:
            message_str, language_code = self._parse_recognition_payload(message)
            if language_code:
                self.current_input_language_code = language_code
                print(u"[LANG] Langue STT detectee: " + language_code)
            else:
                self.current_input_language_code = DEFAULT_STT_LANGUAGE_CODE
            requested_tts_language = self._detect_requested_tts_language(message_str)
            if requested_tts_language:
                self.current_tts_language = requested_tts_language
                print(u"[LANG] Langue demandee explicitement: " + requested_tts_language)
            else:
                self.current_tts_language = self._map_stt_language_to_naoqi(self.current_input_language_code)
            if len(message_str.strip()) == 0:
                self.processing = False
                if not self.force_recog_disabled:
                    self.listen(True)
                return
                
            self.log.write(u"INP: " + message_str + u"\n")
            self.listen(False)
            safe_print(u"USER: " + message_str)
            self._last_speech_time = time.time()  # L'user parle → reset timer de silence

            self._ai_user_message_count += 1
            
            # Ajout a l'historique local
            self.history.append({'role': 'user', 'text': message_str})
            
            update_tablet_interface(message_str, None, status="waiting")
            
            if message_str == u"<error>":
                self.misunderstandings += 1
                if self.misunderstandings == 1:
                    answer = u"I didn't catch that, could you repeat?"
                elif self.misunderstandings == 2:
                    answer = u"Sorry, I still didn't understand. Could you say it once more?"
                else:
                    answer = u"I'm having trouble understanding today, sorry."
                
                print(u"ERREUR, REPONSE PAR DEFAUT: " + answer)
                update_tablet_interface(None, answer)
                self.speak(answer)
            else:
                self.misunderstandings = 0
                message_lower = message_str.lower()
                ai_input = message_str
                if requested_tts_language:
                    ai_input = message_str + u"\n\nSystem instruction: reply only in " + requested_tts_language + u"."
                else:
                    # Renforce la langue detectee par le STT au plus pres de la generation (voir
                    # oaichat/openaichat.py:LANGUAGE_PRIORITY_INSTRUCTION) : sans ce hint par tour,
                    # le LLM doit deviner la langue depuis le seul texte utilisateur, ce qui echoue
                    # par intermittence une fois le prompt systeme alourdi par le catalogue
                    # d'animations (voir tests de la PR).
                    ai_input = message_str + u"\n\n(Detected language: {}. Reply in that language; if unsure, reply in English.)".format(
                        self.current_tts_language)

                # L'image n'est envoyee a Gemini QUE si l'utilisateur demande explicitement
                # une description visuelle. Sinon Gemini decrit l'environnement sur chaque
                # message meme quand c'est hors-sujet (ex: "Spotify", "volume 50").
                normalized_for_vision = normalize_lang_text(message_str)
                VISION_KEYWORDS = [
                    u"vois tu", u"tu vois", u"regarde", u"regardes",
                    u"autour", u"devant toi", u"environnement",
                    u"qu est ce que tu vois", u"ce que tu vois",
                    u"what do you see", u"describe what you see",
                    u"montre", u"camera", u"caméra", u"image", u"photo",
                    u"qu est ce que je tiens", u"qu est ce que c est",
                    u"quel objet", u"quelle couleur",
                ]
                wants_vision = any(normalize_lang_text(kw) in normalized_for_vision for kw in VISION_KEYWORDS)
                
                image_data = None  # Par defaut : pas d'image
                if wants_vision:
                    # Capture immediate pour avoir l'image la plus recente possible
                    print("[CAM] Demande vision explicite - capture immediate")
                    image_data = self._do_capture()
                    if image_data:
                        self.last_image = image_data
                    elif self.last_image:
                        # Si la capture echoue, utiliser la derniere image connue
                        image_data = self.last_image
                        print("[CAM] Capture echouee, utilisation de la derniere image connue")
                
                if image_data:
                    print("[CAM] Image incluse dans la reponse Gemini ({}x{})".format(
                        image_data['width'], image_data['height']
                    ))
                
                if u"danse" in message_lower or u"dance" in message_lower or u"danser" in message_lower:
                    safe_print(u"[DANCE] Mot-cle detecte dans: " + message_lower)
                    answer = u"I'm dancing for you!"
                    update_tablet_interface(None, answer)
                    try:
                        self.speak(answer)
                    except Exception as e_spk:
                        print(u"[DANCE] Erreur speak: " + str(e_spk))
                    self.dance()
                elif (u"serre" in message_lower and u"main" in message_lower) or (u"shake" in message_lower and u"hand" in message_lower):
                    answer = u"I can't shake hands, but I can wave at you."
                    update_tablet_interface(None, answer)
                    # Wave en thread pour qu'il demarre en meme temps que la parole
                    t_wave = threading.Thread(target=self.wave)
                    t_wave.daemon = True
                    t_wave.start()
                    try:
                        self.speak(answer)
                    except Exception as e_spk:
                        print(u"[WAVE] Erreur speak: " + str(e_spk))
                elif u"blague" in message_lower or u"rigole" in message_lower or u"rire" in message_lower or u"joke" in message_lower or u"laugh" in message_lower:
                    self.handle_streaming_response(ai_input, image_data=image_data, skip_reactive_animation=True)
                    self.laugh()
                elif u"bonjour" in message_lower or u"salut" in message_lower or u"hello" in message_lower or u"hi " in message_lower or message_lower.strip() in (u"hi", u"hey"):
                    # Geste coucou SIMULTANE a la parole (thread daemon)
                    t_wave = threading.Thread(target=self.wave)
                    t_wave.daemon = True
                    t_wave.start()
                    self.handle_streaming_response(ai_input, image_data=image_data, skip_reactive_animation=True)
                else:
                    # Les demandes explicites d'animation (ex: "montre tes muscles", "chante
                    # joyeux anniversaire") et les reactions emotionnelles au contenu du message
                    # sont desormais choisies ensemble par le LLM, dans le meme appel Gemini que
                    # la reponse parlee, quelle que soit la langue (voir
                    # oaichat/openaichat.py:respond_stream). _trigger_emotion_animation lance
                    # l'animation correspondante des que la 1ere phrase est prete a etre dite.
                    self.handle_streaming_response(ai_input, image_data=image_data)
                    
        except Exception as e_main:
            # Capturer toutes les exceptions non gerees pour eviter un crash silencieux
            print(u"[ERREUR processRemote] Exception non geree: " + repr(e_main))
            try:
                self.speak(u"Sorry, I had a problem. Could you say that again?")
            except Exception:
                pass
        finally:
            self.processing = False
            if getattr(self, '_ai_user_message_count', 0) >= 5:
                try:
                    chatbot.reset()
                    print(u"[AI] Historique Gemini vide apres 5 messages utilisateur.")
                except Exception as e_reset:
                    print(u"[AI] Reset historique Gemini impossible: " + str(e_reset))
                self._ai_user_message_count = 0
            if self.app_mode not in ["quiz", "quizz"] and not self.force_recog_disabled:
                self.listen(True)
            pending_message = self._pending_recognition_message
            self._pending_recognition_message = None
            if pending_message is not None and self.app_mode not in ["quiz", "quizz"]:
                print("Traitement du message mis en attente.")
                self.processRemote(signalName, pending_message)

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
