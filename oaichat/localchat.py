# -*- coding: utf-8 -*-

###########################################################
# Chat 100% local via Ollama (remplace Gemini, aucune donnee ne quitte le PC).
# Meme interface que OaiChat (openaichat.py) pour que oaiserver.py, oaiclient.py
# et module_dialogue.py fonctionnent sans modification :
#   respond(), respond_stream(), add_to_history(), reset(), last_emotion_tag
#
# Config (.env) :
#   OLLAMA_HOST          (defaut http://127.0.0.1:11434)
#   OLLAMA_MODEL         (defaut qwen3.5:9b : multilingue + vision (camera Pepper), meilleur
#                         compromis intelligence/vitesse qui tient dans 8 Go de VRAM avec Whisper)
#   OLLAMA_VISION_MODEL  (defaut = OLLAMA_MODEL. A renseigner seulement si OLLAMA_MODEL ne lit
#                         pas les images (ex: qwen3:8b -> gemma3:4b). "none" = image ignoree)
#   OLLAMA_THINK         (defaut false : la "reflexion" des modeles qwen ajouterait plusieurs
#                         secondes avant le 1er mot)
#   OLLAMA_KEEP_ALIVE    (defaut -1 : modele garde en VRAM en permanence)
###########################################################
import os, sys, re, json, base64, io
from collections import namedtuple
from datetime import datetime

import requests
import dotenv
dotenv.load_dotenv()

from oaichat.oairesponse import OaiResponse
from oaichat.chatcommon import (
    VALID_EMOTION_TAGS, EMOTION_JSON_INSTRUCTION, LANGUAGE_PRIORITY_INSTRUCTION,
    load_prompt, trim_history,
)

if sys.version_info[0] < 3:
    raise ImportError('Local Chat requires Python 3')

# 127.0.0.1 et pas "localhost" : sous Windows, localhost tente d'abord IPv6 (::1) alors qu'Ollama
# n'ecoute qu'en IPv4 -> ~2 s perdues a CHAQUE connexion (mesure : 2.02 s vs 0.002 s).
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3.5:9b')
OLLAMA_VISION_MODEL = os.getenv('OLLAMA_VISION_MODEL') or OLLAMA_MODEL
if OLLAMA_VISION_MODEL.lower() == 'none':
    OLLAMA_VISION_MODEL = ''
# Garde le modele charge en VRAM indefiniment : sinon Ollama le decharge apres 5 min
# d'inactivite et le tour suivant paie plusieurs secondes de rechargement.
# Ollama attend un entier (secondes, -1 = infini) ou une duree avec unite ("10m") : "-1" en
# chaine est refuse ("missing unit in duration").
OLLAMA_KEEP_ALIVE = os.getenv('OLLAMA_KEEP_ALIVE', '-1')
try:
    OLLAMA_KEEP_ALIVE = int(OLLAMA_KEEP_ALIVE)
except ValueError:
    pass

# Consignes propres a la sortie vocale locale : Gemini produisait peu d'emojis/markdown, les
# modeles locaux beaucoup, et module_dialogue.py:clean_for_speech ne retire pas les emojis.
SPOKEN_OUTPUT_INSTRUCTION = (
    u"\n\n---\n"
    u"Ta reponse est lue a voix haute par le robot : texte parle uniquement, sans emoji, sans "
    u"markdown, sans liste a puces, sans didascalies entre asterisques."
)

# Tour de dialogue principal en UNE seule requete : le modele ecrit d'abord le tag entre
# crochets sur sa propre ligne, puis la reponse parlee. Avec Gemini, le tag venait d'un 2e appel
# separe ; en local ca s'est revele plus lent : Ollama sert par defaut une requete a la fois
# (OLLAMA_NUM_PARALLEL=1), les deux appels se mettaient en file, et alterner deux prompts
# systeme differents invalidait le cache de prompt a chaque tour (mesure : 1er mot a 2.4-5.6 s
# contre ~0.4 s en requete unique).
EMOTION_TAG_FORMAT_INSTRUCTION = (
    u"\n\nFORMAT OBLIGATOIRE : commence TOUJOURS ta reponse par une premiere ligne contenant "
    u"uniquement le tag choisi entre crochets, par exemple [Emotions/Positive/Happy_1], ou [null] "
    u"si aucun tag ne convient. Puis, a la ligne suivante, ta reponse parlee. Le tag n'est jamais "
    u"prononce."
)

# Emojis et pictogrammes (les ideogrammes CJK, le coreen et l'arabe ne sont pas touches).
_EMOJI_RE = re.compile(
    u'[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF'
    u'\U0000FE0F\U0000200D\U000020E3\U0001F1E6-\U0001F1FF]+'
)

_TAG_MAX_PREFIX = 80

# oaiserver.py lit chunk.text (format Gemini) : on expose la meme forme.
Chunk = namedtuple('Chunk', ['text'])


def _think_option(model):
    # Le parametre "think" est refuse par Ollama pour les modeles sans mode reflexion (gemma3...).
    if not model.startswith(('qwen3', 'deepseek-r1', 'gpt-oss', 'magistral')):
        return {}
    v = os.getenv('OLLAMA_THINK', 'false')
    return {'think': v.strip().lower() in ('1', 'true', 'yes')}


def strip_emojis(text):
    return _EMOJI_RE.sub(u'', text)


_TAG_TOKEN_RE = re.compile(r'[A-Za-z]+(?:/[A-Za-z0-9_]+)+$')

# Le dernier segment de chaque tag est unique dans animations_map.json : permet de rattraper un
# chemin approximatif invente par le modele ("Emotions/Positive/Shocked_1" -> le vrai
# "Emotions/Negative/Shocked_1") au lieu de perdre l'animation.
_TAG_BY_NAME = {t.rsplit(u'/', 1)[-1].lower(): t for t in VALID_EMOTION_TAGS}


def _resolve_tag(candidate):
    if candidate in VALID_EMOTION_TAGS:
        return candidate
    return _TAG_BY_NAME.get(candidate.rsplit(u'/', 1)[-1].lower())


def split_emotion_tag(prefix):
    """'[Tag]\\nReponse' -> ('Tag' ou None, 'Reponse'). Un tag inconnu ou null donne None.

    Tolere les variantes observees en test (crochet oublie : "Waiting/AirGuitar_1] Woah",
    "null" nu sur la 1ere ligne) : dans tous les cas le tag est retire du texte, pour ne jamais
    etre prononce par le robot."""
    s = prefix.lstrip()
    nl = s.find(u'\n')
    first = s if nl < 0 else s[:nl]
    tail = u'' if nl < 0 else s[nl:]
    close = first.find(u']')
    if close >= 0:
        head, rest = first[:close + 1], first[close + 1:] + tail
    else:
        head, rest = first, tail
    candidate = head.strip().strip(u'[]').strip()
    if (candidate.lower() in (u'null', u'none') or _TAG_TOKEN_RE.match(candidate)
            or candidate.lower() in _TAG_BY_NAME):
        return _resolve_tag(candidate), rest.lstrip(u' \r\n')
    return None, prefix


def _may_still_be_tag(prefix):
    """Vrai tant que le debut du flux peut encore devenir un tag (on retient alors le texte)."""
    s = prefix.lstrip()
    return (u']' not in s and u'\n' not in s and u' ' not in s.lstrip(u'[').strip()
            and len(s) < _TAG_MAX_PREFIX)


class LocalChat:

    def __init__(self, user, prompt=None):
        self.log = None
        self.system_instruction = None
        self.dialogue_system_instruction = None
        self.last_emotion_tag = None
        # (texte livre, sortie brute du modele) du dernier respond_stream, voir add_to_history
        self._last_stream_output = None
        self.history = []
        self.session = requests.Session()
        self.reset(user, prompt)
        self._warmup()

    # ------------------------------------------------------------------ setup

    def reset(self, user, prompt=None):
        self.user = user
        self.system_instruction, self.history = self.loadPrompt(
            prompt or os.getenv('OPENAI_PROMPTFILE')
        )
        base = self.system_instruction or u"You are a helpful assistant."
        # Construit une seule fois : un prompt systeme identique d'un tour a l'autre permet a
        # Ollama de reutiliser son cache de prompt (seuls les nouveaux messages sont evalues).
        self.dialogue_system_instruction = (
            base + SPOKEN_OUTPUT_INSTRUCTION + EMOTION_JSON_INSTRUCTION
            + EMOTION_TAG_FORMAT_INSTRUCTION + LANGUAGE_PRIORITY_INSTRUCTION
        )

    def loadPrompt(self, promptFile):
        return load_prompt(promptFile)

    def _warmup(self):
        """Verifie qu'Ollama repond, charge le modele en VRAM et pre-remplit le cache avec le
        prompt systeme, pour que le premier tour de dialogue ne paie ni le chargement (~plusieurs
        secondes a froid) ni l'evaluation du long prompt persona."""
        try:
            tags = self.session.get(OLLAMA_HOST + '/api/tags', timeout=5).json()
            installed = {m.get('name') for m in tags.get('models', [])}
            for model in {OLLAMA_MODEL, OLLAMA_VISION_MODEL} - {''}:
                if model not in installed and (model + ':latest') not in installed:
                    print('WARNING: modele Ollama "{}" absent. Lancer : ollama pull {}'.format(model, model))
            if OLLAMA_MODEL not in installed and (OLLAMA_MODEL + ':latest') not in installed:
                return
            start = datetime.now()
            self._chat(
                self._build_messages(self.dialogue_system_instruction, u'Bonjour', with_history=False),
                options={'num_predict': 1},
            )
            print('Modele Ollama "{}" charge et prompt en cache en {}'.format(
                OLLAMA_MODEL, datetime.now() - start))
        except Exception as e:
            print('WARNING: Ollama injoignable sur {} ({}). Est-il lance ? (ollama serve)'.format(OLLAMA_HOST, e))

    # ---------------------------------------------------------------- history

    def resetRequestLog(self):
        pass

    def add_to_history(self, user_input, assistant_response):
        """Ajoute un echange complet a l'historique (utilise apres streaming).

        On y remet la sortie BRUTE du modele (tag "[...]" et emojis compris) plutot que le texte
        nettoye livre au robot : le prompt du tour suivant prolonge alors exactement la sequence
        deja en cache dans Ollama. Indispensable avec qwen3.5 (architecture hybride recurrente) :
        a la moindre difference le cache ne peut pas etre reutilise partiellement et tout le
        prompt persona (~3000 tokens) est re-evalue (~2 s de plus avant le 1er mot). Ca montre
        aussi au modele ses reponses precedentes au bon format, ce qui l'aide a le garder."""
        if self._last_stream_output and self._last_stream_output[0] == assistant_response:
            assistant_response = self._last_stream_output[1]
        self._last_stream_output = None
        self.history.append({'role': 'user', 'content': user_input})
        self.history.append({'role': 'assistant', 'content': assistant_response})
        self._trim_history()

    def _trim_history(self):
        trim_history(self.history)

    def _build_messages(self, system_prompt, inputText, image_data=None, with_history=True):
        messages = [{'role': 'system', 'content': system_prompt}]
        if with_history:
            self._trim_history()
            for msg in self.history:
                if msg.get('role') in ('user', 'assistant') and msg.get('content'):
                    messages.append({'role': msg['role'], 'content': msg['content']})
        user_msg = {'role': 'user', 'content': inputText}
        image_b64 = self._encode_image(image_data) if image_data and OLLAMA_VISION_MODEL else None
        if image_b64:
            user_msg['images'] = [image_b64]
            print('Image camera incluse dans la requete Ollama ({}x{})'.format(
                image_data['width'], image_data['height']))
        messages.append(user_msg)
        return messages

    def _encode_image(self, image_data):
        """Image NaoQI (BGR/RGB brut en base64) -> JPEG base64 attendu par Ollama."""
        try:
            from PIL import Image
            raw_bytes = base64.b64decode(image_data['raw'])
            w, h = int(image_data['width']), int(image_data['height'])
            if image_data.get('mode', 'BGR') == 'BGR':
                img = Image.frombytes('RGB', (w, h), raw_bytes, 'raw', 'BGR')
            else:
                img = Image.frombytes('RGB', (w, h), raw_bytes)
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            return base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception as e:
            print('Warning: impossible de decoder image camera: ' + str(e))
            return None

    # ------------------------------------------------------------------ calls

    @staticmethod
    def _keep_alive_for(model):
        """Le modele de dialogue reste en VRAM en permanence ; un modele vision distinct (tours
        avec image, rares) est libere apres 1 min pour ne pas priver Whisper de VRAM."""
        if model == OLLAMA_VISION_MODEL and model != OLLAMA_MODEL:
            return '1m'
        return OLLAMA_KEEP_ALIVE

    @staticmethod
    def _model_for(messages):
        """Modele vision seulement si une image est effectivement jointe au message."""
        return OLLAMA_VISION_MODEL if messages[-1].get('images') else OLLAMA_MODEL

    def _chat(self, messages, model=None, stream=False, options=None):
        model = model or OLLAMA_MODEL
        payload = {
            'model': model,
            'messages': messages,
            'stream': stream,
            'keep_alive': self._keep_alive_for(model),
        }
        payload.update(_think_option(model))
        if options:
            payload['options'] = options
        r = self.session.post(OLLAMA_HOST + '/api/chat', json=payload, stream=stream, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError('Ollama {}: {}'.format(r.status_code, r.text[:300]))
        return r

    def respond(self, inputText, image_data=None, **kwargs):
        """Appel non-streaming (accueil, commentaire environnement...). Retourne un OaiResponse."""
        start = datetime.now()
        messages = self._build_messages(
            (self.system_instruction or u"You are a helpful assistant.") + SPOKEN_OUTPUT_INSTRUCTION,
            inputText, image_data)
        data = self._chat(messages, model=self._model_for(messages)).json()
        answer = strip_emojis((data.get('message') or {}).get('content', u'')).strip()

        self.history.append({'role': 'user', 'content': inputText})
        self.history.append({'role': 'assistant', 'content': answer})
        self._trim_history()

        print('Request delay', datetime.now() - start)
        fake = json.dumps({
            'choices': [{'message': {'content': answer, 'role': 'assistant'}}]
        })
        return OaiResponse(fake)

    def respond_stream(self, inputText, image_data=None):
        """
        Tour de dialogue principal. Generateur de Chunk(text).

        Le modele ecrit "[tag]" puis la reponse (voir EMOTION_TAG_FORMAT_INSTRUCTION) : le debut du
        flux est retenu jusqu'a la fin du tag, qui est pose dans self.last_emotion_tag AVANT de
        livrer le 1er chunk (meme garantie que la version Gemini : le tag est connu des la 1ere
        phrase, module_dialogue.py peut lancer l'animation en parallele du TTS). Le tag n'est
        jamais transmis comme texte a dire.
        """
        start = datetime.now()
        self.last_emotion_tag = None

        messages = self._build_messages(self.dialogue_system_instruction, inputText, image_data)
        r = self._chat(messages, model=self._model_for(messages), stream=True)

        prefix = u''
        raw = u''
        delivered = u''
        tag_resolved = False
        try:
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get('error'):
                    raise RuntimeError(data['error'])
                content = (data.get('message') or {}).get('content', u'')
                done = data.get('done')
                raw += content

                if not tag_resolved:
                    prefix += content
                    if _may_still_be_tag(prefix) and not done:
                        continue
                    self.last_emotion_tag, content = split_emotion_tag(prefix)
                    tag_resolved = True
                    print('Emotion tag delay', datetime.now() - start, '->', self.last_emotion_tag)

                content = strip_emojis(content)
                if content:
                    delivered += content
                    yield Chunk(content)
                if done:
                    break
        finally:
            r.close()

        self._last_stream_output = (delivered, raw)

        print('Speech stream total delay', datetime.now() - start)


if __name__ == '__main__':
    chat = LocalChat('test')
    while True:
        try:
            s = input('> ')
        except KeyboardInterrupt:
            break
        if not s:
            break
        out = u''
        for c in chat.respond_stream(s):
            out += c.text
            sys.stdout.write(c.text)
            sys.stdout.flush()
        chat.add_to_history(s, out)
        print('\n[emotion_tag: {}]'.format(chat.last_emotion_tag))
    print('Closing Local Chat')
