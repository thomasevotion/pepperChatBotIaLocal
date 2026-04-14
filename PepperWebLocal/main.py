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

# Fonction globale pour gerer l'etat de l'IA proprement
def set_app_mode(mode):
    global session_global
    if session_global:
        try:
            session_global.service("ALMemory").raiseEvent("PepperAppMode", str(mode))
        except:
            pass

HEADER_HTML = """
<div style="position:fixed; top:0; left:0; width:100%; height:80px; background:#ededed; z-index:1000; display:flex; align-items:center; justify-content:space-between; padding:0 20px; box-sizing:border-box; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
    <a href="/menu"><img src="/images/EvotionLogo.png" style="height:60px;" onerror="this.style.display='none'"></a>
    <div style="display:flex; gap:40px; margin-right:20px; align-items:center;">
        <a href="/menu"><img src="/images/25694.png" style="height:50px; opacity:0.7;" onerror="this.src='https://cdn-icons-png.flaticon.com/512/25/25694.png'"></a>
        <img src="/images/56763.png" style="height:50px; opacity:0.7; cursor:pointer;" onclick="toggleVolumeOverlay()" onerror="this.src='https://cdn-icons-png.flaticon.com/512/56/56763.png'">
    </div>
</div>

<!-- MENU BURGER : VOLUME OVERLAY -->
<div id="volume-overlay" style="display:none; position:fixed; top:0; right:0; width:300px; height:100%; background:rgba(80,80,80,0.95); z-index:2000; color:white; flex-direction:column; align-items:center; padding-top:20px;">
    <h3>Gestion du volume</h3>
    <div style="display:flex; align-items:center; justify-content:center; margin:20px 0;">
        <div onclick="changeVolume(10)" style="font-size:40px; cursor:pointer; background:white; color:#333; width:50px; height:50px; border-radius:50%; display:flex; justify-content:center; align-items:center;">+</div>
        <div id="vol-display" style="font-size:50px; font-weight:bold; margin:0 20px;">70</div>
        <div onclick="changeVolume(-10)" style="font-size:40px; cursor:pointer; background:white; color:#333; width:50px; height:50px; border-radius:50%; display:flex; justify-content:center; align-items:center;">-</div>
    </div>
    <div style="display:flex; flex-direction:column; align-items:flex-start; margin-top:30px; padding:0 20px; width:100%; box-sizing:border-box;">
        <label style="display:flex; align-items:center; font-size:20px; margin-bottom:30px; cursor:pointer; text-align:left;">
            <input type="checkbox" id="mute-robot" style="width:30px; height:30px; margin-right:20px;" onchange="toggleMute()">
            Couper le son<br>du robot
        </label>
        <label style="display:flex; align-items:center; font-size:20px; cursor:pointer; text-align:left;">
            <input type="checkbox" id="mute-recog" style="width:30px; height:30px; margin-right:20px;" onchange="toggleRecog()">
            Désactiver la<br>reconnaissance<br>vocale
        </label>
    </div>
    <div onclick="toggleVolumeOverlay()" style="margin-top:auto; margin-bottom:40px; background:#ededed; color:#333; padding:15px 40px; border-radius:30px; font-size:24px; font-weight:bold; cursor:pointer;">Fermer</div>
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
"""

COMMON_CSS = """
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; text-align: center; background: linear-gradient(135deg, #614d98 0%, #5E9bd4 100%); margin: 0; padding: 0; color: white; -webkit-user-select: none; overflow: hidden; width: 100%; height: 100vh; position: fixed; }
    h1 { color: white; font-size: 40px; margin: 20px 0; text-shadow: none; }
    .container { width: 100%; height: 100vh; margin: 0 auto; padding-top: 80px; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; overflow: hidden; }
    .btn { display: inline-flex; align-items: center; justify-content: center; background: #ecf0f1; border: none; border-radius: 30px; padding: 15px 30px; margin: 10px; font-size: 20px; color: #333; text-decoration: none; box-shadow: 0 5px 15px rgba(0,0,0,0.2); cursor: pointer; font-weight: bold; transition: transform 0.1s; }
    .btn:active { transform: scale(0.95); background: #bdc3c7; }
    .btn-green { background: #2ecc71; color: white; }
    .btn-red { background: #e74c3c; color: white; }
    .btn-menu { width: 280px; height: 80px; font-size: 26px; text-transform: uppercase; letter-spacing: 1px; }
    
    .chat-container { display: flex; flex-direction: column; gap: 15px; padding: 15px; width: 90%; flex: 1; min-height: 0; overflow-y: auto; background: rgba(255,255,255,0.1); border-radius: 20px; margin-bottom: 10px; }
    .bubble { padding: 15px; border-radius: 15px; background: #ededed; color: #474747; font-size: 20px; text-align: left; box-shadow: 0 2px 5px rgba(0,0,0,0.1); position: relative; font-weight: bold; }
    .user-bubble { align-self: flex-start; margin-right: 20%; border-left: 10px solid #ff4081; }
    .robot-bubble { align-self: flex-end; margin-left: 20%; text-align: right; border-right: 10px solid #00e676; }
    .status-bar { padding: 15px; font-size: 24px; font-weight: bold; color: white; background: #95a5a6; border-radius: 10px; margin-top: 10px; margin-bottom: 10px; width: 80%; flex-shrink: 0; }
    .status-listening { background: #00e676; }
    .status-speaking { background: #9c27b0; }
    .status-waiting { background: #bdc3c7; color: #333; }
</style>
"""

def render_menu():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS, "</head><body>", HEADER_HTML,
        "<div class='container'>",
        "<h1 style='font-size:45px; margin-top:45px; flex-shrink:0;'>Hello ! Je suis Inno,<br> que puis-je faire pour toi ?</h1>",
        "<div style='display:flex; flex-direction:row; align-items:center; justify-content:center; gap:80px; width:100%; flex:1;'>",
        "<div style='display:flex; flex-direction:column; gap:25px;'>",
        "<a class='btn btn-menu' href='/quiz/start'>JOUONS AU QUIZ</a>",
        "<a class='btn btn-menu' href='/ai_module'>IA CHAT</a>",
        "</div>",
        "<img src='/images/pepperwebMenu.webp' style='height:45vh; max-height:350px; object-fit:contain;' onerror=\"this.src='https://techcrunch.com/wp-content/uploads/2015/06/pepper.jpg'; this.style.borderRadius='20px'\">",
        "</div></div></body></html>"
    ]
    return "".join(parts)

def render_chat():
    parts = [
        "<html><head><meta charset='utf-8'>", COMMON_CSS,
        "<script>",
        "var lastStatus = '';",
        "function startPolling() {",
        "  setInterval(function() {",
        "    var xhr = new XMLHttpRequest();",
        "    xhr.open('GET', '/poll?t=' + new Date().getTime(), true);",
        "    xhr.onreadystatechange = function() {",
        "      if (xhr.readyState == 4 && xhr.status == 200) {",
        "        try {",
        "          var data = JSON.parse(xhr.responseText);",
        "          var container = document.getElementById('chat-container');",
        "          if (data.user && data.user !== '') {",
        "            var div = document.createElement('div');",
        "            div.className = 'bubble user-bubble';",
        "            div.innerHTML = data.user;",
        "            container.appendChild(div);",
        "            container.scrollTop = container.scrollHeight;",
        "          }",
        "          if (data.robot && data.robot !== '') {",
        "            var lastChild = container.lastChild;",
        "            while (lastChild && lastChild.nodeType !== 1) { lastChild = lastChild.previousSibling; }",
        "            if (lastChild && lastChild.className && lastChild.className.indexOf('robot-bubble') !== -1) {",
        "                lastChild.innerHTML = data.robot;",
        "            } else {",
        "                var divR = document.createElement('div');",
        "                divR.className = 'bubble robot-bubble';",
        "                divR.innerHTML = data.robot;",
        "                container.appendChild(divR);",
        "            }",
        "            container.scrollTop = container.scrollHeight;",
        "          }",
        "          if (data.status && data.status !== lastStatus) {",
        "            var bar = document.getElementById('status-bar');",
        "            if(data.status === 'listening') { bar.className = 'status-bar status-listening'; bar.innerHTML = 'Je vous ecoute / Parlez !'; }",
        "            else if(data.status === 'robotspeaking') { bar.className = 'status-bar status-speaking'; bar.innerHTML = 'Je parle...'; }",
        "            else { bar.className = 'status-bar status-waiting'; bar.innerHTML = 'Un instant...'; }",
        "            lastStatus = data.status;",
        "          }",
        "        } catch(e) {}",
        "      }",
        "    };",
        "    xhr.send();",
        "  }, 500);",
        "}",
        "window.onload = function() {",
        "  var c=document.getElementById('chat-container');",
        "  if(c) c.scrollTop=c.scrollHeight;",
        "  startPolling();",
        "};",
        "</script></head><body>", HEADER_HTML,
        "<div class='container'><h1>Discussion avec l'IA Pepper</h1>",
        "<div class='chat-container' id='chat-container'></div>",
        "<div class='status-bar status-waiting' id='status-bar'>Initialisation...</div>",
        "<a class='btn' href='/menu' style='margin-bottom:20px;'>Retour Menu</a>",
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
            "<h1 style='flex-shrink:0; max-height:30%; overflow-y:auto; font-size:36px; margin:20px 0; color:white;'>" + q["text"] + "</h1>",
            "<div style='flex:1; display:flex; flex-wrap:wrap; align-content:flex-start; justify-content:center; width:100%; overflow-y:auto; padding-bottom:10px; gap:15px;'>"
        ]
        for i, ans in enumerate(q["answers"]):
            correct_idx = q["correct"]
            parts.append("<div class='btn btn-answer' style='margin:0; margin-right:5px; margin-bottom:5px; padding:15px; font-size:22px; min-height:80px; width:40%; border-radius:20px;' onclick='clickAns(this, " + str(i) + ", " + str(correct_idx) + ")'>" + ans + "</div>")
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
