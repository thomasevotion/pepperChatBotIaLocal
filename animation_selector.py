# -*- coding: utf-8 -*-
# Selection d'animations Pepper a partir de animations_map.json (seule source de verite,
# genere une fois depuis animations.md par un script ponctuel - ne jamais reparser le .md ici).
#
# Les demandes explicites ("prends une photo", "montre tes muscles") ET les reactions
# emotionnelles sont choisies ensemble par le LLM, dans le meme appel Gemini que la reponse
# parlee (voir oaichat/openaichat.py, qui recoit le catalogue tag/description_courte dans son
# prompt systeme et renvoie un emotion_tag contraint par response_schema). Ce module se
# contente de valider ce tag (is_valid_tag, defense en profondeur) avant de le jouer.

import io
import json
import os
import random
import threading

from naoqi import ALProxy

_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "animations_map.json")

with io.open(_MAP_PATH, encoding="utf-8") as _f:
    _DATA = json.load(_f)

ANIMATIONS = _DATA["animations"]
IDLE_POOL = _DATA["idle_pool"]
BY_TAG = dict((a["tag"], a) for a in ANIMATIONS)

# Animations qu'on ne propose jamais en reaction automatique (reservees a l'inactivite 300s).
_IDLE_SET = set(IDLE_POOL)


def is_valid_tag(tag, exclude_idle=True):
    """Verifie qu'un emotion_tag renvoye par le LLM existe reellement dans animations_map.json
    (defense en profondeur : le LLM peut halluciner un tag hors catalogue). Par defaut, rejette
    aussi les tags du pool d'inactivite (reserves a la logique 300s, jamais une reaction du LLM)."""
    if not tag or tag not in BY_TAG:
        return False
    if exclude_idle and tag in _IDLE_SET:
        return False
    return True


def get_full_path(tag):
    entry = BY_TAG.get(tag)
    return entry["full_path"] if entry else None


def play_animation(nao_ip, nao_port, tag):
    """Joue une animation de facon BLOQUANTE. L'appelant doit la lancer dans un thread
    (comme pour wave()/dance() dans module_dialogue.py) pour qu'elle demarre en parallele du TTS."""
    path = get_full_path(tag)
    if not path:
        print(u"[ANIM] Tag inconnu: " + repr(tag))
        return
    if isinstance(path, unicode):
        path = path.encode("utf-8")
    try:
        anim = ALProxy("ALAnimationPlayer", nao_ip, nao_port)
        anim.run(path)
    except Exception as e:
        print(u"[ANIM] Erreur lecture '{}': {}".format(tag, str(e)))


def play_animation_async(nao_ip, nao_port, tag):
    """Variante non-bloquante pratique : demarre play_animation dans un thread daemon."""
    t = threading.Thread(target=play_animation, args=(nao_ip, nao_port, tag))
    t.daemon = True
    t.start()
    return t


def pick_idle_animation():
    """Choisit aleatoirement une animation de la logique d'inactivite 300s (Bored_2,
    AskForAttention_1/2/3, ComeOn_1, KnockEye_1, Robot_1). Ne change pas la logique existante,
    fournit juste le tirage a partir de la meme liste que animations.md."""
    return random.choice(IDLE_POOL)
