# -*- coding: utf-8 -*-

###########################################################
# Gemini chat class - remplace OpenAI GPT.
# Conserve la meme interface qu'avant (OaiChat) pour que
# oaiserver.py, oaiclient.py et module_dialogue.py continuent
# de fonctionner sans modification majeure.
#
# Nouveau : supporte l'envoi d'image (camera Pepper) via image_data.
#
# Author: adapte depuis Erik Billing, University of Skovde
# Requires: pip install google-genai pillow
###########################################################
import os, sys, codecs, json
from datetime import datetime
from oaichat.oairesponse import OaiResponse

import dotenv
dotenv.load_dotenv()

# Charger les variables d'environnement depuis config.env
try:
    with open('config.env', 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
except:
    pass

if sys.version_info[0] < 3:
    raise ImportError('Gemini Chat requires Python 3')

from google import genai
from google.genai import types

from oaichat.chatcommon import (
    VALID_EMOTION_TAGS, EMOTION_JSON_INSTRUCTION, LANGUAGE_PRIORITY_INSTRUCTION,
    load_prompt, trim_history,
)


# Schema structure impose a l'API Gemini (response_schema) pour la classification rapide de
# l'emotion_tag (voir _classify_emotion_tag) : contraint a l'enum exacte du catalogue (ou null),
# applique par l'API elle-meme (sampling contraint), pas seulement verifie a posteriori cote
# Python. Separe du texte "speech" (voir respond_stream) : demander UNIQUEMENT ce champ court
# rend la generation rapide, alors que l'ancien schema combine {speech, emotion_tag} forcait
# Gemini a terminer toute la reponse avant de renvoyer quoi que ce soit (pas de vrai streaming
# reseau possible avec un JSON structure).
EMOTION_TAG_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        'emotion_tag': types.Schema(
            type=types.Type.STRING,
            enum=sorted(VALID_EMOTION_TAGS),
            nullable=True,
        ),
    },
    required=['emotion_tag'],
)


class OaiChat:

    def __init__(self, user, prompt=None):
        self.log = None
        self.system_instruction = None
        self.emotion_system_instruction = None
        self.speech_system_instruction = None
        self.last_emotion_tag = None
        self.history = []
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        self.reset(user, prompt)

    def reset(self, user, prompt=None):
        self.user = user
        self.system_instruction, self.history = self.loadPrompt(
            prompt or os.getenv('OPENAI_PROMPTFILE')
        )
        # Deux prompts systeme distincts pour le tour de dialogue principal (voir
        # respond_stream), construits une seule fois ici plutot qu'a chaque appel :
        #
        # - emotion_system_instruction : persona + catalogue d'animations, utilise SEUL pour
        #   l'appel rapide de classification de l'emotion_tag (_classify_emotion_tag). Le
        #   contrat JSON est impose par EMOTION_TAG_SCHEMA, pas par ce texte.
        # - speech_system_instruction : persona + rappel de langue, SANS le catalogue
        #   d'animations (inutile pour generer la reponse parlee, et ~3000 caracteres de moins
        #   a traiter a chaque tour). Utilise pour le vrai streaming reseau du texte "speech",
        #   sans response_schema (le JSON structure empechait tout streaming token-par-token :
        #   Gemini doit terminer toute la reponse avant de renvoyer un JSON valide).
        #
        # Les autres appels (respond() pour le commentaire environnement, l'accueil, etc.)
        # continuent d'utiliser self.system_instruction tel quel, en texte libre.
        #
        # Pas de cache Gemini explicite ici : persona + catalogue ~= 1300 tokens, sous le
        # minimum de 2048 tokens exige par l'API pour le cache explicite (gemini-2.5-flash/pro) -
        # une tentative de cache serait systematiquement rejetee. Le catalogue est donc renvoye
        # dans system_instruction a chaque tour ; a ce volume l'economie de cache serait de toute
        # facon marginale au regard du cout de creation/gestion du cache.
        self.emotion_system_instruction = (
            (self.system_instruction or u"You are a helpful assistant.")
            + EMOTION_JSON_INSTRUCTION
        )
        self.speech_system_instruction = (
            (self.system_instruction or u"You are a helpful assistant.")
            + LANGUAGE_PRIORITY_INSTRUCTION
        )
        self.resetRequestLog()

    def resetRequestLog(self):
        pass

    def add_to_history(self, user_input, assistant_response):
        """Ajoute un echange complet a l'historique (utilise apres streaming)."""
        self.history.append({'role': 'user', 'content': user_input})
        self.history.append({'role': 'assistant', 'content': assistant_response})
        self._trim_history()

    def _trim_history(self):
        """Garde le prompt systeme puis les derniers echanges user/assistant."""
        trim_history(self.history)

    def _build_gemini_history(self):
        """Convertit l'historique (format OpenAI) vers le format attendu par Gemini."""
        self._trim_history()
        gemini_history = []
        for msg in self.history:
            role = msg['role']
            if role == 'system':
                continue  # Gere par system_instruction dans GenerateContentConfig
            if role == 'assistant':
                role = 'model'
            content = msg.get('content', '')
            if isinstance(content, str) and content:
                gemini_history.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content)]
                    )
                )
        return gemini_history

    def _decode_image(self, image_data):
        """
        Decompresse et convertit une image capturee par NaoQI (BGR brut en base64)
        en objet PIL.Image utilisable par Gemini.
        Retourne un PIL.Image ou None en cas d'echec.
        """
        try:
            import base64
            import io
            from PIL import Image
            raw_bytes = base64.b64decode(image_data['raw'])
            w, h = int(image_data['width']), int(image_data['height'])
            # Le mode est fourni par _do_capture ('BGR' ou 'RGB')
            mode = image_data.get('mode', 'BGR')
            if mode == 'BGR':
                img_pil = Image.frombytes('RGB', (w, h), raw_bytes, 'raw', 'BGR')
            else:
                img_pil = Image.frombytes('RGB', (w, h), raw_bytes)
            return img_pil
        except Exception as e:
            print('Warning: impossible de decoder image camera: ' + str(e))
            return None

    def respond(self, inputText, image_data=None, **kwargs):
        """
        Envoie inputText a Gemini et retourne un OaiResponse.

        image_data (optionnel) : dict avec les cles :
            'raw'    -> bytes en base64 (BGR, depuis ALVideoDevice Pepper)
            'width'  -> int
            'height' -> int
        """
        start = datetime.now()
        stream = kwargs.get('stream', False)

        # --- Construction des parties du message ---
        parts = [types.Part.from_text(text=inputText)]
        if image_data:
            img_pil = self._decode_image(image_data)
            if img_pil is not None:
                import io
                buf = io.BytesIO()
                img_pil.save(buf, format='JPEG')
                parts.append(
                    types.Part.from_bytes(
                        data=buf.getvalue(),
                        mime_type='image/jpeg'
                    )
                )
                print('Image camera incluse dans la requete Gemini ({}x{})'.format(
                    image_data['width'], image_data['height']
                ))

        # --- Configuration Gemini ---
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction or "You are a helpful assistant.",
        )

        # Modele configurable via GEMINI_MODEL dans .env, sinon gemini-2.5-flash par defaut
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')

        # --- Construction de l'historique Gemini ---
        gemini_history = self._build_gemini_history()

        # --- Creation du chat avec historique ---
        chat = self.client.chats.create(
            model=model_name,
            config=config,
            history=gemini_history
        )

        # --- Mode streaming ---
        if stream:
            # L'historique sera mis a jour apres via add_to_history() dans oaiserver.py
            return chat.send_message_stream(parts)

        # --- Mode normal ---
        response = chat.send_message(parts)
        answer = response.text

        # Mettre a jour l'historique de la session
        self.history.append({'role': 'user', 'content': inputText})
        self.history.append({'role': 'assistant', 'content': answer})
        self._trim_history()

        print('Request delay', datetime.now() - start)

        # Retourner un OaiResponse avec un dict compatible format OpenAI
        # (pour que oaiserver.py et oaiclient.py n'aient pas besoin de changer)
        fake = json.dumps({
            'choices': [{'message': {'content': answer, 'role': 'assistant'}}]
        })
        return OaiResponse(fake)

    def _classify_emotion_tag(self, inputText):
        """Appel Gemini dedie, separe du texte "speech" (voir respond_stream). Ne demande QUE
        emotion_tag (EMOTION_TAG_SCHEMA) : generation tres courte (un tag ou null), donc rapide,
        contrairement a l'ancien appel combine qui forcait a attendre toute la reponse parlee en
        plus du JSON. Pas d'historique de conversation transmis ici : le ton du dernier message
        utilisateur suffit au choix du tag, et ca garde le prompt (et donc l'appel) plus court.
        En cas d'echec ou de lenteur anormale, retourne simplement None (fallback deja gere par
        module_dialogue.py:_trigger_emotion_animation -> geste de parole par defaut).

        thinking_budget=0 : gemini-2.5-flash "pense" par defaut avant de repondre, et ces tokens
        de reflexion comptent dans max_output_tokens. Avec un budget de sortie volontairement
        court (classification simple), la reflexion consommait tout le budget et ne laissait
        plus rien pour le JSON lui-meme -> response.text vide -> echec systematique observe en
        test (json.loads sur chaine vide). Desactiver la reflexion pour cette tache de
        classification (pas de raisonnement necessaire) resout le probleme et accelere l'appel."""
        try:
            model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
            config = types.GenerateContentConfig(
                system_instruction=self.emotion_system_instruction,
                response_mime_type='application/json',
                response_schema=EMOTION_TAG_SCHEMA,
                max_output_tokens=40,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            chat = self.client.chats.create(model=model_name, config=config)
            response = chat.send_message([types.Part.from_text(text=inputText)])
            data = json.loads((response.text or u'').strip())
            tag = data.get('emotion_tag')
            return tag if tag in VALID_EMOTION_TAGS else None
        except Exception as e:
            print('WARNING: classification emotion_tag echouee, fallback None:', e)
            return None

    def respond_stream(self, inputText, image_data=None):
        """
        Tour de dialogue principal (utilise par module_dialogue.py:handle_streaming_response).
        DEUX appels Gemini separes desormais (voir _classify_emotion_tag) :
        1. emotion_tag : appel court et rapide, resultat pose dans self.last_emotion_tag AVANT
           de commencer le streaming (meme garantie de timing qu'avant : le tag est toujours
           connu au moment ou la 1ere phrase est prete a etre dite).
        2. speech : VRAI streaming reseau token-par-token (send_message_stream, texte libre,
           sans response_schema) : le decoupage par phrase dans
           module_dialogue.py:handle_streaming_response peut declencher le TTS des la 1ere
           phrase complete, sans attendre la fin de toute la generation.

        thinking_config desactive (thinking_budget=0) sur les deux appels : gemini-2.5-flash
        "reflechit" par defaut avant de produire le premier token de sortie, ce qui explique la
        variance observee en test sur "Speech first chunk delay" (0.9s a 6.5s d'un tour a
        l'autre) - ce temps de reflexion est invisible (aucun token de sortie pendant ce temps)
        mais bloque le debut du streaming. Le desactiver rend le premier chunk plus rapide et
        plus previsible. Contrepartie : les reponses perdent le raisonnement multi-etapes de
        Gemini 2.5 ; pour une persona qui doit repondre vite et sans reflexion complexe
        (repliques courtes), c'est le bon compromis. Si la qualite des reponses baisse trop,
        remplacer thinking_budget=0 par une petite valeur positive (ex: 128) plutot que de
        revenir a la reflexion dynamique par defaut.
        """
        start = datetime.now()

        self.last_emotion_tag = self._classify_emotion_tag(inputText)
        print('Emotion tag delay', datetime.now() - start)

        parts = [types.Part.from_text(text=inputText)]
        if image_data:
            img_pil = self._decode_image(image_data)
            if img_pil is not None:
                import io
                buf = io.BytesIO()
                img_pil.save(buf, format='JPEG')
                parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type='image/jpeg'))

        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        gemini_history = self._build_gemini_history()

        config = types.GenerateContentConfig(
            system_instruction=self.speech_system_instruction,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        chat = self.client.chats.create(model=model_name, config=config, history=gemini_history)

        stream_start = datetime.now()
        first_chunk = True
        for chunk in chat.send_message_stream(parts):
            if first_chunk:
                first_chunk = False
                print('Speech first chunk delay', datetime.now() - stream_start)
            yield chunk

        print('Speech stream total delay', datetime.now() - start)

    def loadPrompt(self, promptFile):
        return load_prompt(promptFile)

if __name__ == '__main__':
    chat = OaiChat('test')
    while True:
        try:
            s = input('> ')
        except KeyboardInterrupt:
            break
        if s:
            print(chat.respond(s).getText())
        else:
            break
    print('Closing Gemini Chat')
