# -*- coding: utf-8 -*-
import sys
import os
import time
import socket
import threading
import argparse
import urllib
import random
import json
import traceback

# Gestion compatibilite Python 2 / Python 3
try:
    import BaseHTTPServer
    import SocketServer
except ImportError:
    import http.server as BaseHTTPServer
    import socketserver as SocketServer

# Patch performance Windows
def not_insane_address_string(self):
    host, port = self.client_address[:2]
    return '%s' % host
BaseHTTPServer.BaseHTTPRequestHandler.address_string = not_insane_address_string

# Import SDK NAOqi
try:
    import qi
except ImportError:
    print("ERREUR: Module 'qi' introuvable.")
    qi = None

# Fallback : naoqi ALProxy (Python 2.7 uniquement, plus fiable pour certains services)
_ALProxy = None
try:
    import sys as _sys
    _sys.path.insert(0, r"C:\Users\thoma\pynaoqi-python2.7-2.5.7.1-win32-vs2013\lib")
    from naoqi import ALProxy as _ALProxy
    print("[NAOQI] naoqi.ALProxy disponible.")
except ImportError:
    print("[NAOQI] naoqi.ALProxy non disponible (Python 3 ou chemin manquant).")

# IP du robot - sera renseignee au demarrage via args
ROBOT_IP_GLOBAL = None

PORT = 9091
WIFI_SSID = "Bbox-0283B47E"
WIFI_PASSWORD = "4SDf7LzcJfsJT3hRXz"
WIFI_SECURITY = "WPA2"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

def _load_client_config():
    config_path = os.path.join(SCRIPT_DIR, "client.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except TypeError:
        try:
            with open(config_path, "r") as f:
                return json.loads(f.read().decode("utf-8"))
        except Exception as e:
            print("[CONFIG] Impossible de charger client.json: " + str(e))
    except Exception as e:
        print("[CONFIG] Impossible de charger client.json: " + str(e))
    return {}

CLIENT_CONFIG = _load_client_config()
PY2 = sys.version_info[0] < 3

def cfg_get(path, default=None):
    cur = CLIENT_CONFIG
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur

def html_text(value):
    """Retourne une chaine compatible avec les templates HTML Python 2/3."""
    if value is None:
        return ""
    if PY2:
        if isinstance(value, unicode):
            return value.encode("utf-8")
        return str(value)
    return str(value)

QUESTIONS = [
    {
        "text": "Que peux-tu faire à l'atelier parfums ?",
        "answers": ["Créer un parfum", "Construire un robot", "Faire du sport", "Cuisiner"],
        "correct": 0,
        "good": "Bravo ! Tu es un créateur du futur !",
        "bad": ["", "Pas ici, mais bonne idée !", "Presque, mais non !", "Miam ! Mais ce n'est pas ici"]
    },
    {
        "text": "Pourquoi faut-il protéger sa peau ?",
        "answers": ["Contre le soleil", "Pour dormir", "Pour courir", "Pour jouer"],
        "correct": 0,
        "good": "Exact ! Tu es un expert !",
        "bad": ["", "Pas vraiment", "Non plus !", "Pas exactement !"]
    },
    {
        "text": "Que permet l'intelligence artificielle ?",
        "answers": ["Créer et inventer", "Dormir", "Manger", "Disparaître"],
        "correct": 0,
        "good": "Bravo ! Tu es prêt pour le futur !",
        "bad": ["", "Non", "Pas encore !", "Impossible !"]
    },
    {
        "text": "Où peux-tu jouer librement ?",
        "answers": ["Fun Zone", "Zone Zen", "Atelier peau", "Accueil"],
        "correct": 0,
        "good": "Oui !! Amuse-toi bien !",
        "bad": ["", "Là on se détend", "On apprend ici !", "On commence ici !"]
    },
    {
        "text": "Que fait un scientifique ?",
        "answers": ["Il expérimente", "Il dort", "Il joue", "Il chante"],
        "correct": 0,
        "good": "Exact ! Comme toi aujourd'hui !",
        "bad": ["", "Non", "Parfois... mais pas tout le temps !", "Pourquoi pas !"]
    }
]
def _fix_quiz_value(value):
    """Convertit recursivement les unicode issus de client.json en str utf-8 (Python 2),
    pour eviter un crash 'ascii codec can't decode' quand ces valeurs sont
    concatenees avec les fragments HTML (str) dans render_quiz()."""
    if isinstance(value, list):
        return [_fix_quiz_value(v) for v in value]
    if isinstance(value, dict):
        return dict((k, _fix_quiz_value(v)) for k, v in value.items())
    if PY2 and isinstance(value, unicode):
        return value.encode("utf-8")
    return value

CONFIG_QUIZ = cfg_get("quiz", None)
if CONFIG_QUIZ:
    QUESTIONS = _fix_quiz_value(CONFIG_QUIZ)

QUIZ_END_TEXT = (
    "Analyse des résultats... bip bip... "
    "Mission réussie ! "
    "Bravo, tu es prêt pour inventer la beauté du futur ! "
    "À bientôt petit inventeur !"
)
QUIZ_END_TEXT = html_text(cfg_get("quizEndText", QUIZ_END_TEXT))

class GameState:
    def __init__(self):
        self.quiz_index = 0
        self.quiz_score = 0
        self.chat_user = ""
        self.chat_robot = "Bonjour !"
        self.chat_status = "waiting"

    def reset_quiz(self):
        self.quiz_index = 0
        self.quiz_score = 0

state = GameState()
session_global = None

THEME_PRIMARY = html_text(cfg_get("theme.primary", "#18C6D9"))
THEME_SECONDARY = html_text(cfg_get("theme.secondary", "#18C6D9"))
THEME_BACKGROUND = html_text(cfg_get("theme.background", "#1F365C"))
THEME_SURFACE = html_text(cfg_get("theme.surface", "#ECF4F8"))
THEME_TEXT_SURFACE = html_text(cfg_get("theme.textOnSurface", "#1A1A1A"))
THEME_TEXT_BACKGROUND = html_text(cfg_get("theme.textOnBackground", "#FFFFFF"))
THEME_OVERLAY = html_text(cfg_get("theme.overlay", THEME_BACKGROUND))
CLIENT_LOGO = html_text(cfg_get("client.logo", "/images/EvotionLogo.png"))
HOME_GREETING = html_text(cfg_get("home.greeting", "Salut ! Je suis Pepper,\nPrêt à apprendre et jouer avec toi"))
CHAT_TITLE = html_text(cfg_get("home.chatTitle", "DISCUSSION AVEC PEPPER"))
CHAT_PLACEHOLDER = html_text(cfg_get("home.chatPlaceholder", "Parlez à Pepper pour démarrer la discussion..."))
STATUS_LISTENING_TEXT = html_text(cfg_get("status.listening", "Vous pouvez parler !"))
STATUS_SPEAKING_TEXT = html_text(cfg_get("status.speaking", "🔊 Attendez, c'est au tour de Pepper de parler"))
STATUS_WAITING_TEXT = html_text(cfg_get("status.waiting", "Veuillez patienter"))

PEPPER_ANIMATIONS = cfg_get("interactions", None) or [
    {"id": "wave", "label": "Coucou", "icon": "👋", "say": "Coucou !"},
    {"id": "dance", "label": "Danse", "icon": "🕺", "say": "Regardez ma petite danse !"},
    {"id": "laugh", "label": "Rire", "icon": "😁", "say": "Ha ha ha !"},
]
for _anim in PEPPER_ANIMATIONS:
    if "id" not in _anim and "animationId" in _anim:
        _anim["id"] = _anim["animationId"]
    _anim["id"] = html_text(_anim.get("id", ""))
    _anim["label"] = html_text(_anim.get("label", _anim["id"]))
    _anim["icon"] = html_text(_anim.get("icon", "?"))
    if "say" in _anim:
        _anim["say"] = html_text(_anim["say"])

PEPPER_ANIMATION_PATHS = {
    "wave": [
        "animations/Stand/Gestures/Hey_1",
        "animations/Stand/Gestures/Hey_2",
    ],
    "dance": [
        "peppers-date-dance-bis",
    ],
    "laugh": [
        "animations/Stand/Emotions/Positive/Laugh_1",
        "animations/Stand/Emotions/Positive/Happy_1",
    ],
}

PEPPER_ANIMATION_BY_ID = {}
for _anim in PEPPER_ANIMATIONS:
    PEPPER_ANIMATION_BY_ID[_anim["id"]] = _anim

# Fonction globale pour gerer l'etat de l'IA proprement
def set_app_mode(mode):
    global session_global
    if session_global:
        try:
            session_global.service("ALMemory").raiseEvent("PepperAppMode", str(mode))
        except:
            pass

HEADER_HTML = """
<a href="/menu"><img class="top-logo" src="__CLIENT_LOGO__" onerror="this.style.display='none'"></a>
<div class="hamburger" onclick="toggleVolumeOverlay()">
    <span></span><span></span><span></span>
</div>

<div id="volume-overlay" class="side-overlay" style="display:none;">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:28px;">
        <div style="font-size:34px; letter-spacing:8px; color:#FFFFFF;">MENU</div>
        <div onclick="toggleVolumeOverlay()" style="font-size:42px; line-height:42px; color:#9aa8b8; cursor:pointer;">×</div>
    </div>
    <div class="side-section-title">
        <span style="height:1px; background:#126273; flex:1;"></span>
        <span style="padding:0 14px;">NAVIGATION</span>
        <span style="height:1px; background:#126273; flex:1;"></span>
    </div>
    <a class="side-nav active" href="/menu"><span>🏠</span><b>Accueil</b><i>•</i></a>
    <a class="side-nav" href="/quiz/start"><span>🎯</span><b>Quiz</b></a>
    <a class="side-nav" href="/animations"><span>🎭</span><b>Interactions</b></a>
    <a class="side-nav" href="/veolia/presentation1.html"><span>📖</span><b>Veolia</b></a>
    <div class="side-section-title">
        <span style="height:1px; background:#126273; flex:1;"></span>
        <span style="padding:0 14px;">ROBOT</span>
        <span style="height:1px; background:#126273; flex:1;"></span>
    </div>
    <div class="side-card side-card-compact">
        <div class="side-info-row"><span class="side-pill">🔋</span><b>Batterie</b><strong id="battery-display">...</strong></div>
    </div>
    <div class="side-section-title">
        <span style="height:1px; background:#126273; flex:1;"></span>
        <span style="padding:0 14px;">SON</span>
        <span style="height:1px; background:#126273; flex:1;"></span>
    </div>
    <div class="side-card side-card-compact">
        <label class="side-check"><input type="checkbox" id="mute-robot" onchange="toggleMute()"> <span>Couper le son du robot</span></label>
        <label class="side-check"><input type="checkbox" id="mute-recog" onchange="toggleRecog()"> <span>Désactiver la reconnaissance vocale</span></label>
        <div style="display:flex; align-items:center; justify-content:center; margin-top:12px;">
            <div onclick="changeVolume(-5)" class="vol-btn">-</div>
            <div id="vol-display" style="font-size:22px; font-weight:bold; margin:0 14px; min-width:46px; text-align:center;">70</div>
            <div onclick="changeVolume(5)" class="vol-btn">+</div>
        </div>
    </div>
    <div class="side-footer">Pepper</div>
</div>

<script>
var _volOverlayOpen = false;
function toggleVolumeOverlay() {
    _volOverlayOpen = !_volOverlayOpen;
    var el = document.getElementById('volume-overlay');
    el.style.display = _volOverlayOpen ? 'flex' : 'none';
    if (_volOverlayOpen) refreshRobotStatus();
}
function _sendVol(vol) {
    var img = new Image();
    img.src = '/setvolume?v=' + vol + '&_=' + Date.now();
}
function changeVolume(delta) {
    var volEl = document.getElementById('vol-display');
    var current = parseInt(volEl.innerText) || 70;
    var newVol = Math.max(0, Math.min(100, current + delta));
    volEl.innerText = newVol;
    _sendVol(newVol);
}
function toggleMute() {
    var muted = document.getElementById('mute-robot').checked;
    var vol = muted ? 0 : (parseInt(document.getElementById('vol-display').innerText) || 70);
    _sendVol(vol);
}
function toggleRecog() {
    var disabled = document.getElementById('mute-recog').checked;
    var img = new Image();
    img.src = '/setrecog?d=' + (disabled ? '1' : '0') + '&_=' + Date.now();
}
function refreshRobotStatus() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/robotstatus?t=' + Date.now(), true);
    xhr.onreadystatechange = function() {
        if (xhr.readyState == 4 && xhr.status == 200) {
            try {
                var data = JSON.parse(xhr.responseText);
                var battery = document.getElementById('battery-display');
                var connection = document.getElementById('connection-display');
                var volume = document.getElementById('vol-display');
                if (battery) battery.innerText = data.battery;
                if (connection) {
                    connection.innerText = data.connected ? 'OK' : 'Hors ligne';
                    connection.style.color = data.connected ? '#63e6be' : '#ff7f9a';
                }
                if (volume && data.volume !== null) volume.innerText = data.volume;
            } catch(e) {}
        }
    };
    xhr.send();
}
</script>
""".replace("__THEME_OVERLAY__", THEME_OVERLAY).replace("__CLIENT_LOGO__", CLIENT_LOGO).replace("__THEME_PRIMARY__", THEME_PRIMARY)

COMMON_CSS = (
"<style>:root{"
"--primary:" + THEME_PRIMARY + ";"
"--secondary:" + THEME_SECONDARY + ";"
"--background:" + THEME_BACKGROUND + ";"
"--surface:" + THEME_SURFACE + ";"
"--text-surface:" + THEME_TEXT_SURFACE + ";"
"--text-background:" + THEME_TEXT_BACKGROUND + ";"
"--overlay:" + THEME_OVERLAY + ";"
"}</style>"
"""
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; text-align: center; background: """ + THEME_BACKGROUND + """; background: var(--background); margin: 0; padding: 0; color: """ + THEME_TEXT_BACKGROUND + """; color: var(--text-background); -webkit-user-select: none; overflow: hidden; width: 100%; height: 100vh; position: fixed; }
    h1 { color: """ + THEME_PRIMARY + """; color: var(--primary); font-size: clamp(28px, 4vw, 44px); margin: 16px 0; text-shadow: none; text-transform: uppercase; letter-spacing: 3px; }
    .container { width: 100%; height: 100vh; margin: 0 auto; padding-top: 80px; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; overflow: hidden; }
    .btn { display: inline-block; display: inline-flex; align-items: center; justify-content: center; background: """ + THEME_SURFACE + """; background: var(--surface); border: 2px solid """ + THEME_PRIMARY + """; border-radius: 26px; padding: 15px 30px; margin: 10px; font-size: 20px; color: """ + THEME_BACKGROUND + """; color: var(--background); text-decoration: none; box-shadow: 0 10px 28px rgba(0,0,0,0.2); cursor: pointer; font-weight: bold; transition: transform 0.1s; }
    .btn:active { transform: scale(0.95); background: #dcecf2; }
    .btn-green { background: #2ecc71; color: white; }
    .btn-red { background: #e74c3c; color: white; }
    .btn-menu { width: 150px; height: 120px; padding: 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 2px; flex-direction: column; }
    .menu-cards .btn-menu { width: 24vh; height: 24vh; padding: 1.5vh; font-size: 2.3vh; letter-spacing: 0.3vh; border-radius: 3.2vh; }
    .menu-cards .btn-menu .icon { font-size: 38px; -webkit-transform: scale(1.6); transform: scale(1.6); margin: 1.5vh 0 3.2vh; }
    .menu-cards .btn-menu .icon-img { max-width: 8vh; max-height: 8vh; margin-bottom: 2.2vh; }
    .btn-menu span { display: block; }
    .btn-menu .icon { font-size: 38px; line-height: 1; margin-bottom: 10px; }
    .btn-menu .icon-img { display:block; max-width:42px; max-height:42px; margin:0 auto 10px; object-fit:contain; }
    
    .chat-container { display: flex; flex-direction: column; gap: 15px; padding: 18px; width: 100%; flex: 1; min-height: 0; overflow-y: auto; background: """ + THEME_SURFACE + """; background: var(--surface); border-radius: 0 0 30px 30px; margin-bottom: 10px; box-sizing: border-box; }
    .bubble { padding: 15px; border-radius: 18px; background: #ffffff; color: """ + THEME_BACKGROUND + """; color: var(--background); font-size: 18px; text-align: left; box-shadow: 0 3px 10px rgba(0,0,0,0.08); position: relative; font-weight: bold; }
    .user-bubble { align-self: flex-end; margin-left: 20%; border: 1px solid rgba(0,0,0,0.05); }
    .robot-bubble { align-self: flex-start; margin-right: 20%; text-align: left; background: """ + THEME_SECONDARY + """; background: var(--secondary); color: white; }
    .status-bar { padding: 12px 16px; font-size: clamp(13px, 1.5vw, 16px); font-weight: bold; color: white; background: """ + THEME_SURFACE + """; margin: 10px 18px 18px; width: auto; flex-shrink: 0; }
    .status-listening { color: #00b864; }
    .status-speaking { color: #8e24aa; }
    .status-waiting { color: #333; }
    .top-logo { position: fixed; top: 28px; left: 24px; z-index: 1100; height: 9vh; max-width: 200px; object-fit: contain; opacity: 0.95; }
    .hamburger { position: fixed; top: 22px; right: 24px; z-index: 1100; width: 34px; height: 26px; display: flex; flex-direction: column; justify-content: space-between; cursor: pointer; }
    .hamburger span { display: block; height: 4px; background: """ + THEME_BACKGROUND + """; border-radius: 99px; margin-bottom: 2px; }
    .side-overlay { position:fixed; top:0; right:0; width:320px; max-width:88vw; height:100%; max-height:100vh; background:""" + THEME_OVERLAY + """; background:var(--overlay); z-index:2000; color:white; flex-direction:column; padding:24px 20px 14px; box-sizing:border-box; box-shadow:-16px 0 34px rgba(0,0,0,0.28); overflow-y:auto; overflow-x:hidden; -webkit-overflow-scrolling:touch; }
    .side-section-title { display:flex; align-items:center; color:#FFFFFF; letter-spacing:4px; font-size:13px; margin:18px 0 12px; flex-shrink:0; }
    .side-nav { display:flex; align-items:center; height:48px; padding:0 14px; margin:8px 0; color:#c6d1dc; text-decoration:none; border-radius:14px; font-size:17px; box-sizing:border-box; flex-shrink:0; }
    .side-nav.active { background:""" + THEME_PRIMARY + """; color:white; box-shadow:0 8px 20px rgba(0,0,0,0.22); }
    .side-nav span { width:38px; font-size:22px; text-align:left; }
    .side-nav b { flex:1; text-align:left; }
    .side-nav i { font-style:normal; font-size:26px; opacity:0.85; }
    .side-card { background:rgba(236,244,248,0.10); border-radius:16px; padding:14px 16px; color:#dce6ee; text-align:left; flex-shrink:0; }
    .side-card-compact { padding:12px 14px; }
    .side-info-row { display:flex; align-items:center; min-height:32px; margin:6px 0; }
    .side-pill { display:inline-flex; align-items:center; justify-content:center; width:36px; height:24px; margin-right:10px; border-radius:8px; background:rgba(236,244,248,0.14); color:""" + THEME_PRIMARY + """; color:var(--primary); font-size:11px; font-weight:800; letter-spacing:1px; }
    .side-card b { flex:1; font-size:17px; font-weight:600; }
    .side-card strong { font-size:17px; }
    .side-check { display:flex; align-items:center; font-size:15px; line-height:1.2; margin:10px 0; color:#dce6ee; }
    .side-check input { width:22px; height:22px; margin:0 10px 0 0; flex:0 0 auto; }
    .side-check span { flex:1; }
    .vol-btn { width:40px; height:40px; line-height:40px; border-radius:50%; background:""" + THEME_SURFACE + """; color:""" + THEME_BACKGROUND + """; text-align:center; font-size:28px; font-weight:bold; cursor:pointer; flex:0 0 auto; }
    .side-footer { margin:18px 0 4px; text-align:center; opacity:0.25; flex-shrink:0; }
    .surface-panel { background: """ + THEME_SURFACE + """; background: var(--surface); color: """ + THEME_TEXT_SURFACE + """; color: var(--text-surface); border-radius: 30px; box-shadow: 0 16px 36px rgba(0,0,0,0.22); }
    .app-layout { width: 100%; height: 100vh; display: flex; overflow: hidden; }
    .app-main { flex: 1; min-width: 0; height: 100vh; position: relative; box-sizing: border-box; }
    .menu-layout { width: 100%; height: 100%; box-sizing: border-box; padding: 14vh 3vw 4vh; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-align: center; -webkit-align-items: center; align-items: center; -webkit-justify-content: space-around; justify-content: space-around; }
    .robot-zone { position: relative; height: 100%; -webkit-flex: 0 1 auto; flex: 0 1 auto; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-orient: vertical; -webkit-flex-direction: column; flex-direction: column; -webkit-box-align: center; -webkit-align-items: center; align-items: center; -webkit-justify-content: center; justify-content: center; }
    .robot-zone img { height: 64vh; max-width: 42vw; object-fit: contain; display: block; }
    .welcome-bubble { position: absolute; top: 18px; left: 0; background: #ffffff; color: """ + THEME_BACKGROUND + """; color: var(--background); border-radius: 18px; padding: 14px 18px; max-width: 250px; text-align: left; font-size: 15px; box-shadow: 0 6px 18px rgba(0,0,0,0.16); white-space: normal; }
    .welcome-bubble:after { content: ''; position: absolute; right: 22px; bottom: -14px; border-width: 14px 12px 0 0; border-style: solid; border-color: #ffffff transparent transparent transparent; }
    .robot-zone .welcome-bubble { position: relative; top: auto; left: auto; -webkit-align-self: flex-start; align-self: flex-start; max-width: 36vw; font-size: 2.4vh; padding: 1.8vh 2.4vh; border-radius: 2.6vh; margin-bottom: 3vh; }
    .menu-cards { width: 52vh; -webkit-flex: 0 0 auto; flex: 0 0 auto; font-size: 0; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-flex-wrap: wrap; flex-wrap: wrap; -webkit-justify-content: space-between; justify-content: space-between; }
    .menu-cards .btn-menu { box-sizing: border-box; margin: 0 0 4vh 0; }
    .chat-shell {
        width: 30vw;
        width: clamp(280px, 30vw, 560px);
        height: 100vh;
        flex: 0 0 30vw;
        flex: 0 0 clamp(280px, 30vw, 560px);
        background: """ + THEME_SURFACE + """;
        background: var(--surface);
        box-shadow: -18px 0 34px rgba(0,0,0,0.24);
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }

    .bubble {
        padding: 15px; 
        border-radius: 18px;
        background: #ffffff; 
        color: """ + THEME_BACKGROUND + """;
        color: var(--background);
        font-size: 18px; 
        text-align: left;
        box-shadow: 0 3px 10px rgba(0,0,0,0.08);
        position: relative; 
        font-weight: bold;
        word-wrap: break-word;
        max-width: 90%;
    }
    .chat-title { min-height: 58px; min-height: 9vh; padding: 0 76px 0 22px; display:flex; align-items:center; justify-content:center; color: """ + THEME_PRIMARY + """; color: var(--primary); font-size: 18px; font-size: clamp(15px, 1.3vw, 26px); font-weight: 800; letter-spacing: 2px; text-transform: uppercase; border-bottom: 1px solid rgba(0,0,0,0.08); flex-shrink: 0; box-sizing: border-box; }
    .chat-placeholder { flex: 1; display: flex; align-items: center; justify-content: center; color: rgba(75,75,75,0.6); font-style: italic; padding: 22px; }
    .animations-main { padding: clamp(76px, 11vh, 110px) clamp(22px, 4vw, 50px) 28px; box-sizing:border-box; display:flex; align-items:center; justify-content:center; }
    .animations-panel { width:min(760px, 82%); max-height:86vh; overflow-y:auto; padding: clamp(24px, 5vh, 36px) clamp(24px, 4vw, 34px) clamp(28px, 5vh, 42px); margin:0 auto; box-sizing:border-box; }
    .animations-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: clamp(14px, 3vh, 22px); margin-top:18px; justify-items:center; }
    .back-menu { position:fixed; top:82px; top:calc(38px + 9vh); left:24px; margin:0; padding:10px 20px; font-size:14px; z-index: 1110; }
    @media (max-width: 900px) {
        .menu-layout { padding-left: 18px; padding-right: 18px; }
        .chat-shell { width: 31vw; flex-basis: 31vw; }
        .menu-cards { width: 26vw; }
        .menu-cards .btn-menu { width: 12.5vw; height: 12.5vw; font-size: 1.5vw; }
        .robot-zone img { max-width: 34vw; }
    }
</style>
""")

CHAT_POLL_SCRIPT = """
<script>
var lastStatus = '';
var STATUS_LISTENING_TEXT = "__STATUS_LISTENING__";
var STATUS_SPEAKING_TEXT = "__STATUS_SPEAKING__";
var STATUS_WAITING_TEXT = "__STATUS_WAITING__";
var MAX_CHAT_BUBBLES = 4;
function trimChatHistory(container) {
  if (!container) return;
  var bubbles = [];
  for (var i = 0; i < container.childNodes.length; i++) {
    var node = container.childNodes[i];
    if (node.nodeType === 1 && node.className && node.className.indexOf('bubble') !== -1) {
      bubbles.push(node);
    }
  }
  while (bubbles.length > MAX_CHAT_BUBBLES) {
    var old = bubbles.shift();
    if (old && old.parentNode) old.parentNode.removeChild(old);
  }
}
function appendBubble(className, html) {
  var container = document.getElementById('chat-container');
  if (!container) return;
  var placeholder = document.getElementById('chat-placeholder');
  if (placeholder) placeholder.style.display = 'none';
  var div = document.createElement('div');
  div.className = className;
  div.innerHTML = html;
  container.appendChild(div);
  trimChatHistory(container);
  container.scrollTop = container.scrollHeight;
}
function startPolling() {
  setInterval(function() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/poll?t=' + new Date().getTime(), true);
    xhr.onreadystatechange = function() {
      if (xhr.readyState == 4 && xhr.status == 200) {
        try {
          var data = JSON.parse(xhr.responseText);
          var container = document.getElementById('chat-container');
          if (data.user && data.user !== '') appendBubble('bubble user-bubble', data.user);
          if (data.robot && data.robot !== '') {
            var lastChild = container ? container.lastChild : null;
            while (lastChild && lastChild.nodeType !== 1) { lastChild = lastChild.previousSibling; }
            if (lastChild && lastChild.className && lastChild.className.indexOf('robot-bubble') !== -1) {
                lastChild.innerHTML = data.robot;
                trimChatHistory(container);
                container.scrollTop = container.scrollHeight;
            } else {
                appendBubble('bubble robot-bubble', data.robot);
            }
          }
          if (data.status && data.status !== lastStatus) {
            var bar = document.getElementById('status-bar');
            if (bar) {
              if(data.status === 'listening') { bar.className = 'status-bar status-listening'; bar.innerHTML = STATUS_LISTENING_TEXT; }
              else if(data.status === 'robotspeaking') { bar.className = 'status-bar status-speaking'; bar.innerHTML = STATUS_SPEAKING_TEXT; }
              else { bar.className = 'status-bar status-waiting'; bar.innerHTML = STATUS_WAITING_TEXT; }
            }
            lastStatus = data.status;
          }
        } catch(e) {}
      }
    };
    xhr.send();
  }, 500);
}
window.onload = function() {
  var c=document.getElementById('chat-container');
  if(c) c.scrollTop=c.scrollHeight;
  startPolling();
};
</script>
""".replace("__STATUS_LISTENING__", STATUS_LISTENING_TEXT).replace("__STATUS_SPEAKING__", STATUS_SPEAKING_TEXT).replace("__STATUS_WAITING__", STATUS_WAITING_TEXT)

def render_chat_sidebar(show_back=False):
    parts = [
        "<aside class='chat-shell'>",
        "<div class='chat-title'>" + CHAT_TITLE + "</div>",
        "<div class='chat-container' id='chat-container'>",
        "<div class='chat-placeholder' id='chat-placeholder'>" + CHAT_PLACEHOLDER + "</div>",
        "</div>",
        "<div class='status-bar status-waiting' id='status-bar'>" + STATUS_WAITING_TEXT + "</div>",
    ]
    if show_back:
        parts.append("<a class='btn' href='/menu' style='margin:0 18px 18px;'>Retour Menu</a>")
    parts.append("</aside>")
    return "".join(parts)

def _activity_icon_html(icon):
    icon = html_text(icon)
    if icon and (icon.startswith("/") or icon.startswith("http://") or icon.startswith("https://")):
        return "<img class='icon-img' src='" + icon + "' onerror=\"this.style.display='none'\">"
    return "<span class='icon'>" + (icon or "?") + "</span>"

def get_enabled_activities():
    configured = cfg_get("activities", None)
    if configured:
        activities = []
        for item in configured:
            if item.get("enabled", True) == False:
                continue
            activity_id = item.get("id", "").upper()
            href = item.get("href")
            if not href:
                if activity_id == "QUIZ":
                    href = "/quiz/start"
                elif activity_id in ["INTERACTIONS", "ANIMATIONS"]:
                    href = "/animations"
                elif activity_id in ["CATALOG", "CATALOGUE"]:
                    href = "/veolia/presentation1.html"
                else:
                    href = "/menu"
            activities.append({
                "label": html_text(item.get("label", activity_id.title())),
                "icon": html_text(item.get("icon", "?")),
                "href": html_text(href)
            })
        return activities
    return [
        {"label": "Quiz", "icon": "?", "href": "/quiz/start"},
        {"label": "Animations", "icon": "🎭", "href": "/animations"},
        {"label": "Veolia", "icon": "📖", "href": "/veolia/presentation1.html"},
    ]

def render_menu():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, CHAT_POLL_SCRIPT, "</head><body>", HEADER_HTML,
        "<div class='app-layout'>",
        "<main class='app-main'>",
        "<div class='menu-layout'>",
        "<div class='robot-zone'>",
        "<div class='welcome-bubble'>" + HOME_GREETING.replace("\n", "<br>") + "</div>",
        "<img src='/images/pepper.png' alt='Pepper'>",
        "</div>",
        "<div class='menu-cards'>",
    ]
    for activity in get_enabled_activities():
        parts.append(
            "<a class='btn btn-menu' href='" + activity["href"] + "'>"
            + _activity_icon_html(activity.get("icon"))
            + "<span>" + activity["label"] + "</span></a>"
        )
    parts.extend([
        "</div>",
        "</div>",
        "</main>",
        render_chat_sidebar(),
        "</div></body></html>"
    ])
    return "".join(parts)

def render_chat():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, CHAT_POLL_SCRIPT, "</head><body>", HEADER_HTML,
        "<div class='app-layout'>",
        "<main class='app-main' style='display:flex; align-items:center; justify-content:center; color:rgba(255,255,255,0.68); font-style:italic;'>",
        "Parlez à Pepper, la discussion s'affiche à droite.",
        "</main>",
        render_chat_sidebar(show_back=True),
        "</div></body></html>"
    ]
    return "".join(parts)

def render_animations(feedback=None):
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, CHAT_POLL_SCRIPT, "</head><body>", HEADER_HTML,
        "<div class='app-layout'>",
        "<main class='app-main animations-main'>",
        "<a class='btn back-menu' href='/menu'>← Retour au menu</a>",
        "<div class='surface-panel animations-panel'>",
        "<h1 style='margin-top:0;'>Animations</h1>",
        "<p style='color:" + THEME_BACKGROUND + "; opacity:0.65; font-style:italic; margin-top:-8px;'>Touchez un bouton ou dites le nom de l'animation à voix haute.</p>",
    ]
    if feedback:
        parts.append("<div style='display:inline-block; background:rgba(10,110,70,0.12); color:" + THEME_BACKGROUND + "; padding:10px 18px; border-radius:99px; font-weight:bold; margin:8px 0 18px;'>" + feedback + "</div>")
    parts.append("<div class='animations-grid'>")
    for anim in PEPPER_ANIMATIONS:
        parts.append(
            "<a class='btn btn-menu' href='/animation/run/" + anim["id"] + "'>"
            + _activity_icon_html(anim["icon"]) +
            "<span>" + anim["label"] + "</span>"
            "</a>"
        )
    parts.append("</div></main>")
    parts.append(render_chat_sidebar())
    parts.append("</div></body></html>")
    return "".join(parts)

CATALOG_ITEMS = cfg_get("catalog", None) or []

def render_catalogue():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, "</head><body>", HEADER_HTML,
        "<div class='container' style='padding:110px 280px 40px 50px; box-sizing:border-box; display:block; overflow-y:auto; -webkit-overflow-scrolling:touch;'>",
        "<a class='btn' href='/menu' style='position:fixed; top:82px; top:calc(38px + 9vh); left:24px; margin:0; padding:10px 20px; font-size:14px;'>← Retour au menu</a>",
    ]
    if CATALOG_ITEMS:
        # Pas de lecteur PDF dans la WebView de la tablette : on affiche le rendu PNG de chaque fiche
        for item in CATALOG_ITEMS:
            parts.append("<h1 style='color:" + THEME_TEXT_BACKGROUND + ";'>" + html_text(item.get("title", "")) + "</h1>")
            if item.get("image"):
                parts.append("<img src='" + html_text(item["image"]) + "' style='width:100%; height:auto; background:white; border-radius:18px; margin-bottom:30px;'>")
    else:
        parts.extend([
            "<div style='display:flex; flex:1; align-items:center; justify-content:center; width:100%;'>",
            "<div style='color:" + THEME_TEXT_BACKGROUND + "; opacity:0.72; font-style:italic;'>Aucune fiche dans le catalogue pour le moment.</div>",
            "</div>",
        ])
    parts.extend([
        "<div style='position:fixed; right:0; top:0; bottom:0; width:260px; border-left:1px solid rgba(255,255,255,0.08);'>",
        "<div class='welcome-bubble' style='top:240px; left:20px;'>Je ne peux pas discuter pendant une activité.</div>",
        "<img src='/images/pepperMuted.png' style='position:absolute; bottom:0; left:8px; width:240px; max-height:70%; object-fit:contain;'>",
        "</div>",
        "</div></body></html>"
    ])
    return "".join(parts)

def _build_question_say_text(q):
    """Construit le texte oral : question + toutes les reponses."""
    say_text = q.get("tts", q["text"]) + ". "
    for ans in q.get("answers_tts", q["answers"]):
        say_text += ans + ". "
    return say_text

def render_quiz(speak_question=True):
    if state.quiz_index < len(QUESTIONS):
        q = QUESTIONS[state.quiz_index]
        good_msg = q.get("good", "Bonne réponse !")
        bad_msgs = q.get("bad", [])
        bad_json = json.dumps(bad_msgs)
        parts = [
            "<html><head><meta charset='utf-8'>", COMMON_CSS,
            "<style>",
            "  .btn-answer { width: 100%; box-sizing: border-box; font-size: 28px; font-size: 3.6vh; font-weight: bold; height: 88px; height: 11vh; transition: background-color 0.2s, color 0.2s, border-color 0.2s; background: white; color: " + THEME_TEXT_SURFACE + "; border: 2px solid " + THEME_PRIMARY + " !important; margin: 0 0 1.8vh 0 !important; border-radius: 5.5vh !important; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-align: center; -webkit-align-items: center; align-items: center; -webkit-box-pack: center; -webkit-justify-content: center; justify-content: center; box-shadow: none !important; text-decoration: none; }",
            "  .btn-answer:last-child { margin-bottom: 0 !important; }",
            "  .btn-answer:active { transform: scale(0.99); background: #f0f8fa; }",
            "  #feedback-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; z-index:5000; flex-direction:column; align-items:center; justify-content:center; }",
            "  #feedback-text { font-size:36px; font-weight:bold; padding:30px 50px; border-radius:20px; max-width:80%; text-align:center; }",
            "  .quiz-back-btn { position: fixed; top: 96px; top: calc(38px + 9vh); left: 24px; z-index: 1110; padding: 10px 24px; font-size: 15px; font-weight: bold; color: white; background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 20px; text-decoration: none; transition: background 0.2s; }",
            "  .quiz-back-btn:active { background: rgba(255, 255, 255, 0.2); }",
            "  .hamburger span { background-color: " + THEME_SURFACE + "; !important; }",
            "</style>",
            "<script>",
            "var answered = false;",
            "var goodMsg = " + json.dumps(good_msg) + ";",
            "var badMsgs = " + bad_json + ";",
            "function clickAns(btn, idx, correctIdx) {",
            "  if (answered) return;",
            "  answered = true;",
            "  var overlay = document.getElementById('feedback-overlay');",
            "  var fbText = document.getElementById('feedback-text');",
            "  if (idx == correctIdx) {",
            "    btn.style.backgroundColor = '#2ecc71'; btn.style.color = 'white'; btn.style.borderColor = '#2ecc71';",
            "    overlay.style.background = 'rgba(46,204,113,0.92)';",
            "    fbText.innerText = goodMsg;",
            "  } else {",
            "    btn.style.backgroundColor = '#e74c3c'; btn.style.color = 'white'; btn.style.borderColor = '#e74c3c';",
            "    overlay.style.background = 'rgba(231,76,60,0.92)';",
            "    var msg = (badMsgs && badMsgs[idx]) ? badMsgs[idx] : 'Mauvaise réponse !';",
            "    fbText.innerText = msg;",
            "  }",
            "  overlay.style.display = 'flex';",
            "  setTimeout(function() { window.location.href = '/quiz/answer/' + idx + '?t=' + new Date().getTime(); }, 3000);",
            "}",
            "</script></head><body>", HEADER_HTML,
            "<div id='feedback-overlay'><div id='feedback-text' style='color:white;'></div></div>",
            "<a class='quiz-back-btn' href='/menu'>← Retour au menu</a>",            
            "<div style='position:fixed; top:80px; right:12px; z-index:1200; display:-webkit-box; display:-webkit-flex; display:flex; -webkit-box-orient:horizontal; -webkit-box-direction:normal; -webkit-flex-direction:row; flex-direction:column; -webkit-box-align:center; -webkit-align-items:center; align-items:flex-end; margin-bottom:6px;'>",
            "  <div style='background:white; color:" + THEME_TEXT_SURFACE + "; padding:10px 22px; border-radius:24px; font-weight:bold; font-size:14px; box-shadow:0 4px 12px rgba(0,0,0,0.15); border:1px solid rgba(0,0,0,0.05); white-space:nowrap;'>",
            "    Je ne peux pas t'écouter pendant l'activité.",
            "  </div>",
            "  <div>",
            "  <img src='/images/pepperHeadMuted.png' onerror=\"this.src='/images/pepperMuted.png'\" style='width:90px; height:90px; object-fit:contain;'>",
            "  </div>",
            "</div>",            
            '<div class="container" style="background-color: transparent; padding: 165px 30px 24px 30px; height: 100vh; box-sizing: border-box; justify-content: center;">',            
            '  <div class="surface-panel" style="width:100%; height:100%; padding:30px 45px 24px; box-sizing:border-box; display:-webkit-box; display:-webkit-flex; display:flex; -webkit-box-orient:vertical; -webkit-box-direction:normal; -webkit-flex-direction:column; flex-direction:column; -webkit-box-align:center; -webkit-align-items:center; align-items:center; border-radius:36px; box-shadow:0 16px 36px rgba(0,0,0,0.22); overflow:hidden;">',
            '    <h1 style="font-size: 50px; font-size: 6vh; margin: 0 0 1.5vh 0; color: ' + THEME_PRIMARY + '; letter-spacing: 4px; font-weight:800; text-shadow:none;">QUIZ AVEC PEPPER</h1>',
            '    <h2 style="font-size: 26px; font-size: 3.8vh; font-weight: bold; margin: 0 0 3vh 0; color: ' + THEME_TEXT_SURFACE + '; line-height:1.2;">' + q['text'] + '</h2>',
            '    <div style="display:-webkit-box; display:-webkit-flex; display:flex; -webkit-box-orient:vertical; -webkit-box-direction:normal; -webkit-flex-direction:column; flex-direction:column; width: 100%; max-width: 92%; -webkit-box-flex:1; -webkit-flex:1; flex:1; -webkit-box-pack:center; -webkit-justify-content:center; justify-content:center; box-sizing:border-box;">'
        ]
        
        for i, ans in enumerate(q["answers"]):
            correct_idx = q["correct"]
            parts.append("      <div class='btn btn-answer' onclick='clickAns(this, " + str(i) + ", " + str(correct_idx) + ")'>" + ans + "</div>")
        
        parts.append("    </div>")
        parts.append("    <p style='margin:16px 0 0 0; flex-shrink:0; font-size:18px; font-size:2.6vh; color:" + THEME_TEXT_SURFACE + "; font-weight:bold;'>Question " + str(state.quiz_index + 1) + "/" + str(len(QUESTIONS)) + "</p>")
        parts.append("  </div>")
        parts.append("</div></body></html>")

        if speak_question:
            threading.Thread(target=action_say, args=(_build_question_say_text(q),)).start()
        return "".join(parts)
    else:
        score_txt = str(state.quiz_score) + " sur " + str(len(QUESTIONS))
        parts = [
            "<html><head><meta charset='utf-8'>", COMMON_CSS, "</head><body>", HEADER_HTML,
            "<div class='container' style='justify-content:center; padding:40px 40px;'>",
            "  <div class='surface-panel' style='width:100%; max-width:680px; padding:40px; border-radius:36px; box-shadow:0 16px 36px rgba(0,0,0,0.22); display:flex; flex-direction:column; align-items:center;'>",
            "    <h1 style='font-size:38px; margin-top:0; margin-bottom:15px;'>Quiz terminé !</h1>",
            "    <div style='font-size:72px; color:#2ecc71; font-weight:bold; margin:15px 0;'>" + score_txt + "</div>",
            "    <p style='font-size:20px; max-width:90%; line-height:1.5; margin:15px auto; color:" + THEME_TEXT_SURFACE + "; font-weight:500;'>" + QUIZ_END_TEXT.replace(". ", ".<br>") + "</p>",
            "    <div style='display:flex; flex-direction:column; gap:12px; margin-top:20px; width:100%; align-items:center;'>",
            "      <a class='btn btn-green' href='/quiz/start' style='width:260px; border-radius:22px; font-size:18px;' onclick=\"this.href='/quiz/start?t=' + new Date().getTime()\">Recommencer</a>",
            "      <a class='btn' href='/menu' style='width:260px; border-radius:22px; font-size:18px; color:var(--background);'>Menu principal</a>",
            "    </div>",
            "  </div>",
            "</div></body></html>"
        ]
        if speak_question:
            threading.Thread(target=action_say, args=(QUIZ_END_TEXT,)).start()
        return "".join(parts)

# Corrections de prononciation (texte dit seulement, pas affiche) : {"mot": "phonetique"} dans client.json
TTS_PHONETIC = _fix_quiz_value(cfg_get("ttsPhonetic", None) or {})

def tts_fix(text):
    text = str(text)
    for wrong, correct in TTS_PHONETIC.items():
        text = text.replace(html_text(wrong), html_text(correct))
    return text

def action_say(text):
    """Dit un texte via le robot (bloquant). Appeler dans un thread."""
    if session_global and qi:
        try:
            tts = session_global.service("ALTextToSpeech")
            try:
                tts.setLanguage("French")
            except Exception as e_lang:
                print("[ROBOT] Avertissement langue: " + str(e_lang))
            print("[ROBOT] Say: " + text)
            tts.say(tts_fix(text))
        except: pass

def action_say_then(text1, text2):
    """Dit text1, puis text2 sequentiellement (feedback puis question suivante)."""
    if session_global and qi:
        try:
            tts = session_global.service("ALTextToSpeech")
            try:
                tts.setLanguage("French")
            except Exception as e_lang:
                print("[ROBOT] Avertissement langue: " + str(e_lang))
            print("[ROBOT] Say feedback: " + text1)
            tts.say(tts_fix(text1))
            time.sleep(0.5)
            print("[ROBOT] Say question: " + text2)
            tts.say(tts_fix(text2))
        except: pass

def action_animation(animation_id):
    anim = PEPPER_ANIMATION_BY_ID.get(animation_id)
    if not anim:
        return
    if session_global and qi:
        if animation_id == "dance":
            try:
                behavior = session_global.service("ALBehaviorManager")
                for path in PEPPER_ANIMATION_PATHS.get(animation_id, []):
                    try:
                        print("[ROBOT] Behavior: " + path)
                        behavior.runBehavior(path)
                        return
                    except Exception as e_path:
                        print("[ROBOT] Behavior echec " + path + ": " + str(e_path))
            except Exception as e_beh:
                print("[ROBOT] ALBehaviorManager indisponible: " + str(e_beh))
            action_say(anim.get("say", anim.get("label", "")))
            return

        try:
            player = session_global.service("ALAnimationPlayer")
            for path in PEPPER_ANIMATION_PATHS.get(animation_id, []):
                try:
                    print("[ROBOT] Animation: " + path)
                    player.run(path)
                    return
                except Exception as e_path:
                    print("[ROBOT] Animation echec " + path + ": " + str(e_path))
        except Exception as e_anim:
            print("[ROBOT] ALAnimationPlayer indisponible: " + str(e_anim))
    action_say(anim.get("say", anim.get("label", "")))

class AppHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_HEAD(self):
        try:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
        except Exception:
            pass

    def _set_volume(self, vol):
        """Applique le volume via toutes les strategies disponibles."""
        print("[VOLUME] Requete GET - vol=" + str(vol) +
              " ALProxy=" + str(_ALProxy is not None) +
              " session=" + str(bool(session_global)) +
              " robot=" + str(ROBOT_IP_GLOBAL))
        done = False
        if not done and _ALProxy and ROBOT_IP_GLOBAL:
            try:
                _ALProxy("ALAudioDevice", ROBOT_IP_GLOBAL, 9559).setOutputVolume(vol)
                print("[VOLUME] OK via ALProxy")
                done = True
            except Exception as e:
                print("[VOLUME] ALProxy echec: " + str(e))
        if not done and session_global:
            try:
                session_global.service("ALAudioDevice").setOutputVolume(vol)
                print("[VOLUME] OK via qi.Session")
                done = True
            except Exception as e:
                print("[VOLUME] qi.Session echec: " + str(e))
        if not done:
            print("[VOLUME] ECHEC total - verifier robot_ip et connexion NaoQI")
        return done

    def _get_robot_status(self):
        status = {"connected": False, "battery": "N/D", "volume": None}
        if _ALProxy and ROBOT_IP_GLOBAL:
            try:
                status["battery"] = str(_ALProxy("ALBattery", ROBOT_IP_GLOBAL, 9559).getBatteryCharge()) + "%"
                status["connected"] = True
            except Exception as e:
                print("[STATUS] Batterie ALProxy echec: " + str(e))
            try:
                status["volume"] = _ALProxy("ALAudioDevice", ROBOT_IP_GLOBAL, 9559).getOutputVolume()
                status["connected"] = True
            except Exception as e:
                print("[STATUS] Volume ALProxy echec: " + str(e))
        if session_global:
            try:
                if status["battery"] == "N/D":
                    status["battery"] = str(session_global.service("ALBattery").getBatteryCharge()) + "%"
                if status["volume"] is None:
                    status["volume"] = session_global.service("ALAudioDevice").getOutputVolume()
                status["connected"] = True
            except Exception as e:
                print("[STATUS] qi.Session echec: " + str(e))
        return status

    def do_GET(self):
        try:
            # 0. Volume via GET  (/setvolume?v=70)
            if self.path.startswith("/setvolume"):
                try:
                    import re as _re2
                    m = _re2.search(r'[?&]v=(\d+)', self.path)
                    if m:
                        self._set_volume(int(m.group(1)))
                except Exception as e_vol:
                    print("[VOLUME] Erreur handler GET: " + str(e_vol))
                # Repondre avec un pixel GIF transparent (aucun rendu)
                gif1px = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\xff\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00\x3b"
                self.send_response(200)
                self.send_header("Content-type", "image/gif")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Content-Length", str(len(gif1px)))
                self.end_headers()
                self.wfile.write(gif1px)
                return

            # 0b. Recog via GET  (/setrecog?d=0|1)
            if self.path.startswith("/setrecog"):
                try:
                    import re as _re3
                    m = _re3.search(r'[?&]d=([01])', self.path)
                    if m and session_global:
                        disabled = (m.group(1) == '1')
                        print("[RECOG] GET desactivation=" + str(disabled))
                        session_global.service("ALMemory").raiseEvent("PepperRecogDisabled", str(disabled))
                except Exception as e_recog:
                    print("[RECOG] Erreur handler GET: " + str(e_recog))
                gif1px = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\xff\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00\x3b"
                self.send_response(200)
                self.send_header("Content-type", "image/gif")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Content-Length", str(len(gif1px)))
                self.end_headers()
                self.wfile.write(gif1px)
                return

            if self.path.startswith("/robotstatus"):
                payload = json.dumps(self._get_robot_status())
                if sys.version_info[0] >= 3:
                    payload = payload.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if self.path == "/" or self.path == "/index.html":
                set_app_mode("chat")
                self.send_response(302)
                self.send_header("Location", "/menu")
                self.end_headers()
                return

            # 2. Fichiers statiques (Images globales)
            if self.path.startswith("/images/") or self.path.startswith("/config-assets/"):
                fpath = self.path[1:]
                if ".." in fpath: return
                if os.path.exists(fpath):
                    self.send_response(200)
                    self.send_header("Cache-Control", "public, max-age=86400")
                    if fpath.endswith(".css"): self.send_header("Content-type", "text/css")
                    elif fpath.endswith(".js"): self.send_header("Content-type", "application/javascript")
                    elif fpath.endswith(".svg"): self.send_header("Content-type", "image/svg+xml")
                    elif fpath.endswith(".png"): self.send_header("Content-type", "image/png")
                    elif fpath.endswith(".jpg") or fpath.endswith(".jpeg"): self.send_header("Content-type", "image/jpeg")
                    elif fpath.endswith(".webp"): self.send_header("Content-type", "image/webp")
                    elif fpath.endswith(".pdf"): self.send_header("Content-type", "application/pdf")
                    self.end_headers()
                    with open(fpath, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            # 3. Fichiers statiques du module VEOLIA
            if self.path.startswith("/veolia/"):
                fpath = self.path[1:]
                if ".." in fpath: return
                if os.path.exists(fpath) and os.path.isfile(fpath):
                    if fpath.endswith(".html") or "." not in fpath:
                        set_app_mode("chat")

                    with open(fpath, "rb") as f:
                        content_bytes = f.read()
                    self.send_response(200)
                    if fpath.endswith(".css"): self.send_header("Content-type", "text/css; charset=utf-8")
                    elif fpath.endswith(".js"): self.send_header("Content-type", "application/javascript; charset=utf-8")
                    elif fpath.endswith(".png"): self.send_header("Content-type", "image/png")
                    elif fpath.endswith(".jpg") or fpath.endswith(".jpeg"): self.send_header("Content-type", "image/jpeg")
                    elif fpath.endswith(".webp"): self.send_header("Content-type", "image/webp")
                    else: self.send_header("Content-type", "text/html; charset=utf-8")
                    
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Content-Length", str(len(content_bytes)))
                    self.end_headers()
                    self.wfile.write(content_bytes)
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            if self.path.startswith('/poll'):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                data = {
                    "user": state.chat_user, 
                    "robot": state.chat_robot, 
                    "status": state.chat_status
                }
                state.chat_user = ""
                state.chat_robot = ""
                out = json.dumps(data)
                self.wfile.write(out.encode('utf-8') if sys.version_info[0] >= 3 else out)
                return
            
            content = ""
            if self.path == "/menu": 
                set_app_mode("chat")
                content = render_menu()
                
            elif self.path.startswith("/ai_module"): 
                state.chat_status = "waiting"
                set_app_mode("chat")
                content = render_chat()
                
            elif self.path.startswith("/quiz"):
                set_app_mode("quiz")
                
                speak = True
                if "/start" in self.path: 
                    state.reset_quiz()
                elif "/answer/" in self.path:
                    speak = False
                    try:
                        ans_str = self.path.split("/answer/")[1].split("?")[0]
                        ans = int(ans_str)
                        q = QUESTIONS[state.quiz_index]
                        correct = q["correct"]
                        if ans == correct:
                            state.quiz_score += 1
                            say_txt = q.get("good", "Bonne reponse !")
                        else:
                            bad_msgs = q.get("bad", [])
                            say_txt = bad_msgs[ans] if ans < len(bad_msgs) and bad_msgs[ans] else "Mauvaise reponse !"
                        state.quiz_index += 1
                        if state.quiz_index < len(QUESTIONS):
                            next_q_text = _build_question_say_text(QUESTIONS[state.quiz_index])
                            threading.Thread(target=action_say_then, args=(say_txt, next_q_text)).start()
                        else:
                            threading.Thread(target=action_say_then, args=(say_txt, QUIZ_END_TEXT)).start()
                    except Exception as e: 
                        print("Erreur Answer: " + str(e))
                content = render_quiz(speak_question=speak)

            elif self.path.startswith("/animations"):
                set_app_mode("animations")
                content = render_animations()

            elif self.path.startswith("/animation/run/"):
                set_app_mode("animations")
                anim_id = self.path.split("/animation/run/")[1].split("?")[0]
                anim = PEPPER_ANIMATION_BY_ID.get(anim_id)
                if anim:
                    threading.Thread(target=action_animation, args=(anim_id,)).start()
                    content = render_animations(anim["label"] + " en cours...")
                else:
                    content = render_animations("Animation indisponible.")

            elif self.path.startswith("/catalogue"):
                set_app_mode("catalogue")
                content = render_catalogue()
                
            else:
                set_app_mode("chat")
                content = render_menu()

            if content:
                try:
                    content_encoded = content.encode('ascii', 'ignore') if sys.version_info[0] < 3 else content.encode('utf-8')
                except:
                    content_encoded = content
                    
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(content_encoded)))
                self.end_headers()
                self.wfile.write(content_encoded)
                
        except Exception as e:
            print("Erreur GET: " + str(e))

    def do_POST(self):
        try:
            if self.path == "/update":
                length_str = self.headers.get('Content-Length', '0')
                length = int(length_str)
                if length > 0:
                    raw_data = self.rfile.read(length).decode('utf-8')
                    data = json.loads(raw_data)
                    
                    if "user" in data: state.chat_user = data["user"]
                    if "robot" in data: state.chat_robot = data["robot"]
                    if "status" in data: state.chat_status = data["status"]
                    
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK" if sys.version_info[0] >= 3 else "OK")

            elif self.path == "/setmode":
                length_str = self.headers.get('Content-Length', '0')
                length = int(length_str)
                if length > 0:
                    raw_data = self.rfile.read(length).decode('utf-8')
                    data = json.loads(raw_data)
                    mode = data.get("mode", "menu")
                    set_app_mode(mode)
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK" if sys.version_info[0] >= 3 else "OK")

            elif self.path == "/setvolume":
                length_str = self.headers.get('Content-Length', '0')
                length = int(length_str) if length_str else 0
                if length > 0:
                    try:
                        raw_data = self.rfile.read(length).decode('utf-8')
                        data = json.loads(raw_data)
                        vol = int(data.get("volume", 70))
                        self._set_volume(vol)
                    except Exception as e_post_vol:
                        print("[VOLUME] Erreur POST fallback: " + str(e_post_vol))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK" if sys.version_info[0] >= 3 else "OK")

            elif self.path == "/setrecog":
                length_str = self.headers.get('Content-Length', '0')
                length = int(length_str)
                if length > 0:
                    raw_data = self.rfile.read(length).decode('utf-8')
                    data = json.loads(raw_data)
                    disabled = data.get("disabled", False)
                    print("[RECOG] Desactivation :", disabled)
                    if session_global:
                        try:
                            mem = session_global.service("ALMemory")
                            mem.raiseEvent("PepperRecogDisabled", str(disabled))
                        except: pass
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK" if sys.version_info[0] >= 3 else "OK")
                
        except Exception as e:
            print("Erreur POST: " + str(e))

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    allow_reuse_address = True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip', required=True)
    args = parser.parse_args()

    global session_global, ROBOT_IP_GLOBAL
    ROBOT_IP_GLOBAL = args.ip
    if qi:
        try:
            session_global = qi.Session()
            session_global.connect("tcp://" + args.ip + ":9559")
            print("[NAOQI] Connecte via qi.Session a " + args.ip)
            try:
                tab = session_global.service("ALTabletService")
                
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    my_ip = s.getsockname()[0]
                except:
                    try:
                        my_ip = socket.gethostbyname(socket.gethostname())
                    except:
                        my_ip = "127.0.0.1"
                finally:
                    s.close()

                print("IP PC detectee : " + str(my_ip))
                url = "http://{}:{}/".format(my_ip, PORT)
                print("Envoi URL tablette : " + url)
                tab.showWebview(url)
            except: pass
        except: pass

    server = ThreadedHTTPServer(("0.0.0.0", PORT), AppHandler)
    print("Serveur lance sur port " + str(PORT))
    try: server.serve_forever()
    except KeyboardInterrupt: sys.exit(0)

if __name__ == "__main__":
    main()
