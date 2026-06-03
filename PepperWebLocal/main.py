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

QUIZ_END_TEXT = (
    "Analyse des résultats... bip bip... "
    "Mission réussie ! "
    "Tu es officiellement un explorateur de la beauté du futur ! "
    "Tu peux continuer ton aventure et tester plein d'ateliers autour de toi ! "
    "Et si tu veux en découvrir encore plus... les animateurs sont là pour t'aider ! "
    "À bientôt petit inventeur du futur !"
)

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

THEME_PRIMARY = "#18C6D9"
THEME_SECONDARY = "#18C6D9"
THEME_BACKGROUND = "#1F365C"
THEME_SURFACE = "#ECF4F8"
THEME_TEXT_SURFACE = "#1A1A1A"
THEME_TEXT_BACKGROUND = "#FFFFFF"
THEME_OVERLAY = "rgba(31,54,92,0.96)"

PEPPER_ANIMATIONS = [
    {"id": "wave", "label": "Coucou", "icon": "👋", "say": "Coucou !"},
    {"id": "dance", "label": "Danse", "icon": "🕺", "say": "Regardez ma petite danse !"},
    {"id": "laugh", "label": "Rire", "icon": "😁", "say": "Ha ha ha !"},
]

PEPPER_ANIMATION_PATHS = {
    "wave": [
        "animations/Stand/Gestures/Hey_1",
        "animations/Stand/Gestures/Hey_2",
    ],
    "dance": [
        "animations/Stand/Gestures/Dance_1",
        "animations/Stand/Gestures/Dance_2",
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
<a href="/menu"><img class="top-logo" src="/images/EvotionLogo.png" onerror="this.style.display='none'"></a>
<div class="hamburger" onclick="toggleVolumeOverlay()">
    <span></span><span></span><span></span>
</div>

<!-- MENU BURGER : VOLUME OVERLAY -->
<div id="volume-overlay" style="display:none; position:fixed; top:0; right:0; width:320px; height:100%; background:__THEME_OVERLAY__; z-index:2000; color:white; flex-direction:column; align-items:center; padding:36px 24px; box-sizing:border-box; box-shadow:-16px 0 34px rgba(0,0,0,0.28);">
    <div onclick="toggleVolumeOverlay()" style="position:absolute; top:22px; right:24px; width:34px; height:26px; display:flex; flex-direction:column; justify-content:space-between; cursor:pointer; opacity:0.8;">
        <span style="display:block; height:4px; background:#ECF4F8; border-radius:99px;"></span>
        <span style="display:block; height:4px; background:#ECF4F8; border-radius:99px; width:22px; margin-left:auto;"></span>
        <span style="display:block; height:4px; background:#ECF4F8; border-radius:99px;"></span>
    </div>
    <h3 style="font-size:22px; margin:10px 0 28px;">Gestion du volume</h3>
    <div style="display:flex; align-items:center; justify-content:center; margin:20px 0;">
        <div onclick="changeVolume(10)" style="font-size:40px; cursor:pointer; background:white; color:#333; width:50px; height:50px; border-radius:50%; display:flex; justify-content:center; align-items:center;">+</div>
        <div id="vol-display" style="font-size:50px; font-weight:bold; margin:0 20px;">70</div>
        <div onclick="changeVolume(-10)" style="font-size:40px; cursor:pointer; background:white; color:#333; width:50px; height:50px; border-radius:50%; display:flex; justify-content:center; align-items:center;">-</div>
    </div>
    <div style="display:flex; flex-direction:column; align-items:flex-start; gap:28px; margin-top:30px; padding:0 6px; width:100%; box-sizing:border-box;">
        <label style="display:flex; align-items:center; font-size:20px; margin-bottom:30px; cursor:pointer; text-align:left;">
            <input type="checkbox" id="mute-robot" style="width:30px; height:30px; margin-right:20px;" onchange="toggleMute()">
            Couper le son<br>du robot
        </label>
        <label style="display:flex; align-items:center; font-size:20px; cursor:pointer; text-align:left;">
            <input type="checkbox" id="mute-recog" style="width:30px; height:30px; margin-right:20px;" onchange="toggleRecog()">
            Désactiver la<br>reconnaissance<br>vocale
        </label>
    </div>
    <div onclick="toggleVolumeOverlay()" style="margin-top:auto; margin-bottom:8px; background:#ECF4F8; color:#1F365C; padding:15px 42px; border-radius:30px; font-size:22px; font-weight:bold; cursor:pointer;">Fermer</div>
</div>

<script>
var _volOverlayOpen = false;
function toggleVolumeOverlay() {
    _volOverlayOpen = !_volOverlayOpen;
    var el = document.getElementById('volume-overlay');
    el.style.display = _volOverlayOpen ? 'flex' : 'none';
}
function _sendVol(vol) {
    /* Methode Image() : compatible 100% des WebViews (Android ancien, Pepper...) */
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
</script>
""".replace("__THEME_OVERLAY__", THEME_OVERLAY)

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
    h1 { color: """ + THEME_PRIMARY + """; color: var(--primary); font-size: 40px; margin: 20px 0; text-shadow: none; text-transform: uppercase; letter-spacing: 3px; }
    .container { width: 100%; height: 100vh; margin: 0 auto; padding-top: 80px; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; overflow: hidden; }
    .btn { display: inline-block; display: inline-flex; align-items: center; justify-content: center; background: """ + THEME_SURFACE + """; background: var(--surface); border: 2px solid rgba(24,198,217,0.45); border-radius: 26px; padding: 15px 30px; margin: 10px; font-size: 20px; color: """ + THEME_BACKGROUND + """; color: var(--background); text-decoration: none; box-shadow: 0 10px 28px rgba(0,0,0,0.2); cursor: pointer; font-weight: bold; transition: transform 0.1s; }
    .btn:active { transform: scale(0.95); background: #dcecf2; }
    .btn-green { background: #2ecc71; color: white; }
    .btn-red { background: #e74c3c; color: white; }
    .btn-menu { width: 150px; height: 120px; padding: 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 2px; flex-direction: column; gap: 10px; }
    .btn-menu span { display: block; }
    .btn-menu .icon { font-size: 38px; line-height: 1; margin-bottom: 10px; }
    
    .chat-container { display: flex; flex-direction: column; gap: 15px; padding: 18px; width: 100%; flex: 1; min-height: 0; overflow-y: auto; background: """ + THEME_SURFACE + """; background: var(--surface); border-radius: 0 0 30px 30px; margin-bottom: 10px; box-sizing: border-box; }
    .bubble { padding: 15px; border-radius: 18px; background: #ffffff; color: """ + THEME_BACKGROUND + """; color: var(--background); font-size: 18px; text-align: left; box-shadow: 0 3px 10px rgba(0,0,0,0.08); position: relative; font-weight: bold; }
    .user-bubble { align-self: flex-end; margin-left: 20%; border: 1px solid rgba(0,0,0,0.05); }
    .robot-bubble { align-self: flex-start; margin-right: 20%; text-align: left; background: """ + THEME_SECONDARY + """; background: var(--secondary); color: white; }
    .status-bar { padding: 15px; font-size: 24px; font-weight: bold; color: white; background: #95a5a6; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; width: 80%; flex-shrink: 0; }
    .status-listening { background: #00e676; }
    .status-speaking { background: #9c27b0; }
    .status-waiting { background: #bdc3c7; color: #333; }
    .top-logo { position: fixed; top: 24px; left: 24px; z-index: 1100; height: 28px; opacity: 0.95; }
    .hamburger { position: fixed; top: 22px; right: 24px; z-index: 1100; width: 34px; height: 26px; display: flex; flex-direction: column; justify-content: space-between; cursor: pointer; }
    .hamburger span { display: block; height: 4px; background: """ + THEME_SURFACE + """; background: var(--surface); border-radius: 99px; }
    .surface-panel { background: """ + THEME_SURFACE + """; background: var(--surface); color: """ + THEME_TEXT_SURFACE + """; color: var(--text-surface); border-radius: 30px; box-shadow: 0 16px 36px rgba(0,0,0,0.22); }
    .app-layout { width: 100%; height: 100vh; display: flex; overflow: hidden; }
    .app-main { flex: 1; min-width: 0; height: 100vh; position: relative; box-sizing: border-box; }
    .menu-layout { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; box-sizing: border-box; padding: 40px 36px 20px; }
    .robot-zone { position: relative; width: 360px; height: 620px; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }
    .robot-zone img { max-width: 100%; max-height: 520px; object-fit: contain; }
    .welcome-bubble { position: absolute; top: 8px; left: 0; background: #ffffff; color: """ + THEME_BACKGROUND + """; color: var(--background); border-radius: 18px; padding: 14px 18px; max-width: 250px; text-align: left; font-size: 15px; box-shadow: 0 6px 18px rgba(0,0,0,0.16); }
    .welcome-bubble:after { content: ''; position: absolute; right: 22px; bottom: -14px; border-width: 14px 12px 0 0; border-style: solid; border-color: #ffffff transparent transparent transparent; }
    .menu-cards { width: 340px; display: block; font-size: 0; text-align: center; margin-left: 70px; }
    .menu-left { display: inline-block; vertical-align: middle; width: 174px; }
    .menu-right { display: inline-block; vertical-align: middle; width: 166px; }
    .menu-cards .btn-menu { display: block; box-sizing: border-box; margin: 9px auto; }
    .chat-shell { width: 360px; height: 100vh; flex: 0 0 360px; background: """ + THEME_SURFACE + """; background: var(--surface); box-shadow: -18px 0 34px rgba(0,0,0,0.24); display: flex; flex-direction: column; overflow: hidden; }
    .chat-title { height: 58px; line-height: 58px; color: """ + THEME_PRIMARY + """; color: var(--primary); font-size: 18px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase; border-bottom: 1px solid rgba(0,0,0,0.08); flex-shrink: 0; }
    .chat-placeholder { flex: 1; display: flex; align-items: center; justify-content: center; color: rgba(31,54,92,0.52); font-style: italic; padding: 22px; }
</style>
""")

CHAT_POLL_SCRIPT = """
<script>
var lastStatus = '';
function appendBubble(className, html) {
  var container = document.getElementById('chat-container');
  if (!container) return;
  var placeholder = document.getElementById('chat-placeholder');
  if (placeholder) placeholder.style.display = 'none';
  var div = document.createElement('div');
  div.className = className;
  div.innerHTML = html;
  container.appendChild(div);
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
            } else {
                appendBubble('bubble robot-bubble', data.robot);
            }
          }
          if (data.status && data.status !== lastStatus) {
            var bar = document.getElementById('status-bar');
            if (bar) {
              if(data.status === 'listening') { bar.className = 'status-bar status-listening'; bar.innerHTML = 'Je vous ecoute / Parlez !'; }
              else if(data.status === 'robotspeaking') { bar.className = 'status-bar status-speaking'; bar.innerHTML = 'Je parle...'; }
              else { bar.className = 'status-bar status-waiting'; bar.innerHTML = 'Un instant...'; }
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
"""

def render_chat_sidebar(show_status=False, show_back=False):
    parts = [
        "<aside class='chat-shell'>",
        "<div class='chat-title'>Discussion avec Pepper</div>",
        "<div class='chat-container' id='chat-container'>",
        "<div class='chat-placeholder' id='chat-placeholder'>Parlez à Pepper pour démarrer la discussion...</div>",
        "</div>",
    ]
    if show_status:
        parts.append("<div class='status-bar status-waiting' id='status-bar' style='font-size:16px; width:auto; margin:10px 18px;'>Initialisation...</div>")
    if show_back:
        parts.append("<a class='btn' href='/menu' style='margin:0 18px 18px;'>Retour Menu</a>")
    parts.append("</aside>")
    return "".join(parts)

def render_menu():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, CHAT_POLL_SCRIPT, "</head><body>", HEADER_HTML,
        "<div class='app-layout'>",
        "<main class='app-main'>",
        "<div class='menu-layout'>",
        "<div class='robot-zone'>",
        "<div class='welcome-bubble'>Salut ! Je suis Pepper,<br>Prêt à apprendre et jouer avec toi</div>",
        "<img src='/images/pepper.png' alt='Pepper'>",
        "</div>",
        "<div class='menu-cards'>",
        "<div class='menu-left'>",
        "<a class='btn btn-menu' href='/quiz/start'><span class='icon'>?</span><span>Quiz</span></a>",
        "<a class='btn btn-menu' href='/animations'><span class='icon'>🎭</span><span>Animations</span></a>",
        "</div>",
        "<div class='menu-right'>",
        "<a class='btn btn-menu' href='/catalogue'><span class='icon'>📖</span><span>Catalogue</span></a>",
        "</div>",
        "</div>",
        "</div>",
        "</main>",
        render_chat_sidebar(),
        "</div></body></html>"
    ]
    return "".join(parts)

def render_chat():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, CHAT_POLL_SCRIPT, "</head><body>", HEADER_HTML,
        "<div class='app-layout'>",
        "<main class='app-main' style='display:flex; align-items:center; justify-content:center; color:rgba(255,255,255,0.68); font-style:italic;'>",
        "Parlez à Pepper, la discussion s'affiche à droite.",
        "</main>",
        render_chat_sidebar(show_status=True, show_back=True),
        "</div></body></html>"
    ]
    return "".join(parts)

def render_animations(feedback=None):
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, CHAT_POLL_SCRIPT, "</head><body>", HEADER_HTML,
        "<div class='app-layout'>",
        "<main class='app-main' style='padding:110px 50px 40px; box-sizing:border-box;'>",
        "<a class='btn' href='/menu' style='position:fixed; top:82px; left:24px; margin:0; padding:10px 20px; font-size:14px;'>← Retour au menu</a>",
        "<div class='surface-panel' style='width:72%; max-width:760px; padding:36px 34px 42px; margin:0 auto;'>",
        "<h1 style='margin-top:0;'>Animations</h1>",
        "<p style='color:" + THEME_BACKGROUND + "; opacity:0.65; font-style:italic; margin-top:-8px;'>Touchez un bouton ou dites le nom de l'animation à voix haute.</p>",
    ]
    if feedback:
        parts.append("<div style='display:inline-block; background:rgba(24,198,217,0.18); color:#1F365C; padding:10px 18px; border-radius:99px; font-weight:bold; margin:8px 0 18px;'>" + feedback + "</div>")
    parts.append("<div style='display:flex; justify-content:center; gap:18px; flex-wrap:wrap; margin-top:18px;'>")
    for anim in PEPPER_ANIMATIONS:
        parts.append(
            "<a class='btn btn-menu' href='/animation/run/" + anim["id"] + "'>"
            "<span class='icon'>" + anim["icon"] + "</span>"
            "<span>" + anim["label"] + "</span>"
            "</a>"
        )
    parts.append("</div></main>")
    parts.append(render_chat_sidebar())
    parts.append("</div></body></html>")
    return "".join(parts)

def render_catalogue():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, "</head><body>", HEADER_HTML,
        "<div class='container' style='padding:110px 50px 40px;'>",
        "<a class='btn' href='/menu' style='position:fixed; top:82px; left:24px; margin:0; padding:10px 20px; font-size:14px;'>← Retour au menu</a>",
        "<h1>Catalogue</h1>",
        "<div style='display:flex; flex:1; align-items:center; justify-content:center; width:100%;'>",
        "<div style='color:#ECF4F8; opacity:0.72; font-style:italic;'>Aucune fiche dans le catalogue pour le moment.</div>",
        "</div>",
        "<div style='position:fixed; right:0; top:0; bottom:0; width:260px; border-left:1px solid rgba(255,255,255,0.08);'>",
        "<div class='welcome-bubble' style='top:160px; left:20px;'>Je ne peux pas discuter pendant une activité.</div>",
        "<img src='/images/pepperMuted.png' style='position:absolute; bottom:0; left:8px; width:240px; max-height:70%; object-fit:contain;'>",
        "</div>",
        "</div></body></html>"
    ]
    return "".join(parts)

def _build_question_say_text(q):
    """Construit le texte oral : question + toutes les reponses."""
    say_text = q["text"] + ". "
    for ans in q["answers"]:
        say_text += ans + ". "
    return say_text

def render_quiz(speak_question=True):
    if state.quiz_index < len(QUESTIONS):
        q = QUESTIONS[state.quiz_index]
        good_msg = q.get("good", "Bonne reponse !")
        bad_msgs = q.get("bad", [])
        bad_json = json.dumps(bad_msgs)
        parts = [
            "<html><head><meta charset='utf-8'>", COMMON_CSS,
            "<style>.btn-answer { width: 45%; font-size: 24px; min-height: 100px; transition: background-color 0.2s; }",
            "#feedback-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%; z-index:5000; flex-direction:column; align-items:center; justify-content:center; }",
            "#feedback-text { font-size:36px; font-weight:bold; padding:30px 50px; border-radius:20px; max-width:80%; text-align:center; }</style>",
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
            "    btn.style.backgroundColor = '#2ecc71'; btn.style.color = 'white';",
            "    overlay.style.background = 'rgba(46,204,113,0.92)';",
            "    fbText.innerText = goodMsg;",
            "  } else {",
            "    btn.style.backgroundColor = '#e74c3c'; btn.style.color = 'white';",
            "    overlay.style.background = 'rgba(231,76,60,0.92)';",
            "    var msg = (badMsgs && badMsgs[idx]) ? badMsgs[idx] : 'Mauvaise reponse !';",
            "    fbText.innerText = msg;",
            "  }",
            "  overlay.style.display = 'flex';",
            "  setTimeout(function() { window.location.href = '/quiz/answer/' + idx + '?t=' + new Date().getTime(); }, 3000);",
            "}",
            "</script></head><body>", HEADER_HTML,
            "<div id='feedback-overlay'><div id='feedback-text' style='color:white;'></div></div>",
            "<div class='container'>",
            "<br>"
            "<h1 style='flex-shrink:0; max-height:30%; overflow-y:auto; font-size:36px; margin:20px 0; margin-bottom:60px; color:white;'>" + q["text"] + "</h1>",
            "<div style='flex:1; display:flex; flex-wrap:wrap; align-content:flex-start; justify-content:center; width:100%; overflow-y:auto; padding-bottom:25px; gap:15px;'>"
        ]
        for i, ans in enumerate(q["answers"]):
            correct_idx = q["correct"]
            parts.append("<div class='btn btn-answer' style='margin:0; margin-right:10px; margin-bottom:10px; padding:10px; font-size:22px; min-height:80px; width:40%; border-radius:20px;' onclick='clickAns(this, " + str(i) + ", " + str(correct_idx) + ")'>" + ans + "</div>")
        parts.append("</div><p style='margin:5px 0; flex-shrink:0; font-size:20px;'>Question " + str(state.quiz_index + 1) + "/" + str(len(QUESTIONS)) + "</p>")
        parts.append("<a class='btn' href='/menu' style='margin-bottom:20px;'>Quitter</a></div></body></html>")

        if speak_question:
            threading.Thread(target=action_say, args=(_build_question_say_text(q),)).start()
        return "".join(parts)
    else:
        score_txt = str(state.quiz_score) + " sur " + str(len(QUESTIONS))
        parts = [
            "<html><head><meta charset='utf-8'>", COMMON_CSS, "</head><body>", HEADER_HTML,
            "<div class='container' style='justify-content:center; padding:100px 30px;'>",
            "<h1 style='font-size:36px; margin-bottom:20px;'>Quiz termin\u00e9 !</h1>",
            "<div style='font-size:70px; color:#2ecc71; font-weight:bold; margin:20px 0;'>" + score_txt + "</div>",
            "<p style='font-size:22px; max-width:80%; line-height:1.6; margin:20px auto;'>" + QUIZ_END_TEXT.replace(". ", ".<br>") + "</p>",
            "<div style='display:flex; flex-direction:column; gap:20px; margin-top:20px;'>",
            "<a class='btn btn-green' href='/quiz/start' style='width:300px;' onclick=\"this.href='/quiz/start?t=' + new Date().getTime()\">Recommencer</a>",
            "<a class='btn' href='/menu' style='width:300px;'>Menu principal</a>",
            "</div></div></body></html>"
        ]
        threading.Thread(target=action_say, args=(QUIZ_END_TEXT,)).start()
        return "".join(parts)

def action_say(text):
    """Dit un texte via le robot (bloquant). Appeler dans un thread."""
    if session_global and qi:
        try:
            tts = session_global.service("ALTextToSpeech")
            print("[ROBOT] Say: " + text)
            tts.say(str(text))
        except: pass

def action_say_then(text1, text2):
    """Dit text1, puis text2 sequentiellement (feedback puis question suivante)."""
    if session_global and qi:
        try:
            tts = session_global.service("ALTextToSpeech")
            print("[ROBOT] Say feedback: " + text1)
            tts.say(str(text1))
            time.sleep(0.5)
            print("[ROBOT] Say question: " + text2)
            tts.say(str(text2))
        except: pass

def action_animation(animation_id):
    anim = PEPPER_ANIMATION_BY_ID.get(animation_id)
    if not anim:
        return
    if session_global and qi:
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

            # 1. Racine → menu principal directement
            if self.path == "/" or self.path == "/index.html":
                set_app_mode("chat")
                self.send_response(302)
                self.send_header("Location", "/menu")
                self.end_headers()
                return

            # 2. Fichiers statiques (Images globales)
            if self.path.startswith("/images/"):
                fpath = self.path[1:]
                if ".." in fpath: return
                if os.path.exists(fpath):
                    self.send_response(200)
                    self.send_header("Cache-Control", "public, max-age=86400")
                    if fpath.endswith(".css"): self.send_header("Content-type", "text/css")
                    elif fpath.endswith(".js"): self.send_header("Content-type", "application/javascript")
                    elif fpath.endswith(".png"): self.send_header("Content-type", "image/png")
                    elif fpath.endswith(".jpg") or fpath.endswith(".jpeg"): self.send_header("Content-type", "image/jpeg")
                    elif fpath.endswith(".webp"): self.send_header("Content-type", "image/webp")
                    self.end_headers()
                    with open(fpath, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            # 3. Fichiers statiques du module VEOLIA
            if self.path.startswith("/veolia/"):
                fpath = self.path[1:] # Retire le premier '/'
                if ".." in fpath: return
                if os.path.exists(fpath) and os.path.isfile(fpath):
                    
                    # --- GESTION DE L'IA DANS LES PRESENTATIONS ---
                    # Des qu'une page HTML de Veolia est chargee, on force l'IA a s'allumer
                    if fpath.endswith(".html") or "." not in fpath:
                        set_app_mode("chat")
                    # ----------------------------------------------

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

            # 4. Polling chat IA
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
            
            # 5. Pages de l'application Pepper (Menu, Chat, Quiz)
            content = ""
            if self.path == "/menu": 
                set_app_mode("chat") # IA active sur le menu principal
                content = render_menu()
                
            elif self.path.startswith("/ai_module"): 
                state.chat_status = "waiting"
                set_app_mode("chat") # IA active dans la page chat
                content = render_chat()
                
            elif self.path.startswith("/quiz"):
                set_app_mode("quiz") # SEUL ENDROIT OU L'IA EST COUPEE !
                
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
                        next_q_text = ""
                        if state.quiz_index < len(QUESTIONS):
                            next_q_text = _build_question_say_text(QUESTIONS[state.quiz_index])
                        if next_q_text:
                            threading.Thread(target=action_say_then, args=(say_txt, next_q_text)).start()
                        else:
                            threading.Thread(target=action_say, args=(say_txt,)).start()
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
                    content = render_animations(anim["icon"] + " " + anim["label"] + " en cours...")
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
                # Compatibilite ancienne version (POST) — redirige vers la logique GET
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
                
                # Detection IP PC pour l'URL
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
