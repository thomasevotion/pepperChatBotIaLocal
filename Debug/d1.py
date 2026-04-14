# -*- coding: utf-8 -*-
import sys
import os
import time
import socket
import threading
import argparse
import json
import random

# Gestion compatibilite Python 2 / Python 3
try:
    import SimpleHTTPServer
    import SocketServer
except ImportError:
    import http.server as SimpleHTTPServer
    import socketserver as SocketServer

# Patch performance Windows : Desactiver la resolution DNS inverse
import BaseHTTPServer
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

# --- CONFIGURATION ---
PORT = 9090

# --- DONNEES QUIZ ---
QUESTIONS = [
    {
        "text": "Quand on parle de “Machine Learning”, ça veut dire que :", 
        "answers": ["Le robot apprend tout seul comme un humain", "Le robot apprend grâce aux données qu’on lui donne", "Le robot devient plus intelligent chaque nuit", "Le robot télécharge des compétences sur Internet"], 
        "correct": 1,
        "feedback_correct": "Exact. Les données, c’est mon carburant. Sans elles, je suis juste un grille-pain évolué.",
        "feedback_wrong": "Pas tout à fait… mais j’apprécie la créativité humaine."
    },
    {
        "text": "Quel est le rôle principal d’un algorithme en IA ?", 
        "answers": ["Donner une personnalité au robot", "Décorer l’interface", "Permettre à la machine de prendre des décisions ou faire des calculs", "Contrôler la batterie"], 
        "correct": 2,
        "feedback_correct": "Bravo, petit génie !",
        "feedback_wrong": "Ce n’est pas ça… mais tu feras mieux à la troisième question"
    },
    {
        "text": "C’est quoi un \"deepfake\" ?", 
        "answers": ["Une IA qui dort profondément", "Une vidéo ou image modifiée grâce à l’IA", "Un robot espion", "Un filtre TikTok officiel"], 
        "correct": 1,
        "feedback_correct": "Bravo. Tu es officiellement résistant à la désinformation.",
        "feedback_wrong": "Non… mais rassure-toi, beaucoup tombent dans le piège."
    },
    {
        "text": "Quand une IA se trompe complètement, on appelle souvent ça :", 
        "answers": ["Un bug émotionnel", "Une crise existentielle", "Une surcharge Wi-Fi", "Une hallucination"], 
        "correct": 3,
        "feedback_correct": "Exact. Même les intelligences artificielles peuvent se tromper.",
        "feedback_wrong": "Erreur détectée… mais tu restes humain, donc ça passe."
    }
]

# --- ETAT GLOBAL (STORE) ---
class GameState:
    def __init__(self):
        # Quiz
        self.quiz_index = 0
        self.quiz_score = 0
        # Chat
        self.chat_history = [] # List of {"role": "user"/"robot", "text": "..."}
        self.chat_status = "waiting"

    def reset_quiz(self):
        self.quiz_index = 0
        self.quiz_score = 0

state = GameState()
session_global = None
lock = threading.Lock()

# --- HELPER CSS & HTML ---
HEADER_HTML = """
<div style="position:fixed; top:0; left:0; width:100%; height:80px; background:#ededed; z-index:1000; display:flex; align-items:center; justify-content:space-between; padding:0 20px; box-sizing:border-box; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
    <a href="/"><img src="/images/Robot.png" style="height:60px;"></a>
    <div style="display:flex;">
        <a href="/"><img src="https://cdn-icons-png.flaticon.com/512/25/25694.png" style="height:50px; opacity:0.7;"></a>
        <img src="https://cdn-icons-png.flaticon.com/512/56/56763.png" style="height:50px; opacity:0.7; cursor:pointer; margin-left: 60px;" onclick="toggleVolumeOverlay()">
    </div>
</div>

<!-- VOLUME OVERLAY -->
<div id="volume-overlay" style="display:none; position:fixed; top:0; right:0; width:300px; height:100%; background:rgba(80,80,80,0.95); z-index:2000; color:white; flex-direction:column; align-items:center; padding-top:20px;">
    <h3>Gestion du volume</h3>
    <div style="display:flex; align-items:center; margin:20px 0;">
        <div onclick="changeVolume(10)" style="font-size:40px; cursor:pointer; background:white; color:#333; width:50px; height:50px; border-radius:50%; display:flex; justify-content:center; align-items:center; margin-right: 30px;">+</div>
        <div id="vol-display" style="font-size:50px; font-weight:bold; margin-right: 30px;">70</div>
        <div onclick="changeVolume(-10)" style="font-size:40px; cursor:pointer; background:white; color:#333; width:50px; height:50px; border-radius:50%; display:flex; justify-content:center; align-items:center;">-</div>
    </div>
    <br>
    <div style="display:flex; flex-direction:column; align-items:flex-start; margin-top:30px; padding-left: 20px;">
        <label style="display:flex; align-items:center; font-size:24px; margin-bottom: 30px;">
            <input type="checkbox" id="mute-robot" style="width:40px; height:40px; margin-right: 20px;" onchange="toggleMute()"> <span>Couper le son<br>du robot</span>
        </label>
        
        <label style="display:flex; align-items:center; font-size:24px;">
            <input type="checkbox" id="mute-recog" style="width:40px; height:40px; margin-right: 20px;" onchange="toggleRecog()"> <span>Désactiver la<br>reconnaissance<br>vocale</span>
        </label>
    </div>

    <div onclick="toggleVolumeOverlay()" style="margin-top:auto; margin-bottom:40px; background:#ededed; color:#333; padding:15px 40px; border-radius:30px; font-size:24px; font-weight:bold; cursor:pointer;">Fermer</div>
</div>

<script>
    function toggleVolumeOverlay() {
        var el = document.getElementById('volume-overlay');
        el.style.display = (el.style.display === 'none') ? 'flex' : 'none';
    }
    
    function changeVolume(delta) {
        var volEl = document.getElementById('vol-display');
        var current = parseInt(volEl.innerText);
        var newVol = Math.max(0, Math.min(100, current + delta));
        volEl.innerText = newVol;
        sendVolumeCmd(newVol);
    }

    function toggleMute() {
        var muted = document.getElementById('mute-robot').checked;
        sendVolumeCmd(muted ? 0 : parseInt(document.getElementById('vol-display').innerText));
    }

    function toggleRecog() {
        var disabled = document.getElementById('mute-recog').checked;
        // Send command to disable recognition (not implemented in backend yet but UI is ready)
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/set_recog', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.send(JSON.stringify({disabled: disabled}));
    }

    function sendVolumeCmd(vol) {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/set_volume', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.send(JSON.stringify({volume: vol}));
    }
</script>
"""

COMMON_CSS = """
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; text-align: center; background: linear-gradient(135deg, #614d98 0%, #5E9bd4 100%); margin: 0; padding: 0; color: white; -webkit-user-select: none; overflow: hidden; width: 100%; height: 100%; position: fixed; }
    h1 { color: #474747; font-size: 40px; margin: 20px 0; text-shadow: none; }
    .container { max-width: 1280px; height: 100%; margin: 0 auto; padding-top: 80px; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; }
    .btn { 
        display: inline-flex; align-items: center; justify-content: center;
        background: #ecf0f1; border: none; border-radius: 30px;
        padding: 15px 30px; margin: 10px; font-size: 20px; color: #333; text-decoration: none; 
        box-shadow: 0 5px 15px rgba(0,0,0,0.2); cursor: pointer; font-weight: bold;
        transition: transform 0.1s;
    }
    .btn:active { transform: scale(0.95); background: #bdc3c7; }
    
    /* Couleurs */
    .btn-green { background: #2ecc71; color: white; }
    .btn-green:active { background: #27ae60; }
    .btn-red { background: #e74c3c; color: white; }
    
    .btn-menu { width: 250px; height: 70px; font-size: 24px; text-transform: uppercase; letter-spacing: 1px; }
    
    /* Chat specific */
    .chat-container { display: flex; flex-direction: column; gap: 15px; padding: 15px; width: 90%; flex: 1; min-height: 0; overflow-y: auto; }
    .bubble { padding: 15px; border-radius: 15px; background: #ededed; color: #474747; font-size: 20px; text-align: left; box-shadow: 0 2px 5px rgba(0,0,0,0.1); position: relative; font-weight: bold; }
    
    .user-bubble { align-self: flex-start; margin-right: 20%; border-left: 10px solid #ff4081; }
    .robot-bubble { align-self: flex-end; margin-left: 20%; text-align: right; border-right: 10px solid #00e676; }
    
    .status-bar { padding: 10px; font-size: 20px; font-weight: bold; color: #474747; background: #e0e0e0; border-radius: 30px; margin-top: 5px; margin-bottom: 5px; width: 60%; flex-shrink: 0; box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
    .status-listening { background: #00e676; color: white; }
    .status-speaking { background: #DB737E; color: white; } /* Couleur saumon/rouge du screenshot */
    .status-waiting { background: #bdc3c7; color: #333; }
</style>
"""

# --- GENERATEURS DE PAGES ---

def render_menu():
    html = "<html><head>" + COMMON_CSS + "</head><body>" + HEADER_HTML
    html += "<div class='container' style='justify-content:center; padding-top: 80px;'>"
    html += "<h1 style='color:white; font-size:32px; margin-bottom:10px;'>Hello ! Je suis Pepper, que puis-je faire pour toi ?</h1>"
    html += "<div style='display:flex; justify-content:center; gap:20px; width:100%; align-items:center; height: 50%;'>"
    html += "<a class='btn btn-menu' href='/quiz/start' style='width: 220px; height: 60px; font-size: 20px; padding: 10px; white-space: nowrap;'>JOUONS AU QUIZ</a>"
    html += "<img src='/images/pepperwebMenu.webp' style='height:100%; max-height: 250px; object-fit: contain; flex-shrink: 1; min-width: 100px;'>"
    html += "<a class='btn btn-menu' href='/chat' style='width: 220px; height: 60px; font-size: 20px; padding: 10px; white-space: nowrap;'>IA CHAT</a>"
    html += "</div></div></body></html>"
    return html

def render_chat():
    html = "<html><head>" + COMMON_CSS + """
    <script>
        var lastLen = """ + str(len(state.chat_history)) + """;
        var lastStatus = "";

        function startPolling() {
            setInterval(function() {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/poll', true);
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4 && xhr.status === 200) {
                        try {
                            var data = JSON.parse(xhr.responseText);
                            var history = data.history;
                            var container = document.getElementById('chat-container');
                            
                            if (history && history.length > lastLen) {
                                for (var i = lastLen; i < history.length; i++) {
                                    var msg = history[i];
                                    var div = document.createElement('div');
                                    div.className = 'bubble ' + (msg.role === 'user' ? 'user-bubble' : 'robot-bubble');
                                    div.textContent = msg.text;
                                    container.appendChild(div);
                                }
                                lastLen = history.length;
                                container.scrollTop = container.scrollHeight;
                            }
                            // Fallback pour mise a jour du dernier message si necessaire
                            else if (history && history.length > 0) {
                                var lastMsg = history[history.length - 1];
                                var lastBubble = container.lastElementChild;
                                if (lastBubble && lastBubble.textContent !== lastMsg.text) {
                                    lastBubble.textContent = lastMsg.text;
                                    container.scrollTop = container.scrollHeight;
                                }
                            }
                            
                            if (data.status && data.status !== lastStatus) {
                                var bar = document.getElementById('status-bar');
                                bar.className = "status-bar"; // Reset
                                if(data.status === "listening") {
                                    bar.classList.add("status-listening");
                                    bar.textContent = "Je vous écoute (Parlez !)";
                                } else if(data.status === "robot_speaking") {
                                    bar.classList.add("status-speaking");
                                    bar.textContent = "Je parle...";
                                } else if(data.status === "waiting") {
                                    bar.classList.add("status-waiting");
                                    bar.textContent = "Un instant...";
                                }
                                lastStatus = data.status;
                            }
                        } catch(e) {}
                    }
                };
                xhr.send();
            }, 500);
        }
        
        // Notifier le serveur qu'on est en mode CHAT
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/set_mode', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.send(JSON.stringify({mode: 'chat'}));
        
        window.onload = startPolling;
    </script>
    </head><body>""" + HEADER_HTML
    html += "<div class='container'>"
    html += "<h1 style='color:white;'>Discute avec mon IA ultra perfectionnée !</h1>"
    html += "<div class='chat-container' id='chat-container'>"
    # Render existing history
    for msg in state.chat_history:
        role_class = "user-bubble" if msg["role"] == "user" else "robot-bubble"
        html += "<div class='bubble " + role_class + "'>" + msg["text"] + "</div>"
    
    html += "</div>"
    html += "<div class='status-bar status-listening' id='status-bar' style='margin-bottom: 20px;'>Je vous écoute</div>"
    html += "</div></body></html>"
    return html

def render_quiz():
    if state.quiz_index < len(QUESTIONS):
        q = QUESTIONS[state.quiz_index]
        html = "<html><head>" + COMMON_CSS + """
        <style>
            .btn-answer { width: 45%; font-size: 28px; min-height: 100px; }
            .correct-click { background: #2ecc71 !important; color: white !important; border-color: #27ae60 !important; }
            .wrong-click { background: #e74c3c !important; color: white !important; border-color: #c0392b !important; }
        </style>
        <script>
            var answered = false;
            function clickAns(btn, idx, correctIdx) {
                if (answered) return;
                answered = true;
                
                // Desactiver tous les boutons
                var btns = document.getElementsByClassName('btn-answer');
                for(var i=0; i<btns.length; i++) {
                    btns[i].style.pointerEvents = 'none';
                    btns[i].style.opacity = '0.7';
                }
                btn.style.opacity = '1';

                if (idx == correctIdx) {
                    btn.className += " correct-click";
                } else {
                    btn.className += " wrong-click";
                    // Montrer la bonne reponse aussi
                    btns[correctIdx].className += " correct-click";
                    btns[correctIdx].style.opacity = '1';
                }
                
                // Envoyer la reponse au serveur pour qu'il parle et mette a jour le score
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/quiz/process_answer?ans=' + idx, true);
                xhr.send();

                // Attendre que le robot finisse de parler (5s) avant de passer a la suite
                setTimeout(function() {
                    window.location.href = "/quiz/next";
                }, 5000);
            }
            // Notifier mode QUIZ
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/set_mode', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.send(JSON.stringify({mode: 'quiz'}));
        </script>
        </head><body>""" + HEADER_HTML
        
        html += "<div class='container'>"
        html += "<h1 style='flex-shrink: 0; max-height: 25%; overflow-y: auto; font-size: 38px; margin: 20px 0; margin-top:70px; color:white; padding: 0 20px;'>" + q["text"] + "</h1>"
        html += "<div style='flex: 1; display: flex; flex-wrap: wrap; align-content: center; justify-content: center; width: 100%; overflow-y: auto; padding-bottom: 5px; gap: 20px;'>"
        for i, ans in enumerate(q["answers"]):
            correct_idx = q["correct"]
            html += "<div class='btn btn-answer' style='margin: 10px; padding: 15px; font-size: 20px; min-height: 60px; width: 40%; border-radius:20px; display:flex; align-items:center; justify-content:center;' onclick='clickAns(this, "+str(i)+", "+str(correct_idx)+")'>" + ans + "</div>"
        html += "</div>"
        html += "<p style='margin: 5px 0; margin-bottom: 20px; flex-shrink: 0; font-size:18px;'>Question " + str(state.quiz_index+1) + "/" + str(len(QUESTIONS)) + "</p>"
        html += "</div></body></html>"
        threading.Thread(target=action_say, args=(q.get("text_spoken", q["text"]),)).start()
        return html
    else:
        html = "<html><head>" + COMMON_CSS + "</head><body>" + HEADER_HTML
        html += "<div class='container' style='justify-content: center;'>"
        html += "<h1 style='color:white; font-size:40px;'>Bravo ! Le quiz est terminé. Voici votre score :</h1>"
        html += "<div style='font-size:60px; color:white; font-weight:bold; margin: 35px 0;'>" + str(state.quiz_score) + " / " + str(len(QUESTIONS)) + " bonne(s) réponse(s)</div>"
        html += "<div style='display:flex; flex-direction:column; gap:20px;'>"
        html += "<a class='btn' href='/quiz/start' style='width:300px;'>Recommencer</a>"
        html += "<a class='btn' href='/' style='width:300px;'>Menu principal</a>"
        html += "</div></div></body></html>"
        threading.Thread(target=action_say, args=("Bravo, tu as fini le quiz.",)).start()
        return html

def render_feedback(ans_idx):
    # Cette fonction n'est plus utilisee car on reste sur la meme page
    pass

# --- ACTIONS ROBOT ---
def action_say(text):
    if session_global:
        try:
            print("[ROBOT] Say: " + text)
            session_global.service("ALTextToSpeech").say(text)
        except: pass

# --- SERVEUR WEB ---
class AppHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Gestion des fichiers statiques
        if self.path.startswith("/images/") or self.path.startswith("/module_chess/"):
            try:
                fpath = self.path[1:]
                if ".." in fpath: return
                if os.path.exists(fpath):
                    self.send_response(200)
                    self.send_header("Cache-Control", "public, max-age=86400")
                    if fpath.endswith(".css"): self.send_header("Content-type", "text/css")
                    elif fpath.endswith(".js"): self.send_header("Content-type", "application/javascript")
                    elif fpath.endswith(".png"): self.send_header("Content-type", "image/png")
                    elif fpath.endswith(".jpg"): self.send_header("Content-type", "image/jpeg")
                    self.end_headers()
                    with open(fpath, 'rb') as f:
                        self.wfile.write(f.read())
                    return
            except: pass
            
        # --- API CHAT (POLLING) ---
        if self.path == '/poll':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            data = {
                "history": state.chat_history,
                "status": state.chat_status
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        # --- ROUTAGE DYNAMIQUE ---
        with lock:
            if self.path == "/" or self.path == "/menu":
                self.send_html(render_menu())
                return

            if self.path == "/chat":
                # On ne reset PAS l'affichage ici, on laisse le polling recuperer l'etat reel
                # state.chat_user = "..." 
                # state.chat_robot = "Bonjour ! Je t'écoute."
                self.send_html(render_chat())
                return

            if "/quiz" in self.path:
                if "/start" in self.path:
                    state.reset_quiz()
                    self.send_html(render_quiz())
                    return
                elif "/process_answer" in self.path:
                    try:
                        ans_idx = int(self.path.split("ans=")[1].split("&")[0])
                        q = QUESTIONS[state.quiz_index]
                        is_correct = (ans_idx == q["correct"])
                        
                        if is_correct:
                            state.quiz_score += 1
                            threading.Thread(target=action_say, args=(q["feedback_correct"],)).start()
                        else:
                            threading.Thread(target=action_say, args=(q["feedback_wrong"],)).start()
                        
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"OK")
                        return
                    except: pass
                elif "/next" in self.path:
                    state.quiz_index += 1
                    self.send_html(render_quiz())
                    return
                
                self.send_html(render_quiz())
                return

            if "/chess" in self.path:
                self.send_html(render_chess())
                return
            
            if "/run/" in self.path:
                if "chess_move" in self.path:
                    try:
                        move = self.path.split("move=")[1]
                        threading.Thread(target=action_say, args=("Ah, tu joues " + move,)).start()
                    except: pass
                elif "chess_robot_played" in self.path:
                    threading.Thread(target=action_say, args=("C'est mon coup.",)).start()
                self.send_response(200)
                self.end_headers()
                return

        self.send_html(render_menu())

    def do_HEAD(self):
        # Meme logique que GET mais sans le corps
        # On force 200 OK pour tout le monde pour eviter les 404
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

    def do_POST(self):
        if self.path == '/update':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                
                with lock:
                    if 'user' in data: 
                        # Si le dernier message etait deja un user, on le remplace (correction d'erreur ou mise a jour)
                        if state.chat_history and state.chat_history[-1]["role"] == "user":
                            state.chat_history[-1]["text"] = data['user']
                        else:
                            state.chat_history.append({"role": "user", "text": data['user']})
                            
                    if 'robot' in data: 
                        # Si le dernier message etait deja un robot, on le met a jour (streaming)
                        if state.chat_history and state.chat_history[-1]["role"] == "robot":
                            state.chat_history[-1]["text"] = data['robot']
                        else:
                            state.chat_history.append({"role": "robot", "text": data['robot']})
                            
                    if 'status' in data: state.chat_status = data['status']
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                print("Erreur POST: " + str(e))
                self.send_response(400)
                self.end_headers()
                
        elif self.path == '/set_volume':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                vol = data.get('volume', 70)
                print("[VOLUME] Changement demande : " + str(vol))
                
                if session_global:
                    try:
                        audio = session_global.service("ALAudioDevice")
                        audio.setOutputVolume(vol)
                    except Exception as e:
                         print("[NAOQI] Erreur volume : " + str(e))

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                print("Erreur POST /set_volume: " + str(e))
                self.send_response(400)
                self.end_headers()

        elif self.path == '/set_recog':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                disabled = data.get('disabled', False)
                print("[RECOG] Changement demande : " + str(disabled))
                
                # Note: La desactivation reelle de la reco vocale depend de l'architecture
                # Ici on envoie juste un event que le module de dialogue peut ecouter
                if session_global:
                    try:
                        mem = session_global.service("ALMemory")
                        mem.raiseEvent("Pepper/RecogDisabled", disabled)
                    except Exception as e:
                         print("[NAOQI] Erreur envoi event : " + str(e))

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                print("Erreur POST /set_recog: " + str(e))
                self.send_response(400)
                self.end_headers()
                
        elif self.path == '/set_mode':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                mode = data.get('mode', 'menu')
                print("[MODE] Changement demande : " + mode)
                
                if session_global:
                    try:
                        mem = session_global.service("ALMemory")
                        mem.raiseEvent("Pepper/AppMode", mode)
                    except Exception as e:
                         print("[NAOQI] Erreur envoi event : " + str(e))

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                print("Erreur POST /set_mode: " + str(e))
                self.send_response(400)
                self.end_headers()

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        if isinstance(content, str):
            self.wfile.write(content)
        else:
            self.wfile.write(content.encode('utf-8'))

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True

def main():
    # FORCE LE DOSSIER DE TRAVAIL
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print("[WEB] Dossier de travail : " + script_dir)

    # Detection IP PC
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
    except:
        my_ip = "127.0.0.1"
    s.close()
    print("[INFO] IP du PC detectee : " + my_ip)
    print("[INFO] Si cette IP n'est pas accessible par le robot, verifiez votre Pare-feu !")

    parser = argparse.ArgumentParser()
    parser.add_argument('--ip', required=True)
    args = parser.parse_args()

    global session_global
    if qi:
        try:
            session_global = qi.Session()
            session_global.connect("tcp://" + args.ip + ":9559")
            print("[NAOQI] Connecte.")
            
            try:
                tab = session_global.service("ALTabletService")
                url = "http://{}:{}/".format(my_ip, PORT)
                print("--> Envoi URL tablette : " + url)
                tab.showWebview(url)
            except Exception as e:
                print("Erreur Tablette: " + str(e))
        except:
            print("Erreur connexion NAOqi.")
    
    server = ThreadedHTTPServer(("", PORT), AppHandler)
    print("Serveur lance sur port " + str(PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()